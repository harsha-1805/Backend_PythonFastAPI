from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TestCaseGenerateRequest(BaseModel):
    entity_type: Literal["task", "bug", "subtask"]
    entity_id: int


class TestCaseRegenerateRequest(BaseModel):
    entity_type: Literal["task", "bug", "subtask"]
    entity_id: int
    # User's feedback about what's wrong and what to improve/add.
    # e.g. "Add more edge cases for the password field" or
    # "The steps are too vague — be more specific about which button to click"
    feedback: str = Field(..., min_length=5, max_length=2000)


class TestCaseGenerateResponse(BaseModel):
    entity_type: Literal["task", "bug", "subtask"]
    entity_id: int
    entity_title: str
    count: int
    test_cases: list[dict] = Field(default_factory=list)
    # Pre-formatted CSV text — the frontend turns this straight into a
    # downloadable Blob, no separate authenticated download route needed.
    csv: str


class TestCaseSaveRequest(BaseModel):
    entity_type: Literal["task", "bug", "subtask"]
    entity_id: int
    entity_title: str
    test_cases: list[dict]
    csv: str
    project_id: int


class SavedTestCaseOut(BaseModel):
    id: int
    project_id: int
    task_id: Optional[int]
    bug_id: Optional[int]
    subtask_id: Optional[int] = None
    entity_type: str
    entity_title: str
    csv_data: str
    test_cases_json: str  # raw JSON string — frontend parses
    saved_by: Optional[int]
    saver_name: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
