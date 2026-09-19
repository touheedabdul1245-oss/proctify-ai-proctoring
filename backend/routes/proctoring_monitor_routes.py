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
    Exam,
    ExamAssignment,
    ExamBatchAssignment,
    ExamReadinessCheck,
    ExamSession,
    Incident,
    RiskScore,
    Student,
    Teacher,
    TrustScore,
)
from ..proctoring import bands_contract
from ..proctoring.constants import TRUST_BASE_SCORE, trust_level_for
from ..schemas import LiveStudentRow, LiveStudentsOut, ProctoringIngestIn, ProctoringSignalOut
from ..services.exam_state import reconcile_exam
from ..schemas_stage4 import (
    ProctoringMonitorDetail,
    ProctoringMonitorEvidenceCard,
    ProctoringMonitorIncidentCard,
    ProctoringMonitorRiskRow,
    ProctoringMonitorSessionRow,
    ProctoringMonitorSummary,
    ProctoringMonitorTrustRow,
    ProctoringReviewIn,
    ProctoringReviewOut,
)
from ..services.proctoring_service import ingest_and_persist
from .evidence_media_routes import evidence_src

router = APIRouter(prefix="/api/proctoring/monitor", tags=["proctoring-monitor"])

RISK_ORDER = {"NORMAL": 0, "LOW": 1, "ATTENTION": 2, "ELEVATED": 3, "HIGH": 4}
CONTRACT = bands_contract()


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


def _latest_trust(session: ExamSession) -> Optional[TrustScore]:
    rows = session.trust_rows or []
    if not rows:
        return None
    return max(rows, key=lambda r: r.id)


def _trust_snapshot(session: ExamSession):
    """(score, level, delta) for a session's LIVE trust value.

    SQL (trust_scores) is the source of truth: the newest row wins. Sessions
    with no row yet are at the legal baseline (100 / NORMAL)."""
    last = _latest_trust(session)
    if last is None:
        return TRUST_BASE_SCORE, "NORMAL", 0.0
    score = float(last.trust_score or TRUST_BASE_SCORE)
    return score, (last.risk_level or trust_level_for(score)).upper(), float(last.delta or 0.0)


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
                media_url=evidence_src(e),
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
    rc = s.readiness
    if rc is not None:
        camera = bool(rc.camera_checked)
        audio = bool(rc.microphone_checked)
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
    trust_score, trust_level, trust_delta = _trust_snapshot(s)
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
        trust_score=round(trust_score, 2),
        trust_level=trust_level,
        trust_delta=round(trust_delta, 2),
    )


# ---------------------------------------------------------------------------
# read surfaces (SQL-authoritative)
# ---------------------------------------------------------------------------


def _assigned_ids_for_exams(db: Session, exam_ids: list[int]) -> dict[int, set[int]]:
    """Direct + batch-resolved student set per exam (SQL is the truth)."""
    out: dict[int, set[int]] = {eid: set() for eid in exam_ids}
    if not exam_ids:
        return out
    for (eid, sid) in db.query(ExamAssignment.exam_id, ExamAssignment.student_id_db).filter(
        ExamAssignment.exam_id.in_(exam_ids)
    ).all():
        out.setdefault(eid, set()).add(sid)
    for (eid, cid) in db.query(ExamBatchAssignment.exam_id, ExamBatchAssignment.class_id).filter(
        ExamBatchAssignment.exam_id.in_(exam_ids)
    ).all():
        for (sid,) in db.query(Student.id).filter(Student.class_id == cid).all():
            out.setdefault(eid, set()).add(sid)
    return out


@router.get("/live-students", response_model=LiveStudentsOut)
def live_students(
    current_user: Any = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Assigned-student live list for the teacher dashboard.

    One row per (assigned student, exam) so the teacher sees every student
    who may take each of their exams — not just students who already created a
    session. Statuses are read from SQL: NOT_STARTED / PREPARING / IN_PROGRESS
    (ACTIVE session) / SUBMITTED / EXPIRED / TERMINATED. ``monitor_status`` is
    LIVE only when a session is ACTIVE **and** the exam is still ACTIVE for it
    and AI events are being streamed — a non-ACTIVE session is never LIVE."""
    exam_query = db.query(Exam)
    if current_user.role == "teacher":
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile required")
        exam_query = exam_query.filter(Exam.teacher_id == teacher.id)
    exams = exam_query.order_by(Exam.scheduled_start.desc()).all()
    for e in exams:
        reconcile_exam(db, e)

    ids_by_exam = _assigned_ids_for_exams(db, [e.id for e in exams])
    student_ids = {sid for ids in ids_by_exam.values() for sid in ids}
    students = {s.id: s for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}

    session_map: dict[tuple[int, int], ExamSession] = {}
    if student_ids:
        sessions = (
            db.query(ExamSession)
            .filter(ExamSession.exam_id.in_([e.id for e in exams]), ExamSession.student_id_db.in_(student_ids))
            .all()
        )
        for s in sessions:
            session_map[(s.exam_id, s.student_id_db)] = s

    rows: list[LiveStudentRow] = []
    live_count = in_progress_count = preparing_count = not_started_count = 0
    submitted_count = expired_count = terminated_count = 0
    elevated_risk = pending_total = 0

    for exam in exams:
        for sid in sorted(ids_by_exam.get(exam.id, set())):
            student = students.get(sid)
            if student is None:
                continue
            session = session_map.get((exam.id, sid))
            status = "NOT_STARTED"
            monitor_status = "IDLE"
            session_id = session_token = None
            started_at = ends_at = last_activity = None
            trust_score: float | None = None
            trust_level = "NORMAL"
            risk_level = "NORMAL"
            risk_index: float | None = None
            camera = microphone = False
            pending = incidents = evidence = events_n = 0
            latest_event: str | None = None

            if session is not None:
                status = (session.status or "").upper()
                session_id = session.id
                session_token = session.session_token
                started_at = session.start_time
                ends_at = session.end_time
                last_activity = session.last_activity_at
                rc = session.readiness
                if rc is not None:
                    camera = bool(rc.camera_checked)
                    microphone = bool(rc.microphone_checked)
                incidents = len(session.incidents or [])
                pending = sum(1 for i in (session.incidents or []) if (i.review_status or "PENDING") == "PENDING")
                evidence = len(session.evidence_records or [])
                events = session.proctoring_events or []
                events_n = len(events)
                last_ts = _latest_trust(session)
                if last_ts is not None:
                    trust_score = round(float(last_ts.trust_score or TRUST_BASE_SCORE), 2)
                    trust_level = (last_ts.risk_level or trust_level_for(last_ts.trust_score or 100.0)).upper()
                lr = _latest_risk(session)
                if lr is not None:
                    risk_level = (lr.level or "NORMAL").upper()
                    risk_index = float(lr.index_value or 0.0)
                if risk_level == "HIGH":
                    elevated_risk += 1
                for e in events:
                    if e.occurred_at and (last_activity is None or e.occurred_at > last_activity):
                        last_activity = e.occurred_at
                    if e.event_type and latest_event is None:
                        latest_event = str(e.event_type)
                is_active_exam = exam.status in ("AVAILABLE", "ACTIVE")
                if status == "ACTIVE" and is_active_exam and events_n > 0:
                    monitor_status = "LIVE"
                elif status == "ACTIVE":
                    monitor_status = "ACTIVE"
                elif status in ("SUBMITTED", "EXPIRED", "TERMINATED"):
                    monitor_status = "DONE"

            pending_total += pending

            if status == "NOT_STARTED":
                not_started_count += 1
            elif status == "PREPARING":
                preparing_count += 1
            elif status == "ACTIVE":
                in_progress_count += 1
                if monitor_status == "LIVE":
                    live_count += 1
            elif status == "SUBMITTED":
                submitted_count += 1
            elif status == "EXPIRED":
                expired_count += 1
            elif status == "TERMINATED":
                terminated_count += 1

            rows.append(LiveStudentRow(
                exam_id=exam.id,
                exam_code=exam.exam_code,
                exam_title=exam.title,
                exam_status=exam.status,
                student_db_id=sid,
                student_id=student.student_id or "",
                student_name=student.full_name or student.email or f"Student#{sid}",
                student_email=student.email or "",
                status=status,
                monitor_status=monitor_status,
                session_id=session_id,
                session_token=session_token,
                session_started_at=started_at,
                session_ends_at=ends_at,
                trust_score=trust_score,
                trust_level=trust_level,
                risk_level=risk_level,
                risk_index=risk_index,
                camera=camera,
                microphone=microphone,
                pending_incidents=pending,
                incident_count=incidents,
                evidence_count=evidence,
                event_count_24h=events_n,
                last_activity_at=last_activity,
                latest_event=latest_event,
            ))

    return LiveStudentsOut(
        exams=len(exams),
        students=len(student_ids),
        live_count=live_count,
        in_progress_count=in_progress_count,
        preparing_count=preparing_count,
        not_started_count=not_started_count,
        submitted_count=submitted_count,
        expired_count=expired_count,
        terminated_count=terminated_count,
        elevated_risk=elevated_risk,
        pending_incidents=pending_total,
        rows=rows,
    )


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
    trust_rows = sorted(
        (s.trust_rows or []),
        key=lambda r: (r.recorded_at or r.id),
        reverse=True,
    )
    trust_score, trust_level, _ = _trust_snapshot(s)
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
        trust_score=round(trust_score, 2),
        trust_level=trust_level,
        trust_rows=[
            ProctoringMonitorTrustRow(
                id=r.id,
                trust_score=float(r.trust_score or TRUST_BASE_SCORE),
                delta=float(r.delta or 0.0),
                level=(r.risk_level or trust_level_for(r.trust_score or 100.0)).upper(),
                source=r.source or "",
                reason=r.reason or "",
                event_types=_split(r.event_types),
                recorded_at=r.recorded_at,
            )
            for r in trust_rows
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
                media_url=evidence_src(e),
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

    Uses the SHARED per-session engine (proctoring.registry) so sustained
    confirmations/cooldowns/repeats work across ingests.

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

    result = ingest_and_persist(db, current_user, session, payload.observation)
    audit(
        db,
        current_user,
        action="PROCTORING:SIGNAL_PERSISTED",
        entity_type="exam_session",
        entity_id=session.id,
        details=f"Ingest persisted risk={result['risk']['level']}, "
        f"trust={result.get('trust', {}).get('score')}, "
        f"events={result.get('events_count', 0)}, "
        f"incidents={len(result.get('incident_candidates') or [])} to SQL.",
    )
    db.commit()
    return ProctoringSignalOut(
        risk=result["risk"],
        runs=result.get("runs"),
        repeated=result.get("repeated"),
        incident_candidates=result.get("incident_candidates"),
        trust=result.get("trust") or {},
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
