"""Sprint routes (Phase 5 + Phase 8 project-team scoping)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import MessageResponse, SprintCreate, SprintOut, SprintUpdate
from app.services import audit_service, project_access, sprint_service

router = APIRouter(prefix="/api/v1/sprints", tags=["Sprints"])


@router.get("", response_model=list[SprintOut])
def list_sprints(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sprints.view")),
):
    accessible_ids = project_access.accessible_project_ids(db, user=current_user)
    sprints = sprint_service.list_sprints(db, project_id=project_id, project_ids=accessible_ids)
    return [SprintOut.model_validate(s) for s in sprints]


@router.get("/{sprint_id}", response_model=SprintOut)
def get_sprint(
    sprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sprints.view")),
):
    sprint = sprint_service.get_sprint(db, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sprint not found")
    project_access.assert_project_access(db, user=current_user, project_id=sprint.project_id)
    return SprintOut.model_validate(sprint)


@router.post("", response_model=SprintOut, status_code=status.HTTP_201_CREATED)
def create_sprint(
    payload: SprintCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sprints.create")),
):
    project_access.assert_project_access(db, user=current_user, project_id=payload.project_id)
    sprint = sprint_service.create_sprint(
        db,
        project_id=payload.project_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=payload.status,
    )
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Sprint",
        entity_id=sprint.id,
        entity_name=sprint.name,
        action="created",
        description=f"{current_user.full_name} created sprint \"{sprint.name}\"",
        project_id=sprint.project_id,
    )
    return SprintOut.model_validate(sprint)


@router.patch("/{sprint_id}", response_model=SprintOut)
def update_sprint(
    sprint_id: int,
    payload: SprintUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sprints.edit")),
):
    before = sprint_service.get_sprint(db, sprint_id=sprint_id)
    if before is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sprint not found")
    project_access.assert_project_access(db, user=current_user, project_id=before.project_id)
    prev_status = before.status

    sprint = sprint_service.update_sprint(db, sprint_id=sprint_id, **payload.model_dump())

    if payload.status and prev_status and payload.status != prev_status:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="Sprint",
            entity_id=sprint.id,
            entity_name=sprint.name,
            action="status_changed",
            field_changed="status",
            old_value=prev_status,
            new_value=sprint.status,
            description=(
                f"{current_user.full_name} moved sprint \"{sprint.name}\" "
                f"from {prev_status} to {sprint.status}"
            ),
            project_id=sprint.project_id,
        )
    else:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="Sprint",
            entity_id=sprint.id,
            entity_name=sprint.name,
            action="updated",
            description=f"{current_user.full_name} updated sprint \"{sprint.name}\"",
            project_id=sprint.project_id,
        )
    return SprintOut.model_validate(sprint)


@router.delete("/{sprint_id}", response_model=MessageResponse)
def delete_sprint(
    sprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sprints.delete")),
):
    sprint = sprint_service.get_sprint(db, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sprint not found")
    project_access.assert_project_access(db, user=current_user, project_id=sprint.project_id)

    sprint_service.delete_sprint(db, sprint_id=sprint_id)
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Sprint",
        entity_id=sprint_id,
        entity_name=sprint.name,
        action="deleted",
        description=f"{current_user.full_name} deleted sprint \"{sprint.name}\"",
        project_id=sprint.project_id,
    )
    return MessageResponse(message="Sprint deleted successfully")
