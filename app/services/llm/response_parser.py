"""
Response parser.

Turns Gemini's raw text response into a validated `BugReportAI`. Kept
separate from gemini_client.py so parsing/validation logic is testable
without making a real API call, and reusable for any future LLM whose
raw output also needs JSON-extraction + schema validation.
"""
from __future__ import annotations

import json
import re

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.schemas.bug_schema import BugReportAI

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def parse_bug_report(raw_text: str) -> BugReportAI:
    cleaned = _strip_code_fences(raw_text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not parse Gemini's response as JSON: {exc}",
        ) from exc

    try:
        return BugReportAI.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini's response did not match the expected bug report schema: {exc}",
        ) from exc
