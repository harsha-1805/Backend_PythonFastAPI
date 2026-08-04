"""
Audit Log business logic.

`log_action` is the single write path every router calls after a
successful create/update/status-change/delete on a Project, Sprint,
Task, SubTask or Bug — mirroring how `role_service.user_has_permission`
is the single read path every permission check goes through. Keeping it
one function means the audit trail's shape can't drift between modules.

Deliberately *never* raises: a logging failure should never take down
the actual request that triggered it. Any exception here is caught and
swallowed (the underlying db.commit() from the calling router already
persisted the real change).
"""
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, User


def log_action(
    db: Session,
    *,
    actor: User | None,
    entity_type: str,
    entity_id: int,
    entity_name: str | None,
    action: str,
    description: str,
    field_changed: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    project_id: int | None = None,
) -> None:
    try:
        entry = AuditLog(
            actor_id=actor.id if actor else None,
            actor_name=actor.full_name if actor else "System",
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            action=action,
            field_changed=field_changed,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            project_id=project_id,
            description=description,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


def list_audit_logs(
    db: Session,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    project_id: int | None = None,
    actor_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    query = db.query(AuditLog).options(joinedload(AuditLog.actor))

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    if project_id is not None:
        query = query.filter(AuditLog.project_id == project_id)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)

    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total
