from typing import Literal

from pydantic import BaseModel, Field


class TestCaseGenerateRequest(BaseModel):
    entity_type: Literal["task", "bug"]
    entity_id: int


class TestCaseGenerateResponse(BaseModel):
    entity_type: Literal["task", "bug"]
    entity_id: int
    entity_title: str
    count: int
    test_cases: list[dict] = Field(default_factory=list)
    # Pre-formatted CSV text — the frontend turns this straight into a
    # downloadable Blob, no separate authenticated download route needed.
    csv: str
