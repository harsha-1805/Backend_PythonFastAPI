"""AI Test Case Generator route — drag a Task or Bug into the AI
Assistant (or use the Sparkles action on its card/row) to get a
grounded set of QA test cases, previewed in-chat and downloadable as
CSV. See app/services/test_case_service.py for how the prompt is built.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import Bug, Task, User
from app.schemas.test_case_schema import TestCaseGenerateRequest, TestCaseGenerateResponse
from app.services import project_access, test_case_service

router = APIRouter(prefix="/api/v1/ai/test-cases", tags=["AI Test Cases"])


@router.post("", response_model=TestCaseGenerateResponse)
def generate_test_cases(
    payload: TestCaseGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai_assistant.use")),
):
    # Resolve the entity's project first so we can enforce the same
    # team-membership access check every other module uses, before
    # spending a Gemini call on something the caller can't see.
    if payload.entity_type == "task":
        entity = db.query(Task).filter(Task.id == payload.entity_id).first()
    else:
        entity = db.query(Bug).filter(Bug.id == payload.entity_id).first()

    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{payload.entity_type.title()} not found")
    project_access.assert_project_access(db, user=current_user, project_id=entity.project_id)

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
