"""In-app notification helper (Stage 5).

Low-volume, human-signal-only notifications: one row per meaningful event
(incident created, incident reviewed, result published, exam published,
session submitted). Never called for routine per-ingest churn so teachers are
not spammed.

``notify()`` adds the row WITHOUT committing so the caller keeps control of the
transaction (audit + commit happen together).
"""
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Notification, User


def notify(
    db: Session,
    user_id: Optional[int],
    type_: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
) -> Optional[Notification]:
    """Create a notification row for ``user_id`` (no commit)."""
    if not user_id:
        return None
    row = Notification(
        user_id=int(user_id),
        type=type_,
        title=title[:255],
        body=body,
        link=link,
        read=False,
    )
    db.add(row)
    return row


def notify_teachers(db: Session, type_: str, title: str,
                    body: Optional[str] = None, link: Optional[str] = None) -> int:
    """Notify every active teacher (and admin) once. Returns the number sent."""
    targets = (
        db.query(User.id)
        .filter(User.is_active.is_(True), User.role.in_(["teacher", "admin"]))
        .all()
    )
    for (uid,) in targets:
        notify(db, uid, type_, title, body, link)
    return len(targets)