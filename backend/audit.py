from sqlalchemy.orm import Session

from .models import AuditLog, User


def audit(db: Session, actor: User, action: str, entity_type: str = None, entity_id: int = None, details: str = None):
    log = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(log)