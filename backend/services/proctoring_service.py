"""Stage 5 — shared proctoring ingest -> SQL persistence (the caller's job).

This is the ARM that the Stage-3 engine contract always assumed existed: the
API layer decodes the client's frame (or accepts a pre-built observation),
feeds the SHARED per-session engine (see proctoring.registry), and persists
confirmed events, risk snapshots, PENDING incident candidates and evidence
into SQL. It is used by BOTH the teacher monitor ingest and the new student
live-proctoring feed so there is exactly one persistence path.

Guarantees preserved from Stages 3/4:
  * incidents are persisted PENDING + resolved=False (engine never verdicts);
  * one risk_scores row only when the band actually changed (keeps quiet
    sessions from flooding the timeline) or when events graduated;
  * duplicate PENDING incidents for the same session+type are not re-created;
  * every persist is audited; teacher/admins are notified once per incident.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..audit import audit
from ..models import (
    AIServiceEvent,
    Evidence,
    ExamSession,
    Incident,
    RiskScore,
    TrustScore,
    User,
)
from ..proctoring.constants import (
    EVENT_SEVERITY,
    RISK_BAND_UPPER,
    RISK_LEVELS,
    TRUST_BASE_SCORE,
    TRUST_LEVEL_NORMAL,
    trust_level_for,
)
from ..proctoring.registry import get_engine
from ..proctoring.evidence import store_image
from .notifications import notify_teachers


def _serialize(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _level_of_index(index: float) -> str:
    idx = _to_float(index)
    for i, upper in enumerate(RISK_BAND_UPPER):
        if idx <= upper:
            return RISK_LEVELS[i]
    return RISK_LEVELS[-1]


def _persist_trust(
    db: Session,
    session: ExamSession,
    signal: Dict[str, Any],
    now: datetime,
) -> None:
    """Write the 0..100 trust history into SQL (the source of truth).

    Guarantees:
      * every session starts with ONE baseline row (score 100, delta 0);
      * a NEW row is written ONLY when the engine's score actually moved vs.
        the last persisted row (delta = current - last, negative for a
        penalty, positive for recovery) — quiet/steady ingests never flood
        the history;
      * the trust band label (risk_level) is derived from the score via the
        single source of truth (constants.trust_level_for), never duplicated.
    """
    trust = signal.get("trust") or {}
    try:
        engine_score = float(trust.get("score", TRUST_BASE_SCORE))
    except (TypeError, ValueError):
        engine_score = TRUST_BASE_SCORE

    last = (
        db.query(TrustScore)
        .filter(TrustScore.exam_session_id == session.id)
        .order_by(TrustScore.id.desc())
        .first()
    )
    if last is None:
        db.add(
            TrustScore(
                exam_session_id=session.id,
                trust_score=TRUST_BASE_SCORE,
                delta=0.0,
                risk_level=TRUST_LEVEL_NORMAL,
                source="baseline",
                reason="session start",
                event_types=None,
                recorded_at=now,
            )
        )
        db.flush()
        last_score = TRUST_BASE_SCORE
    else:
        last_score = _to_float(last.trust_score)

    if abs(engine_score - last_score) < 0.005:
        return

    step_delta = round(engine_score - last_score, 2)
    source = trust.get("source") or ("recovery" if step_delta > 0 else "penalty")
    db.add(
        TrustScore(
            exam_session_id=session.id,
            trust_score=engine_score,
            delta=step_delta,
            risk_level=trust.get("level") or trust_level_for(engine_score),
            source=source,
            reason=trust.get("reason") or "",
            event_types=",".join(trust.get("families") or []) or None,
            recorded_at=now,
        )
    )
    db.flush()


def ingest_and_persist(
    db: Session,
    actor: User,
    session: ExamSession,
    observation: Dict[str, Any],
    frame_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Feed one observation into the shared engine and persist its SQL output.

    ``observation`` is the normalized engine input (see ai_service.pipeline /
    proctoring.observation). ``frame_bytes`` (optional raw JPEG) is stored as
    evidence when a confirmed event warrants a snapshot.
    """
    now = datetime.utcnow()
    engine, meta = get_engine(session.id)
    signal = engine.ingest(observation)

    confirmed = signal.get("events", []) or []
    event_ids: List[int] = []
    for ev in confirmed:
        row = AIServiceEvent(
            exam_session_id=session.id,
            source=ev.get("source") or "camera",
            event_type=ev.get("event_type") or "UNKNOWN",
            severity=EVENT_SEVERITY.get(ev.get("event_type"), ev.get("severity") or "INFO"),
            confidence=_to_float(ev.get("confidence")),
            repeat_count=int(ev.get("repeat_count") or 1),
            payload=_serialize(ev.get("payload")),
            occurred_at=now,
        )
        db.add(row)
        db.flush()
        event_ids.append(row.id)

    risk = signal.get("risk") or {}
    index = _to_float(risk.get("index_value") or risk.get("index"))
    level = (risk.get("level") or _level_of_index(index)).upper()
    last_persisted = (meta.get("last_risk_level") or "").upper()
    risk_changed = level != last_persisted or bool(confirmed)
    new_incidents: List[Dict[str, Any]] = []

    if risk_changed:
        db.add(
            RiskScore(
                exam_session_id=session.id,
                level=level,
                index_value=index,
                score=index,
                reason=risk.get("reason") or f"risk {level} (index {index})",
                factors=_serialize(risk.get("factors")),
                recorded_at=now,
            )
        )
        meta["last_risk_level"] = level

    pending_types = {
        t[0]
        for t in db.query(Incident.incident_type)
        .filter(
            Incident.exam_session_id == session.id,
            Incident.review_status.in_(["PENDING", "CONFIRMED"]),
        )
        .distinct()
        .all()
        if t[0] is not None
    }

    candidates = signal.get("incident_candidates") or []
    for c in candidates:
        itype = c.get("incident_type") or c.get("type") or "SUSPICIOUS"
        if itype in pending_types:
            continue
        incident = Incident(
            exam_session_id=session.id,
            incident_type=itype,
            risk_level=c.get("risk_level") or level,
            confidence=_to_float(c.get("confidence")),
            description=c.get("reason") or c.get("description") or "",
            event_count=int(c.get("event_count") or 1),
            event_types=",".join(c.get("event_types") or []) or None,
            first_event_at=c.get("first_event_at") or now,
            last_event_at=c.get("last_event_at") or now,
            resolved=False,
            review_status="PENDING",
            created_at=now,
        )
        db.add(incident)
        db.flush()
        pending_types.add(itype)

        if frame_bytes:
            stored = store_image(
                session.session_token or f"sess-{session.id}",
                session.id,
                {"event_type": itype, "confidence": _to_float(c.get("confidence"))},
                frame_bytes,
            )
            if stored.get("file_path"):
                db.add(
                    Evidence(
                        exam_session_id=session.id,
                        incident_id=incident.id,
                        source="camera",
                        file_path=stored["file_path"],
                        media_type=stored.get("media_type") or "image/jpeg",
                        description=f"{itype} — {c.get('description') or 'incident candidate'}",
                        meta_json=_serialize(stored.get("metadata")),
                        captured_at=now,
                    )
                )

        audit(
            db,
            actor,
            action="PROCTORING:INCIDENT_CANDIDATE",
            entity_type="incident",
            entity_id=incident.id,
            details=f"Session {session.id} flagged {itype} (PENDING review, risk {level}).",
        )
        notify_teachers(
            db,
            type_="INCIDENT",
            title=f"New proctoring incident: {itype}",
            body=f"Session #{session.id} ({itype}) is pending teacher review.",
            link=f"/teacher/monitor?session={session.id}",
        )
        new_incidents.append({"incident_id": incident.id, "status": "PENDING"})

    _persist_trust(db, session, signal, now)

    trust = signal.get("trust") or {}
    try:
        trust_score = float(trust.get("score", TRUST_BASE_SCORE))
    except (TypeError, ValueError):
        trust_score = TRUST_BASE_SCORE
    trust_delta = trust.get("delta", 0.0)
    try:
        trust_delta = float(trust_delta)
    except (TypeError, ValueError):
        trust_delta = 0.0

    return {
        "risk": {
            "level": level,
            "level_index": RISK_LEVELS.index(level) if level in RISK_LEVELS else 0,
            "index_value": index,
            "factors": risk.get("factors"),
        },
        "runs": signal.get("runs"),
        "repeated": signal.get("repeated"),
        "trust": {
            "score": round(trust_score, 2),
            "level": trust.get("level") or trust_level_for(trust_score),
            "delta": trust_delta,
            "source": trust.get("source") or "baseline",
            "reason": trust.get("reason") or "",
        },
        "incident_candidates": [
            {"incident_id": i["incident_id"], "status": i["status"]} for i in new_incidents
        ],
        "events_count": len(event_ids),
        "risk_changed": bool(risk_changed),
    }