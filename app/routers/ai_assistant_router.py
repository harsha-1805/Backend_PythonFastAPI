"""AI Assistant route — see ai_assistant_service.py for the "basic for
now" design note and the project-membership scoping fix.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.schemas.ai_assistant_schema import AIAssistantQueryRequest, AIAssistantQueryResponse
from app.services import ai_assistant_service, project_access

router = APIRouter(prefix="/api/v1/ai-assistant", tags=["AI Assistant"])


@router.post("/query", response_model=AIAssistantQueryResponse)
def query_assistant(
    payload: AIAssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai_assistant.use")),
):
    if payload.project_id is not None:
        # Raises PermissionError -> 403 via the app-wide handler if the
        # caller isn't Admin/Lead or a member of that project's team.
        project_access.assert_project_access(db, user=current_user, project_id=payload.project_id)

    result = ai_assistant_service.answer_query(
        db,
        message=payload.message,
        project_id=payload.project_id,
        current_user=current_user,
        module=payload.module,
    )
    return AIAssistantQueryResponse(**result)
