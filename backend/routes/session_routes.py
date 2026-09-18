"""Stage 2 — student exam session lifecycle.

Covers: session creation (PREPARING), the pre-exam readiness wizard
(identity / camera / microphone / environment), starting the timer,
the live MCQ paper (navigation, answer autosave, mark-for-review),
heartbeat + resume, explicit submission and auto-submit on timeout.

All state is persisted in SQL (the authoritative store).
"""
import base64
import re
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth import get_current_user
from ..config import SESSION_PHOTO_DIR
from ..database import get_db
from ..models import (
    Answer,
    Exam,
    ExamAssignment,
    ExamBatchAssignment,
    ExamReadinessCheck,
    ExamSession,
    Question,
    Student,
    User,
)
from ..schemas import (
    AnswerSaveOut,
    AnswerSavePayload,
    PaperAnswerOut,
    PaperOut,
    PaperQuestionOut,
    ReadinessOut,
    ReadinessSubmit,
    SessionCreateOut,
    SessionOut,
    SessionStateOut,
    SubmitResponse,
)

router = APIRouter(prefix="/api", tags=["student-session"])

ACTIVE_STATUSES = ("ACTIVE",)
CLOSED_STATUSES = ("SUBMITTED", "EXPIRED")
OPEN_EXAM_STATUSES = ("SCHEDULED", "AVAILABLE", "ACTIVE")


def _now():
    return datetime.utcnow()


def _commit(db, current_user, action, entity_type, entity_id, details=None):
    audit(db, current_user, action, entity_type, entity_id, details)
    db.commit()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _require_student(user: User, db: Session) -> Student:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Students only")
    student = user.student_profile
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return student


def _get_session_for_student(db: Session, token: str, student: Student) -> ExamSession:
    session = db.query(ExamSession).filter(ExamSession.session_token == token).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.student_id_db != student.id:
        raise HTTPException(status_code=403, detail="Session does not belong to you")
    return session


def _assigned_exam_ids(db: Session, student: Student) -> set:
    direct = {
        eid
        for (eid,) in db.query(ExamAssignment.exam_id)
        .filter(ExamAssignment.student_id_db == student.id)
        .all()
    }
    batch = set()
    if student.class_id:
        for (eid,) in db.query(ExamBatchAssignment.exam_id).filter(
            ExamBatchAssignment.class_id == student.class_id
        ).all():
            batch.add(eid)
    return direct | batch


def _remaining_seconds(session: ExamSession) -> int | None:
    if session.status == "ACTIVE" and session.end_time:
        return max(0, int((session.end_time - _now()).total_seconds()))
    return None


def _readiness_out(check: ExamReadinessCheck | None) -> ReadinessOut:
    if not check:
        return ReadinessOut()
    return ReadinessOut(
        identity_verified=bool(check.identity_verified),
        identity_photo_path=check.identity_photo_path,
        camera_checked=bool(check.camera_checked),
        camera_error=check.camera_error,
        microphone_checked=bool(check.microphone_checked),
        microphone_error=check.microphone_error,
        environment_ready=bool(check.environment_ready),
        env_notes=check.env_notes,
    )


def _session_out(session: ExamSession) -> SessionOut:
    return SessionOut(
        id=session.id,
        session_token=session.session_token,
        exam_id=session.exam_id,
        status=session.status,
        start_time=session.start_time,
        end_time=session.end_time,
        last_activity_at=session.last_activity_at,
        submitted_at=session.submitted_at,
        expired_at=session.expired_at,
        readiness=_readiness_out(session.readiness),
        remaining_seconds=_remaining_seconds(session),
    )


def _check_exam_window(exam: Exam):
    """Gate helper: must be published, open, and inside the scheduled window."""
    if not exam.is_published:
        raise HTTPException(status_code=403, detail="Exam has not been published yet")
    if exam.status not in OPEN_EXAM_STATUSES:
        raise HTTPException(status_code=409, detail=f"Exam is not open for taking (status {exam.status})")
    now = _now()
    if exam.scheduled_start and now < exam.scheduled_start:
        raise HTTPException(status_code=409, detail="Exam has not started yet")
    if exam.scheduled_end and now > exam.scheduled_end:
        raise HTTPException(status_code=409, detail="Exam window has closed")


def _finalize_session(db: Session, session: ExamSession, expired: bool):
    """Evaluate answers and close the session."""
    now = _now()
    for ans in session.answers:
        q = ans.question
        if ans.selected_option:
            ans.is_correct = ans.selected_option == q.correct_option
            if ans.is_correct:
                ans.marks_awarded = float(q.marks)
            else:
                ans.marks_awarded = -abs(q.negative_marks or 0)
        else:
            ans.is_correct = None
            ans.marks_awarded = 0.0
        ans.submitted_at = now
    session.status = "EXPIRED" if expired else "SUBMITTED"
    session.submitted_at = now
    if expired:
        session.expired_at = now
    db.add(session)


def _finalize_if_due(db: Session, session: ExamSession) -> bool:
    """Auto-submit when the timer has run out. Returns True if it just happened."""
    if session.status == "ACTIVE" and session.end_time and _now() >= session.end_time:
        _finalize_session(db, session, expired=True)
        db.commit()
        return True
    return False


def _summary(db: Session, session: ExamSession) -> SubmitResponse:
    total = db.query(Question).filter(Question.exam_id == session.exam_id).count()
    answered = sum(1 for a in session.answers if a.selected_option)
    marked = sum(1 for a in session.answers if a.marked_for_review)
    return SubmitResponse(
        session_token=session.session_token,
        status=session.status,
        total_questions=total,
        answered_count=answered,
        marked_count=marked,
        unanswered_count=max(0, total - answered),
        submitted_at=session.submitted_at,
        auto=session.status == "EXPIRED",
        message="Exam submitted." if session.status == "SUBMITTED" else "Time is up — exam was submitted automatically.",
    )


def _save_identity_photo(data_url: str | None, token: str) -> str | None:
    if not data_url:
        return None
    m = re.match(r"data:image/([a-zA-Z0-9]+);base64,(.+)", data_url, re.S)
    if not m:
        return None
    ext = m.group(1).lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    try:
        raw = base64.b64decode(m.group(2))
    except Exception:
        return None
    if len(raw) > 6 * 1024 * 1024:
        return None
    SESSION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSION_PHOTO_DIR / f"{token}.{ext}"
    path.write_bytes(raw)
    return str(path)


# ---------------------------------------------------------------------------
# session state / creation
# ---------------------------------------------------------------------------

@router.get("/student/exams/{exam_id}/session", response_model=SessionStateOut)
def my_exam_session_state(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id, ExamSession.student_id_db == student.id)
        .first()
    )
    if not session:
        return SessionStateOut(session_token=None, status=None)
    _finalize_if_due(db, session)
    return SessionStateOut(
        session_token=session.session_token,
        status=session.status,
        start_time=session.start_time,
        end_time=session.end_time,
        remaining_seconds=_remaining_seconds(session),
    )


@router.post("/student/exams/{exam_id}/session", response_model=SessionCreateOut, status_code=201)
def create_exam_session(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    if exam_id not in _assigned_exam_ids(db, student):
        raise HTTPException(status_code=403, detail="Exam not assigned to you")

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    _check_exam_window(exam)

    session = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id, ExamSession.student_id_db == student.id)
        .first()
    )
    if session:
        # Resume path: return the existing session regardless of its state so
        # the UI can decide between wizard / paper / result.
        _finalize_if_due(db, session)
        return SessionCreateOut(
            session_token=session.session_token, status=session.status, exam_id=exam.id
        )

    session = ExamSession(
        session_token=uuid.uuid4().hex,
        exam_id=exam.id,
        student_id_db=student.id,
        status="PREPARING",
    )
    db.add(session)
    _commit(db, current_user, "SESSION_CREATE", "exam_sessions", None, f"exam {exam.id}")
    return SessionCreateOut(
        session_token=session.session_token, status=session.status, exam_id=exam.id
    )


# ---------------------------------------------------------------------------
# readiness wizard
# ---------------------------------------------------------------------------

@router.post("/student/sessions/{token}/readiness", response_model=ReadinessOut)
def submit_readiness(
    token: str,
    payload: ReadinessSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)
    if session.status == "ACTIVE":
        raise HTTPException(status_code=409, detail="Session already started")
    if session.status in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="Session already closed")

    check = session.readiness
    if not check:
        check = ExamReadinessCheck(exam_session_id=session.id)
        db.add(check)
        session.readiness = check

    now = _now()
    provided = payload.model_dump(exclude_unset=True)

    if "identity_verified" in provided:
        check.identity_verified = bool(payload.identity_verified)
        check.identity_confirmed_at = now if payload.identity_verified else None
    if "identity_photo_data" in provided:
        photo_path = _save_identity_photo(payload.identity_photo_data, session.session_token)
        if photo_path:
            check.identity_photo_path = photo_path

    if "camera_checked" in provided:
        check.camera_checked = bool(payload.camera_checked)
        check.camera_checked_at = now if payload.camera_checked else None
    if "camera_error" in provided:
        check.camera_error = payload.camera_error

    if "microphone_checked" in provided:
        check.microphone_checked = bool(payload.microphone_checked)
        check.microphone_checked_at = now if payload.microphone_checked else None
    if "microphone_error" in provided:
        check.microphone_error = payload.microphone_error

    if "environment_ready" in provided:
        check.environment_ready = bool(payload.environment_ready)
        check.environment_checked_at = now if payload.environment_ready else None
    if "env_notes" in provided:
        check.env_notes = payload.env_notes

    _commit(db, current_user, "READINESS_SUBMIT", "exam_sessions", session.id,
            f"identity={check.identity_verified} cam={check.camera_checked} mic={check.microphone_checked} env={check.environment_ready}")
    return _readiness_out(check)


@router.post("/student/sessions/{token}/start", response_model=SessionOut)
def start_session(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)
    if session.status == "ACTIVE":
        return _session_out(session)
    if session.status in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="Session already closed")

    check = session.readiness
    if not check or not (
        check.identity_verified
        and check.camera_checked
        and check.microphone_checked
        and check.environment_ready
    ):
        raise HTTPException(status_code=422, detail="Complete all readiness checks before starting")

    exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
    _check_exam_window(exam)

    now = _now()
    session.status = "ACTIVE"
    session.start_time = now
    session.end_time = now + timedelta(minutes=exam.duration_minutes)
    session.last_activity_at = now
    _commit(db, current_user, "SESSION_START", "exam_sessions", session.id,
            f"ends {session.end_time}")
    return _session_out(session)


@router.get("/student/sessions/{token}", response_model=SessionOut)
def get_session(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)
    _finalize_if_due(db, session)
    return _session_out(session)


@router.post("/student/sessions/{token}/heartbeat", response_model=SessionOut)
def heartbeat(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)
    if session.status == "ACTIVE":
        session.last_activity_at = _now()
        db.commit()
    _finalize_if_due(db, session)
    return _session_out(session)


# ---------------------------------------------------------------------------
# paper / answers
# ---------------------------------------------------------------------------

@router.get("/student/sessions/{token}/paper", response_model=PaperOut)
def get_paper(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)
    _finalize_if_due(db, session)

    if session.status not in ("ACTIVE",):
        raise HTTPException(status_code=409, detail=f"Session is {session.status}, paper is not available")

    exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
    questions = (
        db.query(Question)
        .filter(Question.exam_id == exam.id)
        .order_by(Question.order_index)
        .all()
    )
    answers = (
        db.query(Answer)
        .filter(Answer.exam_session_id == session.id)
        .all()
    )
    ans_map = {a.question_id: a for a in answers}
    return PaperOut(
        session_token=session.session_token,
        status=session.status,
        exam_id=exam.id,
        title=exam.title,
        description=exam.description,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        question_count=len(questions),
        start_time=session.start_time,
        end_time=session.end_time,
        remaining_seconds=_remaining_seconds(session),
        questions=[
            PaperQuestionOut(
                id=q.id,
                order_index=q.order_index,
                question_text=q.question_text,
                marks=q.marks,
                negative_marks=q.negative_marks,
                option_a=q.option_a,
                option_b=q.option_b,
                option_c=q.option_c,
                option_d=q.option_d,
            )
            for q in questions
        ],
        answers=[
            PaperAnswerOut(
                question_id=a.question_id,
                selected_option=a.selected_option,
                marked_for_review=a.marked_for_review,
                saved_at=a.saved_at,
            )
            for a in answers
        ],
    )


@router.put("/student/sessions/{token}/answers/{question_id}", response_model=AnswerSaveOut)
def save_answer(
    token: str,
    question_id: int,
    payload: AnswerSavePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)
    if _finalize_if_due(db, session):
        raise HTTPException(status_code=409, detail="Time is up — exam was submitted automatically")

    if session.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"Cannot save answers in {session.status} state")

    q = db.query(Question).filter(Question.id == question_id, Question.exam_id == session.exam_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found in this exam")

    ans = (
        db.query(Answer)
        .filter(Answer.exam_session_id == session.id, Answer.question_id == question_id)
        .first()
    )
    if not ans:
        ans = Answer(exam_session_id=session.id, question_id=question_id)
        db.add(ans)
    if payload.selected_option is not None:
        ans.selected_option = payload.selected_option
    if payload.marked_for_review is not None:
        ans.marked_for_review = payload.marked_for_review
    ans.saved_at = _now()
    session.last_activity_at = ans.saved_at
    db.commit()
    return AnswerSaveOut(
        question_id=ans.question_id,
        selected_option=ans.selected_option,
        marked_for_review=ans.marked_for_review,
        saved_at=ans.saved_at,
    )


# ---------------------------------------------------------------------------
# submission
# ---------------------------------------------------------------------------

@router.post("/student/sessions/{token}/submit", response_model=SubmitResponse)
def submit_exam(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)

    _finalize_if_due(db, session)
    if session.status in CLOSED_STATUSES:
        return _summary(db, session)
    if session.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"Cannot submit exam in {session.status} state")

    _finalize_session(db, session, expired=False)
    db.add(session)
    _commit(db, current_user, "SESSION_SUBMIT", "exam_sessions", session.id,
            f"answers saved")
    return _summary(db, session)


@router.get("/student/sessions/{token}/summary", response_model=SubmitResponse)
def session_summary(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _require_student(current_user, db)
    session = _get_session_for_student(db, token, student)
    return _summary(db, session)