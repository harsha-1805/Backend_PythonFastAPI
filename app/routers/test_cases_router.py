"""AI Test Case Generator routes — generate, regenerate with feedback,
save to DB, list saved sets, preview, and delete.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import Bug, Project, Task, User
from app.schemas.test_case_schema import (
    SavedTestCaseOut,
    TestCaseGenerateRequest,
    TestCaseGenerateResponse,
    TestCaseRegenerateRequest,
    TestCaseSaveRequest,
)
from app.services import project_access, test_case_service

router = APIRouter(prefix="/api/v1/ai/test-cases", tags=["AI Test Cases"])


def _resolve_entity_and_project(
    db: Session, entity_type: str, entity_id: int, current_user: User
):
    """Resolve the entity, verify it exists, return (entity, project_id)."""
    if entity_type == "task":
        entity = db.query(Task).filter(Task.id == entity_id).first()
    else:
        entity = db.query(Bug).filter(Bug.id == entity_id).first()

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type.title()} not found",
        )
    project_access.assert_project_access(db, user=current_user, project_id=entity.project_id)
    return entity


@router.post("", response_model=TestCaseGenerateResponse)
def generate_test_cases(
    payload: TestCaseGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai_assistant.use")),
):
    _resolve_entity_and_project(db, payload.entity_type, payload.entity_id, current_user)

    entity_title, rows = test_case_service.generate(
        db, entity_type=payload.entity_type, entity_id=payload.entity_id
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI didn't return any usable test cases — try again, or add more detail "
            "(description / acceptance criteria) to this item first.",
        )

    csv_text = test_case_service.to_csv(entity_title, rows)
    return TestCaseGenerateResponse(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_title=entity_title,
        count=len(rows),
        test_cases=rows,
        csv=csv_text,
    )


@router.post("/regenerate", response_model=TestCaseGenerateResponse)
def regenerate_test_cases(
    payload: TestCaseRegenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai_assistant.use")),
):
    """Re-run test case generation incorporating the user's feedback about
    what was inaccurate, missing, or needs to be changed in the previous result.
    """
    _resolve_entity_and_project(db, payload.entity_type, payload.entity_id, current_user)

    entity_title, rows = test_case_service.regenerate(
        db,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        feedback=payload.feedback,
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI couldn't produce revised test cases — try rephrasing your feedback.",
        )

    csv_text = test_case_service.to_csv(entity_title, rows)
    return TestCaseGenerateResponse(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_title=entity_title,
        count=len(rows),
        test_cases=rows,
        csv=csv_text,
    )


@router.post("/save", response_model=SavedTestCaseOut)
def save_test_cases(
    payload: TestCaseSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai_assistant.use")),
):
    """Persist a generated (or regenerated) test case set so it can be
    accessed later from the Test Cases Library filtered by project/task.
    """
    # Verify the project exists and user has access.
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    project_access.assert_project_access(db, user=current_user, project_id=payload.project_id)

    record = test_case_service.save_test_cases(
        db,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_title=payload.entity_title,
        project_id=payload.project_id,
        test_cases=payload.test_cases,
        csv_data=payload.csv,
        saved_by_id=current_user.id,
    )
    return _to_out(record)


@router.get("/saved", response_model=list[SavedTestCaseOut])
def list_saved_test_cases(
    project_id: Optional[int] = Query(None),
    task_id: Optional[int] = Query(None),
    bug_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai_assistant.use")),
):
    """Return saved test case sets. Filterable by project_id, task_id, and bug_id."""
    # If a project_id filter is supplied, enforce membership.
    if project_id:
        project_access.assert_project_access(db, user=current_user, project_id=project_id)

    records = test_case_service.list_saved_test_cases(
        db, project_id=project_id, task_id=task_id, bug_id=bug_id, skip=skip, limit=limit
    )
    return [_to_out(r) for r in records]


@router.delete("/saved/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_test_case(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai_assistant.use")),
):
    found = test_case_service.delete_saved_test_case(db, record_id=record_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _to_out(record) -> SavedTestCaseOut:
    return SavedTestCaseOut(
        id=record.id,
        project_id=record.project_id,
        task_id=record.task_id,
        bug_id=record.bug_id,
        entity_type=record.entity_type,
        entity_title=record.entity_title,
        csv_data=record.csv_data,
        test_cases_json=record.test_cases_json,
        saved_by=record.saved_by,
        saver_name=record.saver.full_name if record.saver else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
