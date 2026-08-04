"""
Bug routes (Phase 5 + Phase 8 project-team scoping).

`POST /api/v1/bugs` accepts `is_ai_generated: true` + the AI Bug
Generator's output fields as-is (see BugCreate in project_schema.py),
so the frontend flow is: call `POST /api/v1/ai/generate-bug` to get a
draft (which also returns `image_url` for the persisted screenshot),
let the user review/edit it, then `POST /api/v1/bugs` to save it.

`POST /api/v1/bugs/upload-image` is the equivalent for a MANUALLY
created bug (no AI involved) that still wants a screenshot attached —
upload the file first to get an `image_url`, then include that in the
BugCreate/BugUpdate payload.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas import BugCreate, BugListResponse, BugOut, BugUpdate, MessageResponse
from app.services import audit_service, bug_service, project_access
from app.services.image_storage import save_bug_image

router = APIRouter(prefix="/api/v1/bugs", tags=["Bugs"])


@router.get("", response_model=BugListResponse)
def list_bugs(
    project_id: int | None = Query(None),
    sprint_id: int | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    assigned_to: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("bugs.view")),
):
    accessible_ids = project_access.accessible_project_ids(db, user=current_user)
    items, total = bug_service.list_bugs(
        db,
        project_id=project_id,
        sprint_id=sprint_id,
        status=status_,
        assigned_to=assigned_to,
        search=search,
        project_ids=accessible_ids,
        page=page,
        page_size=page_size,
    )
    return BugListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[BugOut(**bug_service.serialize(b)) for b in items],
    )


@router.get("/{bug_id}", response_model=BugOut)
def get_bug(
    bug_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("bugs.view")),
):
    bug = bug_service.get_bug(db, bug_id=bug_id)
    if bug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bug not found")
    project_access.assert_project_access(db, user=current_user, project_id=bug.project_id)
    return BugOut(**bug_service.serialize(bug))


@router.post("/upload-image", status_code=status.HTTP_201_CREATED)
async def upload_bug_image(
    image: UploadFile = File(...),
    _: User = Depends(require_permission("bugs.create")),
):
    """Standalone screenshot upload for a manually-created bug (no AI
    analysis involved — that's POST /api/v1/ai/generate-bug). Returns
    the persisted image_url to include in the BugCreate/BugUpdate
    payload that follows.
    """
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

    image_url = save_bug_image(image_bytes, image.content_type, image.filename)
    return {"image_url": image_url}


@router.post("", response_model=BugOut, status_code=status.HTTP_201_CREATED)
def create_bug(
    payload: BugCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("bugs.create")),
):
    project_access.assert_project_access(db, user=current_user, project_id=payload.project_id)
    bug = bug_service.create_bug(db, reported_by=current_user.id, **payload.model_dump())
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Bug",
        entity_id=bug.id,
        entity_name=bug.title,
        action="created",
        description=f"{current_user.full_name} reported bug \"{bug.title}\"",
        project_id=bug.project_id,
    )
    return BugOut(**bug_service.serialize(bug))


@router.patch("/{bug_id}", response_model=BugOut)
def update_bug(
    bug_id: int,
    payload: BugUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("bugs.edit")),
):
    before = bug_service.get_bug(db, bug_id=bug_id)
    if before is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bug not found")
    project_access.assert_project_access(db, user=current_user, project_id=before.project_id)
    prev_status = before.status

    bug = bug_service.update_bug(db, bug_id=bug_id, **payload.model_dump())

    if payload.status and prev_status and payload.status != prev_status:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="Bug",
            entity_id=bug.id,
            entity_name=bug.title,
            action="status_changed",
            field_changed="status",
            old_value=prev_status,
            new_value=bug.status,
            description=(
                f"{current_user.full_name} moved bug \"{bug.title}\" "
                f"from {prev_status} to {bug.status}"
            ),
            project_id=bug.project_id,
        )
    else:
        audit_service.log_action(
            db,
            actor=current_user,
            entity_type="Bug",
            entity_id=bug.id,
            entity_name=bug.title,
            action="updated",
            description=f"{current_user.full_name} updated bug \"{bug.title}\"",
            project_id=bug.project_id,
        )
    return BugOut(**bug_service.serialize(bug))


@router.patch("/{bug_id}/assign", response_model=BugOut)
def assign_bug(
    bug_id: int,
    assigned_to: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("bugs.assign")),
):
    before = bug_service.get_bug(db, bug_id=bug_id)
    if before is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bug not found")
    project_access.assert_project_access(db, user=current_user, project_id=before.project_id)

    bug = bug_service.update_bug(db, bug_id=bug_id, assigned_to=assigned_to)
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Bug",
        entity_id=bug.id,
        entity_name=bug.title,
        action="assigned",
        description=(
            f"{current_user.full_name} assigned bug \"{bug.title}\" to "
            f"{bug.assignee.full_name if bug.assignee else 'someone'}"
        ),
        project_id=bug.project_id,
    )
    return BugOut(**bug_service.serialize(bug))


@router.delete("/{bug_id}", response_model=MessageResponse)
def delete_bug(
    bug_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("bugs.delete")),
):
    bug = bug_service.get_bug(db, bug_id=bug_id)
    if bug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bug not found")
    project_access.assert_project_access(db, user=current_user, project_id=bug.project_id)

    bug_service.delete_bug(db, bug_id=bug_id)
    audit_service.log_action(
        db,
        actor=current_user,
        entity_type="Bug",
        entity_id=bug_id,
        entity_name=bug.title,
        action="deleted",
        description=f"{current_user.full_name} deleted bug \"{bug.title}\"",
        project_id=bug.project_id,
    )
    return MessageResponse(message="Bug deleted successfully")
