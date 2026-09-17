from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_admin, require_teacher
from ..audit import audit
from ..database import get_db
from ..models import ClassGroup, Student, User
from ..schemas import ClassCreate, ClassOut, ClassUpdate

router = APIRouter(prefix="/api/classes", tags=["classes"])


def _to_out(db: Session, klass: ClassGroup) -> ClassOut:
    count = db.query(Student).filter(Student.class_id == klass.id).count()
    return ClassOut(
        id=klass.id,
        code=klass.code,
        name=klass.name,
        description=klass.description,
        student_count=count,
        created_at=klass.created_at,
    )


@router.get("", response_model=list[ClassOut])
def list_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
    include_empty: bool = True,
):
    classes = db.query(ClassGroup).order_by(ClassGroup.name).all()
    return [_to_out(db, c) for c in classes]


@router.post("", response_model=ClassOut, status_code=201)
def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if db.query(ClassGroup).filter(ClassGroup.code == payload.code.strip()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Class code already exists")
    klass = ClassGroup(code=payload.code.strip(), name=payload.name.strip(), description=payload.description)
    db.add(klass)
    db.flush()
    audit(db, current_user, "CLASS_CREATE", "classes", klass.id, f"{payload.code} - {payload.name}")
    db.commit()
    return _to_out(db, klass)


@router.get("/{class_id}", response_model=ClassOut)
def get_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    klass = db.query(ClassGroup).filter(ClassGroup.id == class_id).first()
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found")
    return _to_out(db, klass)


@router.put("/{class_id}", response_model=ClassOut)
def update_class(
    class_id: int,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    klass = db.query(ClassGroup).filter(ClassGroup.id == class_id).first()
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found")
    if payload.code and payload.code.strip() != klass.code:
        if db.query(ClassGroup).filter(ClassGroup.code == payload.code.strip()).first():
            raise HTTPException(status_code=409, detail="Class code already exists")
        klass.code = payload.code.strip()
    if payload.name:
        klass.name = payload.name.strip()
    if payload.description is not None:
        klass.description = payload.description
    audit(db, current_user, "CLASS_UPDATE", "classes", klass.id)
    db.commit()
    return _to_out(db, klass)


@router.delete("/{class_id}")
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    klass = db.query(ClassGroup).filter(ClassGroup.id == class_id).first()
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found")
    audit(db, current_user, "CLASS_DELETE", "classes", klass.id, klass.code)
    db.delete(klass)
    db.commit()
    return {"message": "Class deleted"}