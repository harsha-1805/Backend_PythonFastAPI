"""Task routes (Phase 5 + Phase 8 project-team scoping)."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import MessageResponse, TaskAttachmentOut, TaskCreate, TaskOut, TaskUpdate
from app.services import audit_service, project_access, task_service
from app.services.image_storage import save_task_attachment_image

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
        acceptance_criteria=payload.acceptance_criteria,
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


# ---------------------------------------------------------------------------
# Reference screenshot attachments — extra visual grounding (design mocks,
# expected-result shots) fed to the AI test-case generator alongside the
# task's description/acceptance criteria. Separate from Bug.image_url: a
# task can carry several of these, a bug carries one.
# ---------------------------------------------------------------------------
@router.post("/{task_id}/attachments", response_model=TaskAttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_task_attachment(
    task_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tasks.edit")),
):
    task = task_service.get_task(db, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    project_access.assert_project_access(db, user=current_user, project_id=task.project_id)

    if image.content_type not in settings.allowed_image_content_type_list:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type: {image.content_type}",
        )
    image_bytes = await image.read()
    max_bytes = settings.max_image_size_mb * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {settings.max_image_size_mb}MB limit",
        )

    image_url = save_task_attachment_image(image_bytes, image.content_type, image.filename)
    attachment = task_service.add_attachment(
        db, task_id=task_id, image_url=image_url, uploaded_by=current_user.id
    )
    return TaskAttachmentOut.model_validate(attachment)


@router.delete("/attachments/{attachment_id}", response_model=MessageResponse)
def delete_task_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tasks.edit")),
):
    attachment = task_service.get_attachment(db, attachment_id=attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    task = task_service.get_task(db, task_id=attachment.task_id)
    if task is not None:
        project_access.assert_project_access(db, user=current_user, project_id=task.project_id)

    task_service.delete_attachment(db, attachment_id=attachment_id)
    return MessageResponse(message="Attachment deleted successfully")
