"""SubTask routes — nested under a Task (Project -> Sprint -> Task -> SubTask)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import MessageResponse, SubTaskCreate, SubTaskOut, SubTaskUpdate
from app.services import audit_service, project_access, subtask_service, task_service

router = APIRouter(prefix="/api/v1/subtasks", tags=["SubTasks"])


@router.get("", response_model=list[SubTaskOut])
def list_subtasks(
    task_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("subtasks.view")),
):
    accessible_ids = project_access.accessible_project_ids(db, user=current_user)
    subtasks = subtask_service.list_subtasks(db, task_id=task_id, project_ids=accessible_ids)
    return [SubTaskOut.model_validate(s) for s in subtasks]


@router.get("/{subtask_id}", response_model=SubTaskOut)
def get_subtask(
    subtask_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("subtasks.view")),
):
    subtask = subtask_service.get_subtask(db, subtask_id=subtask_id)
    if subtask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtask not found")
    parent_task = task_service.get_task(db, task_id=subtask.task_id)
    if parent_task is not None:
        project_access.assert_project_access(db, user=current_user, project_id=parent_task.project_id)
    return SubTaskOut.model_validate(subtask)


@router.post("", response_model=SubTaskOut, status_code=status.HTTP_201_CREATED)
def create_subtask(
    payload: SubTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("subtasks.create")),
):
    parent_task = task_service.get_task(db, task_id=payload.task_id)
    if parent_task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That task does not exist")
    project_access.assert_project_access(db, user=current_user, project_id=parent_task.project_id)

    subtask = subtask_service.create_subtask(
        db,
        task_id=payload.task_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        due_date=payload.due_date,
        assigned_to=payload.assigned_to,
        reported_by=current_user.id,
    )
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="SubTask",
        entity_id=subtask.id,
        entity_name=subtask.title,
        action="created",
        description=(
            f"{current_user.full_name} created subtask \"{subtask.title}\" "
            f"under task \"{parent_task.title}\""
        ),
        project_id=parent_task.project_id,
    )
    return SubTaskOut.model_validate(subtask)


@router.patch("/{subtask_id}", response_model=SubTaskOut)
def update_subtask(
    subtask_id: int,
    payload: SubTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("subtasks.edit")),
):
    before = subtask_service.get_subtask(db, subtask_id=subtask_id)
    if before is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtask not found")
    parent_task = task_service.get_task(db, task_id=before.task_id)
    if parent_task is not None:
        project_access.assert_project_access(db, user=current_user, project_id=parent_task.project_id)
    prev_status = before.status

    subtask = subtask_service.update_subtask(db, subtask_id=subtask_id, **payload.model_dump())

    if payload.status and prev_status and payload.status != prev_status:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="SubTask",
            entity_id=subtask.id,
            entity_name=subtask.title,
            action="moved",
            field_changed="status",
            old_value=prev_status,
            new_value=subtask.status,
            description=(
                f"{current_user.full_name} moved subtask \"{subtask.title}\" "
                f"from {prev_status} to {subtask.status}"
            ),
            project_id=parent_task.project_id if parent_task else None,
        )
    else:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="SubTask",
            entity_id=subtask.id,
            entity_name=subtask.title,
            action="updated",
            description=f"{current_user.full_name} updated subtask \"{subtask.title}\"",
            project_id=parent_task.project_id if parent_task else None,
        )
    return SubTaskOut.model_validate(subtask)


@router.delete("/{subtask_id}", response_model=MessageResponse)
def delete_subtask(
    subtask_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("subtasks.delete")),
):
    subtask = subtask_service.get_subtask(db, subtask_id=subtask_id)
    if subtask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtask not found")
    parent_task = task_service.get_task(db, task_id=subtask.task_id)
    if parent_task is not None:
        project_access.assert_project_access(db, user=current_user, project_id=parent_task.project_id)

    subtask_service.delete_subtask(db, subtask_id=subtask_id)
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="SubTask",
        entity_id=subtask_id,
        entity_name=subtask.title,
        action="deleted",
        description=f"{current_user.full_name} deleted subtask \"{subtask.title}\"",
        project_id=parent_task.project_id if parent_task else None,
    )
    return MessageResponse(message="Subtask deleted successfully")
