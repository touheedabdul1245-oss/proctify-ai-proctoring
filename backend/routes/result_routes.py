"""Stage 5 — results & reports.

The final-exam Result table (reserved since Stage 1) becomes real: rows are
written when a session is finalized (see session_routes._finalize_session),
kept unpublished until a TEACHER explicitly publishes them (audited), and are
then visible to the student. Teacher surfaces provide the report grid, detail
(with proctoring context) and a CSV export.

Access control:
  * students: own results + own closed-session graded detail only;
  * teachers/admins: report grid, detail, publish, CSV export.
"""
import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth import get_current_user, require_admin, require_teacher
from ..database import get_db
from ..models import (
    AIServiceEvent,
    Evidence,
    Exam,
    ExamSession,
    Incident,
    Question,
    Result,
    Student,
    User,
)
from ..schemas_stage5 import (
    MonitoringSummaryOut,
    ResultPublishOut,
    StudentResultDetailOut,
    StudentResultOut,
    TeacherResultDetailOut,
    TeacherResultRowOut,
)
from ..services.notifications import notify as notify_user

router = APIRouter(prefix="/api", tags=["results"])

CLOSED = ("SUBMITTED", "EXPIRED")


def _student(db: Session, user: User) -> Student:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Students only")
    st = user.student_profile
    if not st:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return st


def _session_for_result(db: Session, exam_id: int, student_id_db: int) -> Optional[ExamSession]:
    return (
        db.query(ExamSession)
        .filter(
            ExamSession.exam_id == exam_id,
            ExamSession.student_id_db == student_id_db,
            ExamSession.status.in_(CLOSED),
        )
        .order_by(ExamSession.submitted_at.desc())
        .first()
    )


def _student_out(db: Session, r: Result) -> StudentResultOut:
    exam = r.exam
    sess = _session_for_result(db, r.exam_id, r.student_id_db)
    return StudentResultOut(
        result_id=r.id,
        exam_id=r.exam_id,
        exam_title=exam.title if exam else "",
        exam_code=exam.exam_code if exam else "",
        score=r.score or 0.0,
        total_marks=r.total_marks or 0,
        percent=r.percent,
        result_status=r.result_status or "GRADED",
        published=bool(r.published),
        session_token=sess.session_token if sess else "",
        session_status=sess.status if sess else "",
        submitted_at=sess.submitted_at if sess else None,
        published_at=r.published_at,
    )


def _monitoring_summary(db: Session, sess: Optional[ExamSession]) -> MonitoringSummaryOut:
    if not sess:
        return MonitoringSummaryOut()
    latest = None
    if sess.risk_rows:
        latest = max(sess.risk_rows, key=lambda x: x.recorded_at or x.id)
    incidents = sess.incidents or []
    return MonitoringSummaryOut(
        risk_level=(latest.level if latest else "NORMAL").upper(),
        risk_index=float(latest.index_value or latest.score or 0.0) if latest else 0.0,
        event_count=len(sess.proctoring_events or []),
        pending_incidents=sum(1 for i in incidents if (i.review_status or "PENDING") == "PENDING"),
        confirmed_incidents=sum(1 for i in incidents if (i.review_status or "") == "CONFIRMED"),
        dismissed_incidents=sum(1 for i in incidents if (i.review_status or "") in ("DISMISSED", "RESOLVED")),
        evidence_count=len(sess.evidence_records or []),
    )


# ---------------------------------------------------------------------------
# Student surface
# ---------------------------------------------------------------------------

@router.get("/student/results", response_model=List[StudentResultOut])
def my_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    st = _student(db, current_user)
    rows = (
        db.query(Result)
        .filter(Result.student_id_db == st.id)
        .order_by(Result.created_at.desc())
        .all()
    )
    return [_student_out(db, r) for r in rows]


@router.get("/student/sessions/{token}/result", response_model=StudentResultDetailOut)
def my_session_result(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    st = _student(db, current_user)
    sess = (
        db.query(ExamSession)
        .filter(ExamSession.session_token == token, ExamSession.student_id_db == st.id)
        .first()
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.status not in CLOSED:
        raise HTTPException(status_code=409, detail="Session is not closed yet")

    r = (
        db.query(Result)
        .filter(Result.exam_id == sess.exam_id, Result.student_id_db == st.id)
        .first()
    )

    exam = sess.exam
    answers = {a.question_id: a for a in sess.answers}
    published = bool(r.published if r else False)

    questions = (
        db.query(Question)
        .filter(Question.exam_id == sess.exam_id)
        .order_by(Question.order_index)
        .all()
    )
    graded = []
    for q in questions:
        a = answers.get(q.id)
        selected = a.selected_option if a else None
        correct = q.correct_option
        graded.append({
            "question_id": q.id,
            "order_index": q.order_index,
            "question_text": q.question_text,
            "marks": q.marks,
            "selected_option": selected,
            "correct_option": correct if published else None,
            "is_correct": a.is_correct if a and published else None,
            "marks_awarded": float(a.marks_awarded or 0.0) if a else 0.0,
        })

    base = _student_out(db, r) if r else StudentResultOut(
        exam_id=sess.exam_id,
        exam_title=exam.title if exam else "",
        exam_code=exam.exam_code if exam else "",
        session_token=sess.session_token,
        session_status=sess.status,
        submitted_at=sess.submitted_at,
    )
    return StudentResultDetailOut(
        **base.model_dump(exclude={"questions"}),
        questions=graded,
        monitoring=_monitoring_summary(db, sess),
    )


# ---------------------------------------------------------------------------
# Teacher surface
# ---------------------------------------------------------------------------

@router.get("/teacher/results", response_model=List[TeacherResultRowOut])
def teacher_results(
    exam_id: Optional[int] = None,
    published: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    query = db.query(Result)
    if exam_id:
        query = query.filter(Result.exam_id == exam_id)
    if published is not None:
        query = query.filter(Result.published.is_(bool(published)))
    rows = query.order_by(Result.student_id_db).all()

    out: List[TeacherResultRowOut] = []
    for r in rows:
        sess = _session_for_result(db, r.exam_id, r.student_id_db)
        student = r.student
        out.append(TeacherResultRowOut(
            result_id=r.id,
            student_id=student.id if student else 0,
            student_name=(student.full_name if student else "") or (r.student.email if r.student else ""),
            student_email=student.email if student else "",
            score=r.score or 0.0,
            total_marks=r.total_marks or 0,
            percent=r.percent,
            result_status=r.result_status or "GRADED",
            published=bool(r.published),
            session_token=sess.session_token if sess else "",
            submitted_at=sess.submitted_at if sess else None,
        ))
    return out


# ---------------------------------------------------------------------------
# CSV export (teacher) — formula-injection guarded. MUST be declared before
# /teacher/results/{result_id} so "export" never binds to the int path param.
# ---------------------------------------------------------------------------

def _csv_cell(value: Any) -> str:
    """Guard against spreadsheet formula injection (cells beginning with
    = + - @ are prefixed with a single quote so Excel never evaluates them)."""
    if value is None:
        return ""
    s = str(value)
    if s.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + s
    return s


@router.get("/teacher/results/export")
def export_results_csv(
    exam_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    query = db.query(Result)
    if exam_id:
        query = query.filter(Result.exam_id == exam_id)
    rows = query.order_by(Result.exam_id, Result.student_id_db).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "result_id", "exam_code", "exam_title", "student_id", "student_name",
        "student_email", "score", "total_marks", "percent", "status",
        "published", "submitted_at",
    ])
    for r in rows:
        sess = _session_for_result(db, r.exam_id, r.student_id_db)
        student = r.student
        writer.writerow([_csv_cell(v) for v in [
            r.id,
            r.exam.exam_code if r.exam else "",
            r.exam.title if r.exam else "",
            student.student_id if student else "",
            student.full_name if student else "",
            student.email if student else "",
            r.score,
            r.total_marks,
            r.percent,
            r.result_status,
            r.published,
            sess.submitted_at if sess else "",
        ]])
    buf.seek(0)
    fname = f"proctify-results-{exam_id if exam_id else 'all'}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/teacher/results/{result_id}", response_model=TeacherResultDetailOut)
def teacher_result_detail(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    r = db.query(Result).filter(Result.id == result_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Result not found")
    sess = _session_for_result(db, r.exam_id, r.student_id_db)
    incident_cards = []
    if sess:
        for i in sess.incidents or []:
            incident_cards.append({
                "id": i.id,
                "incident_type": i.incident_type or "",
                "risk_level": i.risk_level or "NORMAL",
                "review_status": i.review_status or "PENDING",
                "resolved": bool(i.resolved),
                "description": i.description or "",
                "created_at": i.created_at,
            })
    student = r.student
    base = TeacherResultRowOut(
        result_id=r.id,
        student_id=student.id if student else 0,
        student_name=(student.full_name if student else "") or (r.student.email if r.student else ""),
        student_email=student.email if student else "",
        score=r.score or 0.0,
        total_marks=r.total_marks or 0,
        percent=r.percent,
        result_status=r.result_status or "GRADED",
        published=bool(r.published),
        session_token=sess.session_token if sess else "",
        submitted_at=sess.submitted_at if sess else None,
    )
    return TeacherResultDetailOut(
        **base.model_dump(),
        exam_id=r.exam_id,
        exam_title=r.exam.title if r.exam else "",
        exam_code=r.exam.exam_code if r.exam else "",
        risk_level=_monitoring_summary(db, sess).risk_level,
        risk_index=_monitoring_summary(db, sess).risk_index,
        incidents=incident_cards,
        event_count=len(sess.proctoring_events or []) if sess else 0,
        evidence_count=len(sess.evidence_records or []) if sess else 0,
    )


@router.post("/teacher/results/{result_id}/publish", response_model=ResultPublishOut)
def publish_result(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    r = db.query(Result).filter(Result.id == result_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Result not found")
    if r.published:
        return ResultPublishOut(
            result_id=r.id, published=True,
            published_by=r.published_by, published_at=r.published_at,
        )
    r.published = True
    r.published_by = current_user.id
    r.published_at = datetime.utcnow()
    db.add(r)
    audit(
        db,
        current_user,
        action="RESULT_PUBLISH",
        entity_type="results",
        entity_id=r.id,
        details=f"result {r.percent}% on exam {r.exam_id}",
    )
    student = r.student
    if student:
        notify_user(
            db,
            student.user_id,
            type_="RESULT",
            title="Your result has been published",
            body=f"You scored {r.percent}% on '{r.exam.title if r.exam else 'the exam'}'.",
            link="/student/results",
        )
    db.commit()
    return ResultPublishOut(
        result_id=r.id, published=True,
        published_by=r.published_by, published_at=r.published_at,
    )