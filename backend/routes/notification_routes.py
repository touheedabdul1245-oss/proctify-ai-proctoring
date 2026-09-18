"""Stage 5 — in-app notification surfaces (role-aware, own-rows only).

Every authenticated user reads/writes only their own notifications. SQL is the
authoritative store; there is no push/email side-effect anywhere.
"""
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Notification, User
from ..schemas_stage4 import _P
from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = _P

    id: int
    type: str
    title: str
    body: str = ""
    link: str = ""
    read: bool = False
    created_at: Any = None


class UnreadCountOut(BaseModel):
    model_config = _P

    unread: int = 0


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        type=n.type or "",
        title=n.title or "",
        body=n.body or "",
        link=n.link or "",
        read=bool(n.read),
        created_at=n.created_at,
    )


@router.get("", response_model=List[NotificationOut])
def list_notifications(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = max(1, min(int(limit), 100))
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )
    return [_out(n) for n in rows]


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    unread = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read.is_(False))
        .count()
    )
    return UnreadCountOut(unread=unread)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read = True
    db.commit()
    return _out(row)


@router.post("/read-all", response_model=UnreadCountOut)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id, Notification.read.is_(False)
    ).update({"read": True})
    db.commit()
    return UnreadCountOut(unread=0)