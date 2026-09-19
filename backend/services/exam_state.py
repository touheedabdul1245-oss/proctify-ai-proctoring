"""Authoritative exam-state reconciliation (SQL + the clock).

The database is the single source of truth for exam state. Most transitions
are explicit teacher actions, but the *window* is clock-driven and this module
owns it so no frontend timer ever decides whether an exam is open:

* published SCHEDULED exam whose window has arrived        -> AVAILABLE
* published SCHEDULED/AVAILABLE/ACTIVE exam past its end   -> COMPLETED
  (every still-ACTIVE session is auto-submitted as EXPIRED, answers graded)
* an AVAILABLE/ACTIVE exam moved back before its start     -> SCHEDULED

CANCELLED / TERMINATED / COMPLETED / ARCHIVED / DRAFT are never touched here —
DRAFT is the authoring cockpit, the terminal states are deliberately frozen.
"""
from datetime import datetime
from typing import Optional

from ..models import Exam, ExamSession

TERMINAL_STATES = ("COMPLETED", "CANCELLED", "TERMINATED", "ARCHIVED")


def reconcile_exam(db, exam: Exam, now: Optional[datetime] = None) -> str:
    """Bring *one* exam's persisted status in line with the clock. Persists any
    change and returns the effective status. Cheap: returns early for states
    that are not clock-driven. Float-safe: never writes unless status changes.
    """
    now = now or datetime.utcnow()
    status = exam.status

    if status in TERMINAL_STATES or status == "DRAFT" or not exam.is_published:
        return status

    start, end = exam.scheduled_start, exam.scheduled_end

    if end is not None and now >= end:
        _complete_exam(db, exam, now)
        return "COMPLETED"

    if start is not None and now < start:
        if status in ("AVAILABLE", "ACTIVE"):
            _set_status(db, exam, "SCHEDULED")
        return exam.status

    if status == "SCHEDULED":
        _set_status(db, exam, "AVAILABLE")
        return "AVAILABLE"

    # status is AVAILABLE or ACTIVE and the window is open: no change needed.
    return status


def _set_status(db, exam: Exam, status: str) -> None:
    exam.status = status
    db.commit()


def _complete_exam(db, exam: Exam, now: datetime) -> None:
    """Close the exam and auto-submit every still-ACTIVE session as EXPIRED.

    Answers are graded into the reserved Result row exactly like a student
    running out of time (SQL stays the source of truth, engine is dropped)."""
    exam.status = "COMPLETED"
    open_rows = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam.id, ExamSession.status == "ACTIVE")
        .all()
    )
    for session in open_rows:
        from ..routes.session_routes import _finalize_session

        _finalize_session(db, session, expired=True)
    db.commit()


def terminate_exam_sessions(db, exam: Exam) -> int:
    """Terminate every open (PREPARING/ACTIVE) session for an exam.

    Answers are PRESERVED as-is — no grading, no auto-submit. The teacher
    keeps an auditable record; a terminated exam can never be re-opened."""
    open_sessions = (
        db.query(ExamSession)
        .filter(
            ExamSession.exam_id == exam.id,
            ExamSession.status.in_(("PREPARING", "ACTIVE")),
        )
        .all()
    )
    for session in open_sessions:
        session.status = "TERMINATED"
    db.commit()
    return len(open_sessions)