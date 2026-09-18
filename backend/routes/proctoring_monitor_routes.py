"""Stage-4 teacher monitoring center API.

SQL is the single source of truth: this router READS from the Stage-1/2/3
tables (exam_sessions joined to students/exams, risk_scores, incidents,
evidence, ai_service_events, exam_readiness_checks) and, for the teacher
review workflow, WRITES only the human-verdict columns on Incident
(review_status/reviewed_by/reviewed_at/review_notes/resolved).

Nothing here produces verdicts. The engine stays suspicion-only (Stage-3
already guarantees that). The teacher is the ONLY final reviewer, and every
one of their verdicts is persisted to SQL + audited.

"Live" works exactly like the rest of the app: the frontend polls the SQL
read surface (overview + detail) and POSTs human review actions; there is no
second in-memory monitoring architecture and no auto-verdict path.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth import require_teacher
from ..database import get_db
from ..models import (
    AIServiceEvent,
    Exam,
    Evidence,
    ExamReadinessCheck,
    ExamSession,
    Incident,
    RiskScore,
    Student,
)
from ..proctoring import (
    bands_contract,
    build_engine,
    stream_from_observation,
)
from ..proctoring.incidents import incident_builder
from ..schemas import ProctoringIngestIn, ProctoringSignalOut
from ..schemas_stage4 import (
    ProctoringMonitorDetail,
    ProctoringMonitorEvidenceCard,
    ProctoringMonitorIncidentCard,
    ProctoringMonitorRiskRow,
    ProctoringMonitorSessionRow,
    ProctoringMonitorSummary,
    ProctoringReviewIn,
    ProctoringReviewOut,
    ProctoringStudentItemOut,
)

router = APIRouter(prefix="/api/proctoring/monitor", tags=["proctoring-monitor"])

RISK_ORDER = {"NORMAL": 0, "LOW": 1, "ATTENTION": 2, "ELEVATED": 3, "HIGH": 4}
CONTRACT = bands_contract()
LEVELS = CONTRACT.get("levels", ["NORMAL", "ATTENTION", "ELEVATED", "HIGH"])


def _jobj(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        import json

        return json.loads(text)
    except Exception:
        return None


def _student_name(student: Optional[Student]) -> str:
    if student is None:
        return ""
    return student.full_name or student.email or f"Student#{student.id}"


def _session_student(session: ExamSession) -> Optional[Student]:
    if session.student is not None:
        return session.student
    return None


def _latest_risk(session: ExamSession) -> Optional[RiskScore]:
    rows = session.risk_rows or []
    if not rows:
        return None
    return max(rows, key=lambda r: r.recorded_at or r.id)


def _risk_level(session: ExamSession) -> str:
    r = _latest_risk(session)
    if r is None:
        return "NORMAL"
    return (r.level or "NORMAL").upper()


def _risk_index(session: ExamSession) -> float:
    r = _latest_risk(session)
    if r is None:
        return 0.0
    return float(r.index_value or r.score or 0.0)


def _risk_factors(session: ExamSession) -> Optional[Dict[str, Any]]:
    r = _latest_risk(session)
    if r is None:
        return None
    return _jobj(r.factors) or {"reason": r.reason}


def _incident_card(i: Incident) -> ProctoringMonitorIncidentCard:
    evidence = [e for e in (i.evidence or [])]
    cards = []
    for e in evidence:
        cards.append(
            ProctoringMonitorEvidenceCard(
                id=e.id,
                evidence_type=e.media_type or "IMAGE",
                media_url=e.file_path or "",
                description=e.description or "",
                captured_at=e.captured_at,
                incident_id=e.incident_id,
                source=e.source or "",
            )
        )
    return ProctoringMonitorIncidentCard(
        id=i.id,
        incident_type=i.incident_type or "",
        risk_level=i.risk_level or _risk_label_from_index(i.confidence),
        confidence=i.confidence,
        description=i.description or "",
        event_count=i.event_count or 0,
        event_types=_split(i.event_types),
        first_event_at=i.first_event_at,
        last_event_at=i.last_event_at,
        review_status=i.review_status or "PENDING",
        resolved=bool(i.resolved),
        reviewed_by=i.reviewed_by,
        reviewed_at=i.reviewed_at,
        review_notes=i.review_notes or "",
        evidence=cards,
    )


def _split(csv_text: Optional[str]) -> Optional[List[str]]:
    if not csv_text:
        return None
    return [s.strip() for s in csv_text.split(",") if s.strip()]


def _risk_label_from_index(conf: Optional[float]) -> str:
    """Fallback label for cards missing a stored level; never a verdict."""
    if conf is None:
        return "NORMAL"
    c = float(conf)
    if c >= 0.9:
        return "HIGH"
    if c >= 0.7:
        return "ELEVATED"
    if c >= 0.45:
        return "ATTENTION"
    return "NORMAL"


def _row_from_session(s: ExamSession) -> ProctoringMonitorSessionRow:
    student = _session_student(s)
    exam = s.exam
    incidents = s.incidents or []
    pending = sum(1 for i in incidents if (i.review_status or "PENDING") == "PENDING")
    events = s.proctoring_events or []
    evidence = s.evidence_records or []
    camera = False
    audio = False
    for rc in s.readiness or []:
        camera = camera or bool(rc.camera_checked)
        audio = audio or bool(rc.microphone_checked)
    last_ev = _latest_risk(s)
    last_time = None
    if last_ev is not None:
        last_time = last_ev.recorded_at
    if events:
        for e in events:
            if e.occurred_at and (last_time is None or e.occurred_at > last_time):
                last_time = e.occurred_at
    recent_types = None
    ordered = [e for e in events if e.occurred_at is not None]
    ordered = sorted(ordered, key=lambda e: e.occurred_at, reverse=True)
    recent = ordered[:8]
    if recent:
        recent_types = sorted({str(e.event_type) for e in recent if e.event_type})
    active = recent_types is not None and len(recent) > 0
    return ProctoringMonitorSessionRow(
        id=s.id,
        exam_session_id=s.id,
        exam_id=s.exam_id,
        exam_code=exam.exam_code if exam else "",
        exam_title=exam.title if exam else "",
        session_token=s.session_token or "",
        student_id=student.id if student else 0,
        student_name=_student_name(student),
        student_email=student.email if student else "",
        status=(s.status or "").upper(),
        risk_level=_risk_level(s),
        risk_index=_risk_index(s),
        risk_factors=_risk_factors(s),
        pending_incidents=pending,
        incident_count=len(incidents),
        evidence_count=len(evidence),
        event_count_24h=len(events),
        recent_events=[
            {
                "id": e.id,
                "event_type": e.event_type or "",
                "source": e.source or "",
                "severity": e.severity or "",
                "confidence": e.confidence,
                "occurred_at": e.occurred_at,
            }
            for e in recent
        ],
        camera_available=camera,
        audio_available=audio,
        monitor_status="LIVE" if active else ("ACTIVE" if events else "IDLE"),
        last_activity_at=last_time,
    )


# ---------------------------------------------------------------------------
# read surfaces (SQL-authoritative)
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=ProctoringMonitorSummary)
def monitor_overview(
    current_user: Any = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(ExamSession)
        .join(Student, ExamSession.student_id_db == Student.id)
        .order_by(ExamSession.id.desc())
        .all()
    )
    rows = [_row_from_session(s) for s in sessions]
    counts = {"NORMAL": 0, "ATTENTION": 0, "ELEVATED": 0, "HIGH": 0}
    for r in rows:
        lvl = r.risk_level if r.risk_level in counts else "NORMAL"
        counts[lvl] = counts.get(lvl, 0) + 1
    return ProctoringMonitorSummary(
        sessions=rows,
        total_sessions=len(rows),
        live_count=sum(1 for r in rows if r.monitor_status == "LIVE"),
        attention_count=counts.get("ATTENTION", 0),
        elevated_count=counts.get("ELEVATED", 0),
        high_count=counts.get("HIGH", 0),
        pending_total=sum(r.pending_incidents for r in rows),
        contract=CONTRACT,
    )


@router.get("/sessions/{session_id}", response_model=ProctoringMonitorDetail)
def monitor_session_detail(
    session_id: int,
    current_user: Any = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    s = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Exam session not found")

    student = _session_student(s)
    exam = s.exam
    incidents = sorted(
        (s.incidents or []),
        key=lambda i: (i.created_at or datetime.min),
        reverse=True,
    )
    risk_rows = sorted(
        (s.risk_rows or []),
        key=lambda r: (r.recorded_at or r.id),
        reverse=True,
    )[:60]
    events = sorted(
        (e for e in (s.proctoring_events or []) if e.occurred_at),
        key=lambda e: e.occurred_at,
        reverse=True,
    )[:60]
    evidence = sorted(
        (s.evidence_records or []),
        key=lambda e: (e.captured_at or e.id),
        reverse=True,
    )
    return ProctoringMonitorDetail(
        exam_session_id=s.id,
        session_token=s.session_token or "",
        exam_id=s.exam_id,
        exam_title=exam.title if exam else "",
        exam_code=exam.exam_code if exam else "",
        student_id=student.id if student else 0,
        student_name=_student_name(student),
        student_email=student.email if student else "",
        status=(s.status or "").upper(),
        risk_level=_risk_level(s),
        risk_index=_risk_index(s),
        risk_factors=_risk_factors(s),
        risk_rows=[
            ProctoringMonitorRiskRow(
                id=r.id,
                level=(r.level or "NORMAL").upper(),
                risk_index=float(r.index_value or 0.0),
                score=float(r.score or 0.0),
                reason=r.reason or "",
                factors=_jobj(r.factors),
                recorded_at=r.recorded_at,
            )
            for r in risk_rows
        ],
        incidents=[_incident_card(i) for i in incidents],
        events=[
            {
                "id": e.id,
                "event_type": e.event_type or "",
                "source": e.source or "",
                "severity": e.severity or "",
                "confidence": e.confidence,
                "occurred_at": e.occurred_at,
                "repeat_count": e.repeat_count,
                "payload": _jobj(e.payload),
            }
            for e in events
        ],
        evidence=[
            ProctoringMonitorEvidenceCard(
                id=e.id,
                evidence_type=e.media_type or "IMAGE",
                media_url=e.file_path or "",
                description=e.description or "",
                captured_at=e.captured_at,
                incident_id=e.incident_id,
                source=e.source or "",
            )
            for e in evidence
        ],
        pending_incidents=sum(
            1 for i in incidents if (i.review_status or "PENDING") == "PENDING"
        ),
        camera_frame=None,
        alert_tone=None,
    )


# ---------------------------------------------------------------------------
# ingest bridge: persist the Stage-3 pure signal into SQL (the caller's job)
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=ProctoringSignalOut)
def monitor_ingest(
    payload: ProctoringIngestIn,
    current_user: Any = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Stage-4 satisfies Stage-3's implicit contract: the pure engine signal
    is persisted into SQL (risk_scores, incidents PENDING, evidence,
    ai_service_events) so the monitor overview/detail are live from SQL.

    The engine STILL never auto-verdicts: incidents are always created with
    review_status=PENDING, resolved=False, awaiting the teacher."""
    session_id = None
    try:
        session_id = int(str(payload.session_token).split("-")[0])
    except (TypeError, ValueError, IndexError):
        session_id = None

    session = None
    if session_id is not None:
        session = (
            db.query(ExamSession).filter(ExamSession.id == session_id).first()
        )
    if session is None and payload.session_token:
        deco = str(payload.session_token)
        session = (
            db.query(ExamSession)
            .filter(func.substr(ExamSession.session_token, 1, 36) == deco[:36])
            .first()
        )
    if session is None:
        raise HTTPException(status_code=404, detail="Exam session not found")

    if not payload.observation:
        raise HTTPException(
            status_code=422, detail="Proctoring ingest requires an observation payload"
        )

    now = datetime.utcnow()
    engine = build_engine(exam_session_id=session.id)
    signal = stream_from_observation(engine, payload.observation)

    # persist events
    for ev in signal.get("events", []) or []:
        db.add(
            AIServiceEvent(
                exam_session_id=session.id,
                source=ev.get("source") or "camera",
                event_type=ev.get("event_type") or "UNKNOWN",
                severity=ev.get("severity") or "INFO",
                confidence=ev.get("confidence"),
                repeat_count=ev.get("repeat_count") or 1,
                payload=_serialize(ev.get("payload")),
                occurred_at=ev.get("occurred_at") or now,
            )
        )

    # persist risk snapshot
    risk = signal.get("risk") or {}
    risk_index = _to_float(risk.get("index_value") or risk.get("index"))
    risk_level = _risk_label_from_index(risk_index)
    levels_map = {lv: i for i, lv in enumerate(LEVELS)}
    band_idx = levels_map.get(risk_level.upper(), 0)
    db.add(
        RiskScore(
            exam_session_id=session.id,
            level=risk_level.upper(),
            index_value=risk_index,
            score=_to_float(risk.get("score")),
            reason=risk.get("reason") or "",
            factors=_serialize(risk.get("factors")),
            recorded_at=now,
        )
    )

    incident = None
    candidates = signal.get("incident_candidates") or []
    if candidates:
        c = candidates[0]
        incident = Incident(
            exam_session_id=session.id,
            incident_type=c.get("incident_type") or c.get("type") or "SUSPICIOUS",
            risk_level=c.get("risk_level") or risk_level,
            confidence=_to_float(c.get("confidence")),
            description=c.get("reason") or c.get("description") or "",
            event_count=c.get("event_count") or 1,
            event_types=",".join(c.get("event_types") or []) or None,
            first_event_at=c.get("first_event_at") or now,
            last_event_at=c.get("last_event_at") or now,
            resolved=False,
            review_status="PENDING",
            created_at=now,
        )
        db.add(incident)
        db.flush()
        # evidence from the incident snapshot
        for ev in c.get("evidence") or []:
            db.add(
                Evidence(
                    exam_session_id=session.id,
                    incident_id=incident.id,
                    source=ev.get("source") or "camera",
                    file_path=ev.get("file_path") or ev.get("media_url") or "",
                    media_type=ev.get("media_type") or "IMAGE",
                    description=ev.get("description") or "",
                    metadata=_serialize(ev.get("meta") or ev.get("payload")),
                    captured_at=ev.get("captured_at") or now,
                )
            )
        audit(
            db,
            current_user,
            action="PROCTORING:INCIDENT_CANDIDATE",
            entity_type="incident",
            entity_id=incident.id,
            details=f"Session {session.id} flagged {c.get('incident_type')} "
            f"(PENDING review, risk {risk_level}).",
        )

    audit(
        db,
        current_user,
        action="PROCTORING:SIGNAL_PERSISTED",
        entity_type="exam_session",
        entity_id=session.id,
        details=f"Ingest persisted risk={risk_level}, events, "
        f"incidents={bool(incident)} to SQL.",
    )
    db.commit()
    return ProctoringSignalOut(
        risk={
            "level": risk_level.upper(),
            "level_index": band_idx,
            "index_value": risk_index,
            "factors": risk.get("factors"),
        },
        runs=signal.get("runs"),
        repeated=signal.get("repeated"),
        incident_candidates=(
            [{"incident_id": incident.id, "status": "PENDING"}] if incident else []
        ),
    )


# ---------------------------------------------------------------------------
# teacher review: the ONLY verdict maker, persisted to SQL + audited
# ---------------------------------------------------------------------------


@router.post("/review", response_model=ProctoringReviewOut)
def monitor_review(
    payload: ProctoringReviewIn,
    current_user: Any = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    incident = (
        db.query(Incident).filter(Incident.id == payload.incident_id).first()
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    action = (payload.action or "CONFIRM").upper()
    if action not in ("CONFIRM", "DISMISS", "RESOLVE"):
        raise HTTPException(status_code=422, detail="Unsupported review action")

    status = {"CONFIRM": "CONFIRMED", "DISMISS": "DISMISSED", "RESOLVE": "RESOLVED"}
    incident.review_status = status[action]
    incident.reviewed_by = current_user.id
    incident.reviewed_at = datetime.utcnow()
    incident.review_notes = payload.remarks or ""
    if action != "DISMISS":
        incident.resolved = True if action == "RESOLVE" else False
    else:
        incident.resolved = True
    audit(
        db,
        current_user,
        action=f"PROCTORING:REVIEW:{action}",
        entity_type="incident",
        entity_id=incident.id,
        details=payload.remarks or "",
    )
    db.commit()
    return ProctoringReviewOut(
        incident_id=incident.id,
        action=action,
        review_status=incident.review_status,
        resolved=bool(incident.resolved),
        reviewed_by=incident.reviewed_by,
        reviewed_at=incident.reviewed_at,
        remarks=incident.review_notes,
        ok=True,
        message=f"Incident #{incident.id} {action}-ed by teacher.",
    )


def _serialize(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        import json

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
