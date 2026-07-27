"""
AI Bug Generator routes.

Reuses the exact same auth dependency (`get_current_user`) every other
protected route uses — no new auth logic. Route stays thin: it only
validates the incoming multipart request shape and delegates all real
work to `services/bug/bug_generator.py`.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.dependencies import get_current_user
from app.models import User
from app.schemas.bug_schema import GenerateBugResponse
from app.services.bug.bug_generator import generate_bug_report
from app.services.evidence.evidence_merger import merge_evidence

router = APIRouter(prefix="/api/v1/ai", tags=["AI Bug Generator"])


@router.post(
    "/generate-bug",
    response_model=GenerateBugResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_bug(
    image: UploadFile = File(..., description="Required screenshot of the bug"),
    user_description: Optional[str] = Form(None),
    console_log: Optional[str] = Form(None),
    stack_trace: Optional[str] = Form(None),
    browser_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 — auth gate, reused as-is
):
    image_bytes = await image.read()

    evidence = merge_evidence(
        image=image,
        image_bytes=image_bytes,
        console_log=console_log,
        stack_trace=stack_trace,
        user_description=user_description,
        browser_url=browser_url,
    )

    return generate_bug_report(evidence)
