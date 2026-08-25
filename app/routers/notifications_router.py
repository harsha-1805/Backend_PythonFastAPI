"""Notifications routes — backs the Navbar bell."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import NotificationListResponse, NotificationOut
from app.services import notification_service

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("notifications.view")),
):
    items = notification_service.list_notifications(db, user=current_user, unread_only=unread_only)
    count = notification_service.unread_count(db, user=current_user)
    return NotificationListResponse(unread_count=count, items=[NotificationOut.model_validate(n) for n in items])


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("notifications.view")),
):
    try:
        notification = notification_service.mark_read(db, user=current_user, notification_id=notification_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return NotificationOut.model_validate(notification)


@router.post("/read-all", response_model=dict)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("notifications.view")),
):
    updated = notification_service.mark_all_read(db, user=current_user)
    return {"updated": updated}
