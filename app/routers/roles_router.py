"""
Roles routes (Phase 3).

Read-only for now — roles/permissions are seeded by the app
(see app/services/role_service.py + app/main.py startup event).
A "create custom role" screen can be added later as a new POST route
here without touching anything else.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import Role, User
from app.schemas import RoleOut

router = APIRouter(prefix="/api/v1/roles", tags=["Roles"])


@router.get("", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.view")),
):
    roles = db.query(Role).order_by(Role.id.asc()).all()
    return [RoleOut.model_validate(r) for r in roles]
