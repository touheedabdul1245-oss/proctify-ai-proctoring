from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..auth import hash_password, require_admin, get_current_user
from ..audit import audit
from ..config import DEFAULT_STUDENT_PASSWORD
from ..database import get_db
from ..models import BulkImport, ClassGroup, Enrollment, Student, Teacher, User
from ..schemas import (
    BulkImportOut,
    BulkImportSummary,
    BulkPreviewOut,
    StudentCreate,
    StudentOut,
    StudentUpdate,
    UserCreate,
    UserDetail,
    UserOut,
    UserUpdate,
)
from ..services.enrollment_service import (
    BulkImportRow,
    confirm_import,
    parse_upload,
    stage_preview,
)

router = APIRouter(prefix="/api", tags=["users"])

USER_FIELDS = [
    "id", "email", "full_name", "role", "is_active", "created_at"
]


def _student_to_out(db: Session, s: Student) -> StudentOut:
    klass = db.query(ClassGroup).filter(ClassGroup.id == s.class_id).first() if s.class_id else None
    return StudentOut(
        id=s.id,
        user_id=s.user_id,
        student_id=s.student_id,
        email=s.email,
        full_name=s.full_name,
        class_id=s.class_id,
        class_code=klass.code if klass else None,
        class_name=klass.name if klass else None,
        is_active=s.user.is_active if s.user else True,
        created_at=s.created_at,
    )


def _user_to_detail(u: User, db: Session) -> UserDetail:
    detail = UserDetail.model_validate(u)
    if u.role == "student" and u.student_profile:
        st = u.student_profile
        klass = db.query(ClassGroup).filter(ClassGroup.id == st.class_id).first() if st.class_id else None
        detail.student_id = st.student_id
        detail.class_id = st.class_id
        detail.class_code = klass.code if klass else None
        detail.class_name = klass.name if klass else None
        detail.created_at = st.created_at
    elif u.role == "teacher" and u.teacher_profile:
        detail.teacher_id = u.teacher_profile.teacher_id
    return detail


# ---------------------------------------------------------------------------
# Users (admin)
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserDetail])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    role: str = None,
    q: str = None,
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.email.ilike(like), User.full_name.ilike(like)))
    users = query.order_by(User.created_at.desc()).all()
    return [_user_to_detail(u, db) for u in users]


@router.post("/users", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    if payload.role == "student":
        if not payload.student_id:
            raise HTTPException(status_code=422, detail="student_id is required for students")
        if db.query(Student).filter(Student.student_id == payload.student_id.strip()).first():
            raise HTTPException(status_code=409, detail="Student ID already exists")
        klass = None
        if payload.class_code:
            klass = db.query(ClassGroup).filter(ClassGroup.code == payload.class_code.strip()).first()
            if not klass:
                raise HTTPException(status_code=422, detail=f"Class '{payload.class_code}' not found")

    user = User(
        email=email,
        password_hash=hash_password(payload.password or DEFAULT_STUDENT_PASSWORD),
        full_name=payload.full_name.strip(),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == "student":
        student = Student(
            user_id=user.id,
            student_id=payload.student_id.strip(),
            email=email,
            full_name=payload.full_name.strip(),
            class_id=klass.id if klass else None,
        )
        db.add(student)
        db.flush()
        if klass:
            db.add(Enrollment(student_id_db=student.id, class_id=klass.id, source="manual"))
    elif payload.role == "teacher":
        tid = payload.teacher_id or f"T-{user.id:04d}"
        if db.query(Teacher).filter(Teacher.teacher_id == tid).first():
            tid = f"T-{user.id:04d}"
        db.add(Teacher(user_id=user.id, teacher_id=tid, email=email, full_name=payload.full_name.strip()))

    audit(db, current_user, "USER_CREATE", "users", user.id, f"{payload.role}:{email}")
    db.commit()
    db.refresh(user)
    return _user_to_detail(user, db)


@router.get("/users/{user_id}", response_model=UserDetail)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_detail(user, db)


@router.put("/users/{user_id}", response_model=UserDetail)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email and payload.email.lower() != user.email:
        if db.query(User).filter(User.email == payload.email.lower()).first():
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = payload.email.lower()
        if user.student_profile:
            user.student_profile.email = user.email
        if user.teacher_profile:
            user.teacher_profile.email = user.email
    if payload.full_name:
        user.full_name = payload.full_name.strip()
        if user.student_profile:
            user.student_profile.full_name = user.full_name
        if user.teacher_profile:
            user.teacher_profile.full_name = user.full_name
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.class_code is not None and user.student_profile:
        klass = None
        if payload.class_code:
            klass = db.query(ClassGroup).filter(ClassGroup.code == payload.class_code.strip()).first()
            if not klass:
                raise HTTPException(status_code=422, detail=f"Class '{payload.class_code}' not found")
        user.student_profile.class_id = klass.id if klass else None

    audit(db, current_user, "USER_UPDATE", "users", user.id)
    db.commit()
    db.refresh(user)
    return _user_to_detail(user, db)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    audit(db, current_user, "USER_DELETE", "users", user.id, user.email)
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

@router.get("/students", response_model=list[StudentOut])
def list_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    class_id: int = None,
    q: str = None,
):
    query = db.query(Student)
    if class_id:
        query = query.filter(Student.class_id == class_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Student.student_id.ilike(like), Student.full_name.ilike(like), Student.email.ilike(like))
        )
    students = query.order_by(Student.student_id).all()
    return [_student_to_out(db, s) for s in students]


@router.get("/students/{student_id}", response_model=StudentOut)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return _student_to_out(db, student)


@router.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if db.query(Student).filter(Student.student_id == payload.student_id.strip()).first():
        raise HTTPException(status_code=409, detail="Student ID already exists")

    klass = None
    if payload.class_code:
        klass = db.query(ClassGroup).filter(ClassGroup.code == payload.class_code.strip()).first()
        if not klass:
            raise HTTPException(status_code=422, detail=f"Class '{payload.class_code}' not found")

    user = User(
        email=email,
        password_hash=hash_password(payload.password or DEFAULT_STUDENT_PASSWORD),
        full_name=payload.full_name.strip(),
        role="student",
    )
    db.add(user)
    db.flush()

    student = Student(
        user_id=user.id,
        student_id=payload.student_id.strip(),
        email=email,
        full_name=payload.full_name.strip(),
        class_id=klass.id if klass else None,
    )
    db.add(student)
    db.flush()
    if klass:
        db.add(Enrollment(student_id_db=student.id, class_id=klass.id, source="manual"))

    audit(db, current_user, "STUDENT_CREATE", "students", student.id, payload.student_id)
    db.commit()
    return _student_to_out(db, student)


@router.put("/students/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if payload.student_id and payload.student_id != student.student_id:
        if db.query(Student).filter(Student.student_id == payload.student_id.strip()).first():
            raise HTTPException(status_code=409, detail="Student ID already exists")
        student.student_id = payload.student_id.strip()
    if payload.email and payload.email.lower() != student.email:
        if db.query(User).filter(User.email == payload.email.lower()).filter(User.id != student.user_id).first():
            raise HTTPException(status_code=409, detail="Email already registered")
        student.email = payload.email.lower()
        student.user.email = student.email
    if payload.full_name:
        student.full_name = payload.full_name.strip()
        student.user.full_name = student.full_name
    if payload.is_active is not None:
        student.user.is_active = payload.is_active
    if payload.class_code is not None:
        klass = None
        if payload.class_code:
            klass = db.query(ClassGroup).filter(ClassGroup.code == payload.class_code.strip()).first()
            if not klass:
                raise HTTPException(status_code=422, detail=f"Class '{payload.class_code}' not found")
        student.class_id = klass.id if klass else None
        if klass and not db.query(Enrollment).filter(
            Enrollment.student_id_db == student.id, Enrollment.class_id == klass.id
        ).first():
            db.add(Enrollment(student_id_db=student.id, class_id=klass.id, source="manual"))

    audit(db, current_user, "STUDENT_UPDATE", "students", student.id)
    db.commit()
    return _student_to_out(db, student)


@router.delete("/students/{student_id}")
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    audit(db, current_user, "STUDENT_DELETE", "students", student.id, student.student_id)
    db.delete(student.user)
    db.commit()
    return {"message": "Student deleted"}


# ---------------------------------------------------------------------------
# Bulk enrollment
# ---------------------------------------------------------------------------

@router.post("/bulk-enrollment/upload", response_model=BulkPreviewOut)
async def bulk_upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Empty file uploaded")
    try:
        parsed = parse_upload(raw, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if len(parsed.rows) == 0:
        raise HTTPException(status_code=422, detail="File contains no data rows")

    try:
        bi = stage_preview(db, parsed, total_rows=len(parsed.rows))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    rows = db.query(BulkImportRow).filter(BulkImportRow.bulk_import_id == bi.id).order_by(
        BulkImportRow.row_number
    ).all()

    from ..schemas import BulkImportRowOut
    out_rows = [BulkImportRowOut.model_validate(r) for r in rows]
    preview = BulkPreviewOut(
        preview_id=bi.id,
        total_rows=bi.total_rows,
        valid_rows=bi.valid_rows,
        invalid_rows=bi.invalid_rows,
        duplicate_rows=bi.duplicate_rows,
        new_rows=bi.valid_rows,
        invalid=[r for r in out_rows if r.status == "INVALID"],
        duplicates=[r for r in out_rows if r.status == "DUPLICATE"],
        new=[r for r in out_rows if r.status == "VALID"],
    )
    return preview


@router.post("/bulk-enrollment/confirm", response_model=BulkImportSummary)
def bulk_confirm(
    preview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        result = confirm_import(db, preview_id, created_by_user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    audit(
        db, current_user, "BULK_IMPORT", "bulk_imports", result["import_id"],
        f"Imported {result['imported']} students",
    )
    return BulkImportSummary(**result)


@router.post("/bulk-enrollment/cancel/{preview_id}")
def bulk_cancel(
    preview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    bi = db.query(BulkImport).filter(BulkImport.id == preview_id).first()
    if bi and bi.status == "PREVIEWED":
        bi.status = "CANCELLED"
        db.commit()
        return {"message": "Import cancelled"}
    return {"message": "Nothing to cancel"}


@router.get("/bulk-enrollment/history", response_model=list[BulkImportOut])
def bulk_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return db.query(BulkImport).filter(
        BulkImport.status.in_(["IMPORTED", "FAILED"])
    ).order_by(BulkImport.created_at.desc()).limit(50).all()