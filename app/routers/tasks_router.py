"""Task routes (Phase 5 + Phase 8 project-team scoping)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import MessageResponse, TaskCreate, TaskOut, TaskUpdate
from app.services import audit_service, project_access, task_service

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(
    project_id: int | None = Query(None),
    assigned_to: int | None = Query(None),
    sprint_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tasks.view")),
):
    accessible_ids = project_access.accessible_project_ids(db, user=current_user)
    tasks = task_service.list_tasks(
        db,
        project_id=project_id,
        assigned_to=assigned_to,
        sprint_id=sprint_id,
        project_ids=accessible_ids,
    )
    return [TaskOut.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tasks.view")),
):
    task = task_service.get_task(db, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    project_access.assert_project_access(db, user=current_user, project_id=task.project_id)
    return TaskOut.model_validate(task)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tasks.create")),
):
    project_access.assert_project_access(db, user=current_user, project_id=payload.project_id)
    task = task_service.create_task(
        db,
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        due_date=payload.due_date,
        assigned_to=payload.assigned_to,
        sprint_id=payload.sprint_id,
        reported_by=current_user.id,
    )
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Task",
        entity_id=task.id,
        entity_name=task.title,
        action="created",
        description=f"{current_user.full_name} created task \"{task.title}\"",
        project_id=task.project_id,
    )
    return TaskOut.model_validate(task)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tasks.edit")),
):
    before = task_service.get_task(db, task_id=task_id)
    if before is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    project_access.assert_project_access(db, user=current_user, project_id=before.project_id)
    prev_status = before.status

    task = task_service.update_task(db, task_id=task_id, **payload.model_dump())

    # A status change coming from the kanban board's drag-and-drop (or
    # the "Move to..." menu) is logged as a distinct "moved" action so
    # the audit trail reads naturally ("moved from To Do to In
    # Progress") instead of a generic "updated".
    if payload.status and prev_status and payload.status != prev_status:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="Task",
            entity_id=task.id,
            entity_name=task.title,
            action="moved",
            field_changed="status",
            old_value=prev_status,
            new_value=task.status,
            description=(
                f"{current_user.full_name} moved task \"{task.title}\" "
                f"from {prev_status} to {task.status}"
            ),
            project_id=task.project_id,
        )
    else:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="Task",
            entity_id=task.id,
            entity_name=task.title,
            action="updated",
            description=f"{current_user.full_name} updated task \"{task.title}\"",
            project_id=task.project_id,
        )
    return TaskOut.model_validate(task)


@router.delete("/{task_id}", response_model=MessageResponse)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tasks.delete")),
):
    task = task_service.get_task(db, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    project_access.assert_project_access(db, user=current_user, project_id=task.project_id)

    task_service.delete_task(db, task_id=task_id)
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Task",
        entity_id=task_id,
        entity_name=task.title,
        action="deleted",
        description=f"{current_user.full_name} deleted task \"{task.title}\"",
        project_id=task.project_id,
    )
    return MessageResponse(message="Task deleted successfully")
