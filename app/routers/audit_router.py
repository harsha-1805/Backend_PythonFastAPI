"""
Audit Log routes — read-only. Visible to QA, Lead ("Project Manager")
and Admin (see role_service.ROLE_PERMISSIONS: "audit.view").
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import AuditLogListResponse, AuditLogOut
from app.services import audit_service

router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Log"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    entity_type: str | None = Query(None, description="Project | Sprint | Task | SubTask | Bug"),
    entity_id: int | None = Query(None),
    project_id: int | None = Query(None),
    actor_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("audit.view")),
):
    items, total = audit_service.list_audit_logs(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        actor_id=actor_id,
        page=page,
        page_size=page_size,
    )
    return AuditLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[AuditLogOut.model_validate(i) for i in items],
    )
