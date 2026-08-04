"""
Project routes (Phase 5 + Phase 8 team membership). Every route is
gated by `require_permission`, same pattern as admin_router.py.

Phase 8: list/get are additionally scoped by team membership via
project_access.py — Admin/Lead see every project, everyone else only
the ones they've been added to. Member management endpoints
(add/remove/list) live here too, gated by "projects.edit" — whoever can
edit a project is trusted to manage its team.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import (
    AddProjectMembersRequest,
    MessageResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdate,
)
from app.services import audit_service, project_access, project_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


@router.get("", response_model=ProjectListResponse)
def list_projects(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.view")),
):
    accessible_ids = project_access.accessible_project_ids(db, user=current_user)
    items, total = project_service.list_projects(
        db, search=search, project_ids=accessible_ids, page=page, page_size=page_size
    )
    return ProjectListResponse(
        total=total, page=page, page_size=page_size, items=[ProjectOut.model_validate(p) for p in items]
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.view")),
):
    project_access.assert_project_access(db, user=current_user, project_id=project_id)
    project = project_service.get_project(db, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectOut.model_validate(project)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.create")),
):
    project = project_service.create_project(
        db,
        name=payload.name,
        description=payload.description,
        owner_id=payload.owner_id or current_user.id,
        member_ids=payload.member_ids,
    )
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Project",
        entity_id=project.id,
        entity_name=project.name,
        action="created",
        description=f"{current_user.full_name} created project \"{project.name}\"",
        project_id=project.id,
    )
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.edit")),
):
    project = project_service.update_project(
        db,
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        owner_id=payload.owner_id,
    )
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Project",
        entity_id=project.id,
        entity_name=project.name,
        action="updated",
        description=f"{current_user.full_name} updated project \"{project.name}\"",
        project_id=project.id,
    )
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.delete")),
):
    project = project_service.get_project(db, project_id=project_id)
    project_service.delete_project(db, project_id=project_id)
    if project is not None:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="Project",
            entity_id=project_id,
            entity_name=project.name,
            action="deleted",
            description=f"{current_user.full_name} deleted project \"{project.name}\"",
        )
    return MessageResponse(message="Project deleted successfully")


# ---------------------------------------------------------------------------
# Team membership
# ---------------------------------------------------------------------------
@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.view")),
):
    project_access.assert_project_access(db, user=current_user, project_id=project_id)
    members = project_service.list_project_members(db, project_id=project_id)
    return [
        ProjectMemberOut(
            user_id=m.user_id, full_name=m.user.full_name, email=m.user.email, added_at=m.added_at
        )
        for m in members
    ]


@router.post("/{project_id}/members", response_model=list[ProjectMemberOut])
def add_project_members(
    project_id: int,
    payload: AddProjectMembersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.edit")),
):
    members = project_service.add_project_members(db, project_id=project_id, user_ids=payload.user_ids)
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Project",
        entity_id=project_id,
        entity_name=None,
        action="updated",
        description=f"{current_user.full_name} added {len(payload.user_ids)} member(s) to the project team",
        project_id=project_id,
    )
    return [
        ProjectMemberOut(
            user_id=m.user_id, full_name=m.user.full_name, email=m.user.email, added_at=m.added_at
        )
        for m in members
    ]


@router.delete("/{project_id}/members/{user_id}", response_model=MessageResponse)
def remove_project_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("projects.edit")),
):
    project_service.remove_project_member(db, project_id=project_id, user_id=user_id)
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Project",
        entity_id=project_id,
        entity_name=None,
        action="updated",
        description=f"{current_user.full_name} removed a member from the project team",
        project_id=project_id,
    )
    return MessageResponse(message="Member removed from project")
