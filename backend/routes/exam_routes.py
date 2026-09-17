from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from ..auth import require_teacher, get_current_user
from ..audit import audit
from ..config import EXAM_TRANSITIONS
from ..database import get_db
from ..models import ClassGroup, Exam, ExamAssignment, ExamBatchAssignment, Question, Student, Teacher, User
from ..schemas import (
    AssignedExamOut,
    ClassOut,
    ExamAssignPayload,
    ExamCreate,
    ExamDetail,
    ExamOut,
    ExamSchedulePayload,
    ExamStatusChange,
    ExamUpdate,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
    StudentOut,
)
from ..services.enrollment_service import generate_exam_code

router = APIRouter(prefix="/api", tags=["exams"])


# ---------------------------------------------------------------------------
# serialization helpers
# ---------------------------------------------------------------------------

def _exam_to_out(db: Session, exam: Exam) -> ExamOut:
    q_count = db.query(Question).filter(Question.exam_id == exam.id).count()
    a_count = db.query(ExamAssignment).filter(ExamAssignment.exam_id == exam.id).count()
    return ExamOut(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        exam_code=exam.exam_code,
        subject=exam.subject,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        status=exam.status,
        pass_marks=exam.pass_marks,
        scheduled_start=exam.scheduled_start,
        scheduled_end=exam.scheduled_end,
        is_published=exam.is_published,
        is_saved_draft=exam.is_saved_draft,
        question_count=q_count,
        assigned_student_count=a_count,
        created_by=exam.created_by,
        created_at=exam.created_at,
    )


def _question_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        exam_id=q.exam_id,
        order_index=q.order_index,
        question_text=q.question_text,
        question_type=q.question_type,
        marks=q.marks,
        option_a=q.option_a,
        option_b=q.option_b,
        option_c=q.option_c,
        option_d=q.option_d,
        correct_option=q.correct_option,
        negative_marks=q.negative_marks,
    )


def _assert_status_change(current: str, target: str):
    allowed = EXAM_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Illegal state transition {current} -> {target}. Allowed: {allowed}",
        )


# ---------------------------------------------------------------------------
# Exam CRUD
# ---------------------------------------------------------------------------

@router.get("/exams", response_model=list[ExamOut])
def list_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
    status: str = Query(None),
    q: str = Query(None),
    mine: bool = False,
):
    query = db.query(Exam)
    if mine:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if teacher:
            query = query.filter(Exam.teacher_id == teacher.id)
    if status:
        query = query.filter(Exam.status == status)
    if q:
        query = query.filter(Exam.title.ilike(f"%{q}%"))
    exams = query.order_by(Exam.created_at.desc()).all()
    return [_exam_to_out(db, e) for e in exams]


@router.get("/exams/{exam_id}", response_model=ExamDetail)
def get_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = db.query(Question).filter(Question.exam_id == exam.id).order_by(Question.order_index).all()
    assignments = db.query(ExamAssignment).filter(ExamAssignment.exam_id == exam.id).all()
    batch_assignments = db.query(ExamBatchAssignment).filter(ExamBatchAssignment.exam_id == exam.id).all()

    sids = [a.student_id_db for a in assignments]
    students = []
    if sids:
        for s in db.query(Student).filter(Student.id.in_(sids)).all():
            klass = db.query(ClassGroup).filter(ClassGroup.id == s.class_id).first() if s.class_id else None
            students.append(StudentOut(
                id=s.id, user_id=s.user_id, student_id=s.student_id, email=s.email,
                full_name=s.full_name, class_id=s.class_id,
                class_code=klass.code if klass else None, class_name=klass.name if klass else None,
                is_active=s.user.is_active if s.user else True, created_at=s.created_at,
            ))

    cids = [b.class_id for b in batch_assignments]
    batches = []
    if cids:
        for c in db.query(ClassGroup).filter(ClassGroup.id.in_(cids)).all():
            cnt = db.query(Student).filter(Student.class_id == c.id).count()
            batches.append(ClassOut(id=c.id, code=c.code, name=c.name, description=c.description, student_count=cnt, created_at=c.created_at))

    return ExamDetail(
        **_exam_to_out(db, exam).model_dump(
            exclude={"question_count", "assigned_student_count"}
        ),
        question_count=len(questions),
        assigned_student_count=len(students),
        questions=[_question_out(q) for q in questions],
        assigned_students=students,
        assigned_batches=batches,
    )


@router.post("/exams", response_model=ExamOut, status_code=201)
def create_exam(
    payload: ExamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if current_user.role == "teacher" and not teacher:
        raise HTTPException(status_code=403, detail="Teacher profile required")

    exam = Exam(
        title=payload.title.strip(),
        description=payload.description,
        exam_code=generate_exam_code(db),
        subject=payload.subject,
        duration_minutes=payload.duration_minutes,
        total_marks=payload.total_marks or 0,
        pass_marks=payload.pass_marks,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        created_by=current_user.id,
        teacher_id=teacher.id if teacher else None,
        status="DRAFT",
        is_published=False,
        is_saved_draft=bool(payload.save_as_draft),
    )
    db.add(exam)
    db.flush()
    audit(db, current_user, "EXAM_CREATE", "exams", exam.id, exam.title)
    db.commit()
    return _exam_to_out(db, exam)


@router.put("/exams/{exam_id}", response_model=ExamOut)
def update_exam(
    exam_id: int,
    payload: ExamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status == "ARCHIVED":
        raise HTTPException(status_code=422, detail="Archived exams cannot be edited")

    for field in ["title", "description", "subject", "duration_minutes", "total_marks", "pass_marks", "scheduled_start", "scheduled_end"]:
        val = getattr(payload, field)
        if val is not None:
            setattr(exam, field, val.strip() if isinstance(val, str) else val)

    audit(db, current_user, "EXAM_UPDATE", "exams", exam.id)
    db.commit()
    return _exam_to_out(db, exam)


@router.delete("/exams/{exam_id}")
def delete_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status in ("ACTIVE", "COMPLETED"):
        raise HTTPException(status_code=422, detail="Active/completed exams cannot be deleted")
    audit(db, current_user, "EXAM_DELETE", "exams", exam.id, exam.title)
    db.delete(exam)
    db.commit()
    return {"message": "Exam deleted"}


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

def _apply_question(db, payload: QuestionCreate, q: Question):
    q.question_text = payload.question_text.strip()
    q.marks = payload.marks
    q.order_index = payload.order_index
    q.option_a = q.option_b = q.option_c = q.option_d = None
    for opt in payload.options:
        key = opt.option.upper()
        if key in ("A", "B", "C", "D"):
            setattr(q, f"option_{key.lower()}", opt.text)
    q.correct_option = payload.correct_option.upper()
    q.negative_marks = payload.negative_marks


@router.get("/exams/{exam_id}/questions", response_model=list[QuestionOut])
def list_questions(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return [_question_out(q) for q in db.query(Question).filter(Question.exam_id == exam_id).order_by(Question.order_index).all()]


@router.post("/exams/{exam_id}/questions", response_model=QuestionOut, status_code=201)
def add_question(
    exam_id: int,
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status not in ("DRAFT", "SCHEDULED"):
        raise HTTPException(status_code=422, detail="Questions can only be added to DRAFT or SCHEDULED exams")

    order = payload.order_index or db.query(Question).filter(Question.exam_id == exam_id).count() + 1
    q = Question(exam_id=exam_id, order_index=order, question_type="MCQ")
    _apply_question(db, payload, q)
    db.add(q)
    db.flush()

    # auto-update total marks
    total = db.query(Question).filter(Question.exam_id == exam_id).count()
    sum_marks = sum(x for (x,) in db.query(Question.marks).filter(Question.exam_id == exam_id).all())
    exam.total_marks = sum_marks
    audit(db, current_user, "QUESTION_ADD", "questions", q.id, f"exam {exam_id} (q{total})")
    db.commit()
    return _question_out(q)


@router.put("/exams/{exam_id}/questions/{qid}", response_model=QuestionOut)
def update_question(
    exam_id: int,
    qid: int,
    payload: QuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    q = db.query(Question).filter(Question.id == qid, Question.exam_id == exam_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    _apply_question(db, payload, q)
    sum_marks = sum(x for (x,) in db.query(Question.marks).filter(Question.exam_id == exam_id).all())
    q.exam.total_marks = sum_marks
    audit(db, current_user, "QUESTION_UPDATE", "questions", q.id)
    db.commit()
    return _question_out(q)


@router.delete("/exams/{exam_id}/questions/{qid}")
def delete_question(
    exam_id: int,
    qid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    q = db.query(Question).filter(Question.id == qid, Question.exam_id == exam_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    exam = q.exam
    audit(db, current_user, "QUESTION_DELETE", "questions", q.id)
    db.delete(q)
    db.flush()
    exam.total_marks = sum(x for (x,) in db.query(Question.marks).filter(Question.exam_id == exam_id).all())
    db.commit()
    return {"message": "Question deleted"}


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

def _assigned_students_for_exam(db: Session, exam_id: int) -> set:
    rows = db.query(ExamAssignment.student_id_db).filter(ExamAssignment.exam_id == exam_id).all()
    direct = {r[0] for r in rows}
    batch_ids = [b.class_id for b in db.query(ExamBatchAssignment).filter(ExamBatchAssignment.exam_id == exam_id).all()]
    indirect = set()
    if batch_ids:
        for (sid,) in db.query(Student.id).filter(Student.class_id.in_(batch_ids)).all():
            indirect.add(sid)
    return direct | indirect


@router.post("/exams/{exam_id}/assign", response_model=ExamDetail)
def assign_exam(
    exam_id: int,
    payload: ExamAssignPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status == "ARCHIVED":
        raise HTTPException(status_code=422, detail="Archived exams cannot be assigned")

    added_students, added_batches = 0, 0
    for sid in payload.student_ids or []:
        if not db.query(Student).filter(Student.id == sid).first():
            continue
        if not db.query(ExamAssignment).filter(ExamAssignment.exam_id == exam_id, ExamAssignment.student_id_db == sid).first():
            db.add(ExamAssignment(exam_id=exam_id, student_id_db=sid))
            added_students += 1
    for cid in payload.class_ids or []:
        if not db.query(ClassGroup).filter(ClassGroup.id == cid).first():
            continue
        if not db.query(ExamBatchAssignment).filter(ExamBatchAssignment.exam_id == exam_id, ExamBatchAssignment.class_id == cid).first():
            db.add(ExamBatchAssignment(exam_id=exam_id, class_id=cid))
            added_batches += 1

    if added_students or added_batches:
        audit(db, current_user, "EXAM_ASSIGN", "exams", exam.id, f"+{added_students} students, +{added_batches} batches")
        db.commit()

    return get_exam(exam_id, db, current_user)


@router.post("/exams/{exam_id}/unassign", response_model=ExamDetail)
def unassign_exam(
    exam_id: int,
    payload: ExamAssignPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    for sid in payload.student_ids or []:
        row = db.query(ExamAssignment).filter(ExamAssignment.exam_id == exam_id, ExamAssignment.student_id_db == sid).first()
        if row:
            db.delete(row)
    for cid in payload.class_ids or []:
        row = db.query(ExamBatchAssignment).filter(ExamBatchAssignment.exam_id == exam_id, ExamBatchAssignment.class_id == cid).first()
        if row:
            db.delete(row)

    audit(db, current_user, "EXAM_UNASSIGN", "exams", exam.id)
    db.commit()
    return get_exam(exam_id, db, current_user)


@router.get("/exams/{exam_id}/assigned-students", response_model=list[StudentOut])
def assigned_students(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    ids = _assigned_students_for_exam(db, exam_id)
    out = []
    for s in db.query(Student).filter(Student.id.in_(ids)).order_by(Student.student_id).all():
        klass = db.query(ClassGroup).filter(ClassGroup.id == s.class_id).first() if s.class_id else None
        out.append(StudentOut(
            id=s.id, user_id=s.user_id, student_id=s.student_id, email=s.email,
            full_name=s.full_name, class_id=s.class_id,
            class_code=klass.code if klass else None, class_name=klass.name if klass else None,
            is_active=s.user.is_active if s.user else True, created_at=s.created_at,
        ))
    return out


# ---------------------------------------------------------------------------
# Scheduling, states, publish, preview
# ---------------------------------------------------------------------------

@router.post("/exams/{exam_id}/schedule", response_model=ExamOut)
def schedule_exam(
    exam_id: int,
    payload: ExamSchedulePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if payload.scheduled_end <= payload.scheduled_start:
        raise HTTPException(status_code=422, detail="scheduled_end must be after scheduled_start")

    exam.scheduled_start = payload.scheduled_start
    exam.scheduled_end = payload.scheduled_end

    if exam.status == "DRAFT":
        _assert_status_change("DRAFT", "SCHEDULED")
        exam.status = "SCHEDULED"
        exam.is_saved_draft = False

    audit(db, current_user, "EXAM_SCHEDULE", "exams", exam.id,
          f"{payload.scheduled_start} -> {payload.scheduled_end}")
    db.commit()
    return _exam_to_out(db, exam)


@router.post("/exams/{exam_id}/reschedule", response_model=ExamOut)
def reschedule_exam(
    exam_id: int,
    payload: ExamSchedulePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status in ("ACTIVE", "COMPLETED", "ARCHIVED"):
        raise HTTPException(status_code=422, detail="Only DRAFT/SCHEDULED/AVAILABLE exams can be rescheduled")
    if payload.scheduled_end <= payload.scheduled_start:
        raise HTTPException(status_code=422, detail="scheduled_end must be after scheduled_start")

    exam.scheduled_start = payload.scheduled_start
    exam.scheduled_end = payload.scheduled_end
    if exam.status == "AVAILABLE":
        exam.status = "SCHEDULED"
    audit(db, current_user, "EXAM_RESCHEDULE", "exams", exam.id)
    db.commit()
    return _exam_to_out(db, exam)


@router.post("/exams/{exam_id}/cancel", response_model=ExamOut)
def cancel_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status in ("ACTIVE", "COMPLETED"):
        raise HTTPException(status_code=422, detail="Cannot cancel an ACTIVE/COMPLETED exam")
    exam.status = "ARCHIVED"
    exam.is_published = False
    audit(db, current_user, "EXAM_CANCEL", "exams", exam.id)
    db.commit()
    return _exam_to_out(db, exam)


@router.post("/exams/{exam_id}/publish", response_model=ExamOut)
def publish_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    q_count = db.query(Question).filter(Question.exam_id == exam.id).count()
    if q_count == 0:
        raise HTTPException(status_code=422, detail="Add at least one question before publishing")
    if not exam.scheduled_start or not exam.scheduled_end:
        raise HTTPException(status_code=422, detail="Schedule the exam before publishing")

    exam.is_published = True
    exam.is_saved_draft = False
    if exam.status == "DRAFT":
        exam.status = "SCHEDULED"
    audit(db, current_user, "EXAM_PUBLISH", "exams", exam.id)
    db.commit()
    return _exam_to_out(db, exam)


@router.post("/exams/{exam_id}/status", response_model=ExamOut)
def change_status(
    exam_id: int,
    payload: ExamStatusChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    _assert_status_change(exam.status, payload.target_status)
    exam.status = payload.target_status
    audit(db, current_user, "EXAM_STATUS", "exams", exam.id, f"-> {payload.target_status}")
    db.commit()
    return _exam_to_out(db, exam)


@router.post("/exams/{exam_id}/preview", response_model=ExamDetail)
def preview_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    return get_exam(exam_id, db, current_user)