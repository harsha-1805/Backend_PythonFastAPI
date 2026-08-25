"""
Notification business logic (Phase 7).

Backs the notification bell in the Navbar, which previously had no
`onClick` at all and a hardcoded "unread" dot that was never actually
tied to anything. Notifications are created server-side by other
services (comment_service today; bug_service/task_service can call
create_notification the same way for "assigned to you" / "status
changed" later without touching this file).
"""
from sqlalchemy.orm import Session

from app.models import Notification, User


def create_notification(
    db: Session,
    *,
    recipient_id: int,
    kind: str,
    message: str,
    link_path: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> Notification:
    notification = Notification(
        recipient_id=recipient_id,
        kind=kind,
        message=message,
        link_path=link_path,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def list_notifications(db: Session, *, user: User, unread_only: bool = False, limit: int = 30) -> list[Notification]:
    query = db.query(Notification).filter(Notification.recipient_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


def unread_count(db: Session, *, user: User) -> int:
    return db.query(Notification).filter(Notification.recipient_id == user.id, Notification.is_read.is_(False)).count()


def mark_read(db: Session, *, user: User, notification_id: int) -> Notification:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.recipient_id == user.id)
        .first()
    )
    if notification is None:
        raise LookupError("Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


def mark_all_read(db: Session, *, user: User) -> int:
    updated = (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id, Notification.is_read.is_(False))
        .update({"is_read": True})
    )
    db.commit()
    return updated
