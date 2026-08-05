"""
Pydantic schemas for Projects, Sprints, Tasks and Bugs (Phase 5).

Kept in their own file for the same reason admin_schema.py is separate:
one concern per file, re-exported from schemas/__init__.py so every
other import site keeps working unchanged.
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.admin_schema import RoleSummary  # noqa: F401 (kept importable together)


def _reject_past_date(value: Optional[date]) -> Optional[date]:
    """Shared guard used by every create/update schema below that carries
    a start/due date: creating (or moving) something to a date that's
    already in the past doesn't make sense for a start/due date — only
    `end_date`/"Completed" timestamps are allowed to look backwards, and
    those aren't validated here (a sprint/task can legitimately end
    "today"). Kept as a free function (not a class) so it can be reused
    across ProjectBase-less Sprint/Task/SubTask schemas without a mixin.
    """
    if value is not None and value < date.today():
        raise ValueError("This date can't be in the past")
    return value


class UserSummary(BaseModel):
    """Lightweight user shape embedded inside project/bug/task responses."""

    id: int
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
class ProjectBase(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    owner_id: Optional[int] = None
    # Team members to grant access to this project at creation time —
    # the owner is always added automatically even if omitted here. See
    # project_service.create_project / project_access.py.
    member_ids: List[int] = Field(default_factory=list)


class ProjectMemberOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddProjectMembersRequest(BaseModel):
    user_ids: List[int] = Field(min_length=1)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = None
    owner_id: Optional[int] = None


class ProjectOut(ProjectBase):
    id: int
    shortcode: Optional[str] = None
    owner: Optional[UserSummary] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProjectOut]


# ---------------------------------------------------------------------------
# Sprints
# ---------------------------------------------------------------------------
class SprintBase(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: str = Field(default="Planned")


class SprintCreate(SprintBase):
    project_id: int

    @field_validator("start_date")
    @classmethod
    def _start_not_past(cls, v):
        return _reject_past_date(v)

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date can't be before the start date")
        return self


class SprintUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None

    @field_validator("start_date")
    @classmethod
    def _start_not_past(cls, v):
        return _reject_past_date(v)

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date can't be before the start date")
        return self


class SprintOut(SprintBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SprintSummary(BaseModel):
    """Lightweight sprint shape embedded inside task/bug responses."""

    id: int
    name: str
    status: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
class TaskBase(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: Optional[str] = None
    # What must actually be true for this task to be considered done —
    # kept distinct from `description` so the AI test-case generator has
    # a clean "conditions to verify" signal instead of having to parse
    # criteria back out of a general description.
    acceptance_criteria: Optional[str] = None
    status: str = Field(default="To Do")
    due_date: Optional[date] = None


class TaskCreate(TaskBase):
    project_id: int
    # Sprint is mandatory when creating a task — per team lead's process:
    # Project -> Sprint -> Task -> SubTask. Every task must be scoped to
    # a sprint at creation time (no more "backlog" tasks with no sprint).
    sprint_id: int
    assigned_to: Optional[int] = None

    @field_validator("due_date")
    @classmethod
    def _due_not_past(cls, v):
        return _reject_past_date(v)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    sprint_id: Optional[int] = None
    assigned_to: Optional[int] = None

    @field_validator("due_date")
    @classmethod
    def _due_not_past(cls, v):
        return _reject_past_date(v)


class TaskAttachmentOut(BaseModel):
    id: int
    task_id: int
    image_url: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskOut(TaskBase):
    id: int
    custom_id: Optional[str] = None
    project_id: int
    sprint_id: Optional[int] = None
    sprint: Optional[SprintSummary] = None
    assignee: Optional[UserSummary] = None
    reporter: Optional[UserSummary] = None
    attachments: list[TaskAttachmentOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskSummary(BaseModel):
    """Lightweight task shape embedded inside bug responses."""

    id: int
    title: str
    status: str
    sprint_id: Optional[int] = None
    sprint: Optional[SprintSummary] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# SubTasks (nested under a Task — Project -> Sprint -> Task -> SubTask)
# ---------------------------------------------------------------------------
class SubTaskBase(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: Optional[str] = None
    status: str = Field(default="To Do")
    due_date: Optional[date] = None


class SubTaskCreate(SubTaskBase):
    task_id: int
    assigned_to: Optional[int] = None

    @field_validator("due_date")
    @classmethod
    def _due_not_past(cls, v):
        return _reject_past_date(v)


class SubTaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    assigned_to: Optional[int] = None

    @field_validator("due_date")
    @classmethod
    def _due_not_past(cls, v):
        return _reject_past_date(v)


class SubTaskOut(SubTaskBase):
    id: int
    custom_id: Optional[str] = None
    task_id: int
    assignee: Optional[UserSummary] = None
    reporter: Optional[UserSummary] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Bugs
# ---------------------------------------------------------------------------
class BugBase(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    severity: str = Field(default="Medium", description="Critical | High | Medium | Low")
    priority: str = Field(default="P2", description="P0 | P1 | P2 | P3")
    status: str = Field(default="Open", description="Open | In Progress | Resolved | Closed")
    summary: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    module: Optional[str] = None
    bug_type: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    possible_root_cause: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=100)
    steps_to_reproduce: List[str] = Field(default_factory=list)
    image_url: Optional[str] = Field(
        None, description="URL of the evidence screenshot, if one was attached"
    )


class BugCreate(BugBase):
    project_id: int
    sprint_id: Optional[int] = None
    task_id: Optional[int] = Field(
        None, description="Optional task to assign this (often AI-generated) bug to"
    )
    assigned_to: Optional[int] = None
    is_ai_generated: bool = False


class BugUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    severity: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    sprint_id: Optional[int] = None
    task_id: Optional[int] = None
    assigned_to: Optional[int] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    module: Optional[str] = None
    bug_type: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    possible_root_cause: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=100)
    steps_to_reproduce: Optional[List[str]] = None
    image_url: Optional[str] = None


class BugOut(BaseModel):
    id: int
    custom_id: Optional[str] = None
    project_id: int
    sprint_id: Optional[int] = None
    task_id: Optional[int] = None
    task: Optional[TaskSummary] = None
    title: str
    severity: str
    priority: str
    status: str
    summary: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    module: Optional[str] = None
    bug_type: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    possible_root_cause: Optional[str] = None
    confidence_score: Optional[float] = None
    steps_to_reproduce: List[str] = Field(default_factory=list)
    is_ai_generated: bool
    image_url: Optional[str] = None
    reporter: Optional[UserSummary] = None
    assignee: Optional[UserSummary] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BugListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[BugOut]
