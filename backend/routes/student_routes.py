from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    BulkImport,
    ClassGroup,
    Enrollment,
    Exam,
    ExamAssignment,
    ExamBatchAssignment,
    Question,
    Student,
    Teacher,
    User,
)
from ..schemas import AssignedExamOut, ProfileOut

router = APIRouter(prefix="/api", tags=["student"])


def _assigned_exam_rows(db: Session, student: Student):
    """Return the set of exam ids a student is assigned to, direct or via batch."""
    direct = {eid for (eid,) in db.query(ExamAssignment.exam_id).filter(ExamAssignment.student_id_db == student.id).all()}
    batch = set()
    if student.class_id:
        for (eid,) in db.query(ExamBatchAssignment.exam_id).filter(ExamBatchAssignment.class_id == student.class_id).all():
            batch.add(eid)
    return direct | batch


def _assigned_exam_out(db: Session, exam: Exam, student: Student) -> AssignedExamOut:
    q_count = db.query(Question).filter(Question.exam_id == exam.id).count()
    direct = db.query(ExamAssignment).filter(
        ExamAssignment.exam_id == exam.id, ExamAssignment.student_id_db == student.id
    ).count() > 0
    via_batch = student.class_id is not None and db.query(ExamBatchAssignment).filter(
        ExamBatchAssignment.exam_id == exam.id, ExamBatchAssignment.class_id == student.class_id
    ).count() > 0
    via = []
    if direct:
        via.append("direct")
    if via_batch:
        via.append("batch")
    return AssignedExamOut(
        exam_id=exam.id,
        title=exam.title,
        description=exam.description,
        subject=exam.subject,
        exam_code=exam.exam_code,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        status=exam.status,
        is_published=exam.is_published,
        scheduled_start=exam.scheduled_start,
        scheduled_end=exam.scheduled_end,
        question_count=q_count,
        assigned_via=via,
    )


@router.get("/student/exams", response_model=list[AssignedExamOut])
def my_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_unpublished: bool = False,
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Students only")
    student = current_user.student_profile
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    ids = _assigned_exam_rows(db, student)
    exams = db.query(Exam).filter(Exam.id.in_(ids)).all()
    exams = [e for e in exams if e.is_published or include_unpublished]
    exams.sort(key=lambda e: e.scheduled_start or e.created_at)
    return [_assigned_exam_out(db, e, student) for e in exams]


@router.get("/student/exams/{exam_id}", response_model=AssignedExamOut)
def my_exam_detail(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Students only")
    student = current_user.student_profile
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam_id not in _assigned_exam_rows(db, student):
        raise HTTPException(status_code=403, detail="Exam not assigned to you")
    if not exam.is_published:
        raise HTTPException(status_code=403, detail="Exam has not been published yet")
    return _assigned_exam_out(db, exam, student)


@router.get("/profile", response_model=ProfileOut)
def my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = ProfileOut(user=current_user)
    if current_user.role == "student" and current_user.student_profile:
        st = current_user.student_profile
        profile.student_id = st.student_id
        klass = db.query(ClassGroup).filter(ClassGroup.id == st.class_id).first() if st.class_id else None
        profile.class_code = klass.code if klass else None
        profile.class_name = klass.name if klass else None
        profile.enrolled_total = db.query(Enrollment).filter(Enrollment.student_id_db == st.id).count()
        profile.assigned_exam_count = len(_assigned_exam_rows(db, st))
    elif current_user.role == "teacher" and current_user.teacher_profile:
        profile.teacher_id = current_user.teacher_profile.teacher_id
    return profile


# ---------------------------------------------------------------------------
# Role-aware dashboard stats
# ---------------------------------------------------------------------------

@router.get("/dashboard/stats")
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stats = {"role": current_user.role, "name": current_user.full_name, "counts": {}}
    if current_user.role == "admin":
        stats["counts"] = {
            "total_users": db.query(User).count(),
            "students": db.query(Student).count(),
            "teachers": db.query(Teacher).count(),
            "classes": db.query(ClassGroup).count(),
            "exams": db.query(Exam).count(),
            "imports": db.query(BulkImport).filter(BulkImport.status == "IMPORTED").count(),
            "enrollments": db.query(Enrollment).count(),
        }
    elif current_user.role == "teacher":
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        exam_query = db.query(Exam)
        if teacher:
            exam_query = exam_query.filter(Exam.teacher_id == teacher.id)
        exams = exam_query.all()
        stats["counts"] = {
            "total_exams": len(exams),
            "draft": sum(1 for e in exams if e.status == "DRAFT"),
            "scheduled": sum(1 for e in exams if e.status in ("SCHEDULED", "AVAILABLE")),
            "active": sum(1 for e in exams if e.status == "ACTIVE"),
            "completed": sum(1 for e in exams if e.status == "COMPLETED"),
            "archived": sum(1 for e in exams if e.status == "ARCHIVED"),
            "questions": db.query(Question).filter(Question.exam_id.in_([e.id for e in exams] or [0])).count(),
            "students": db.query(Student).count(),
        }
    elif current_user.role == "student":
        student = current_user.student_profile
        ids = list(_assigned_exam_rows(db, student))
        exams = db.query(Exam).filter(Exam.id.in_(ids)).all() if ids else []
        published = [e for e in exams if e.is_published]
        stats["counts"] = {
            "assigned_exams": len(exams),
            "published_exams": len(published),
            "upcoming": sum(1 for e in published if e.status in ("SCHEDULED", "AVAILABLE")),
            "available": sum(1 for e in published if e.status == "AVAILABLE"),
        }
    return stats