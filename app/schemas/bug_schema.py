"""
Pydantic schemas for the AI Bug Generator (Phase 2).

`BugReportAI` is the single source of truth for the structured JSON we
require Gemini to return. `response_parser.py` validates the raw model
output against this schema, so a malformed/incomplete LLM response
fails fast with a clear error instead of silently reaching the frontend.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class BugReportAI(BaseModel):
    """Structured bug report produced by the AI Bug Generator."""

    title: str = Field(..., description="Short, human-readable bug title")
    summary: str = Field(..., description="One or two sentence summary of the bug")
    description: str = Field(..., description="Detailed description of the issue")

    severity: str = Field(..., description="Critical | High | Medium | Low")
    priority: str = Field(..., description="P0 | P1 | P2 | P3")

    environment: Optional[str] = Field(None, description="OS / device / browser environment")
    module: Optional[str] = Field(None, description="Feature area or module affected")
    bug_type: Optional[str] = Field(None, description="UI, Functional, Performance, Crash, etc.")

    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    possible_root_cause: Optional[str] = None

    confidence_score: float = Field(
        ..., ge=0, le=100, description="Gemini's confidence (0-100) in this report"
    )

    steps_to_reproduce: List[str] = Field(default_factory=list)

    @field_validator("severity")
    @classmethod
    def _normalize_severity(cls, v: str) -> str:
        allowed = {"critical", "high", "medium", "low"}
        if v.strip().lower() not in allowed:
            # Don't reject — normalize to "Medium" so a slightly-off LLM
            # value never breaks the whole response. Confidence engine
            # can flag this via a follow-up question instead.
            return "Medium"
        return v.strip().capitalize()

    @field_validator("priority")
    @classmethod
    def _normalize_priority(cls, v: str) -> str:
        allowed = {"p0", "p1", "p2", "p3"}
        v_norm = v.strip().lower().replace(" ", "")
        if v_norm not in allowed:
            return "P2"
        return v_norm.upper()


class GenerateBugRequestMeta(BaseModel):
    """Non-file fields accepted alongside the multipart upload."""

    user_description: Optional[str] = None
    console_log: Optional[str] = None
    stack_trace: Optional[str] = None
    browser_url: Optional[str] = None


class GenerateBugResponse(BaseModel):
    """Top-level response returned by POST /api/v1/ai/generate-bug."""

    bug_report: BugReportAI
    low_confidence: bool = Field(
        ..., description="True if confidence_score fell below the configured threshold"
    )
    model_used: str
    image_url: Optional[str] = Field(
        None,
        description=(
            "Public URL of the screenshot that was uploaded, persisted to disk so it "
            "can be shown as a preview later (e.g. saved onto the Bug once created)."
        ),
    )