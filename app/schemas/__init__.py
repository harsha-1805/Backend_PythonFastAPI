"""
Pydantic schemas (request/response contracts).

Kept separate from SQLAlchemy models on purpose: models describe the
database, schemas describe the API. This lets the API shape evolve
independently of the storage layer.

Phase 2 note: this file was converted from a single module (schemas.py)
into a package (schemas/) so the AI Bug Generator's schemas could live
in their own file (schemas/bug_schema.py) per the requested clean
architecture, WITHOUT changing any existing import elsewhere in the
app — `from app.schemas import LoginRequest` etc. still works exactly
as before because everything originally in schemas.py is still defined
right here in schemas/__init__.py.
"""
from datetime import datetime
from typing import List

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class RoleSummary(BaseModel):
    """Lightweight role shape embedded inside a user object (Phase 3)."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    role: RoleSummary | None = None
    roles: List[RoleSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenPayload(BaseModel):
    sub: str | None = None
    exp: int | None = None


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# AI Bug Generator (Phase 2) — re-exported so `from app.schemas import X`
# keeps working the same way it does for every schema above.
# ---------------------------------------------------------------------------
from app.schemas.bug_schema import (  # noqa: E402  (import at bottom is intentional)
    BugReportAI,
    GenerateBugRequestMeta,
    GenerateBugResponse,
)

# ---------------------------------------------------------------------------
# RBAC (Phase 3) + Admin User Management (Phase 4) — re-exported the same
# way bug_schema's classes are above.
# ---------------------------------------------------------------------------
from app.schemas.admin_schema import (  # noqa: E402
    AdminSetPasswordRequest,
    AdminUserListResponse,
    AdminUserOut,
    AdminUserUpdateRequest,
    AssignRoleRequest,
    AssignRolesRequest,
    ChangeOwnPasswordRequest,
    InviteUserRequest,
    InviteUserResponse,
    PermissionOut,
    RoleOut,
    UpdateOwnProfileRequest,
)

# ---------------------------------------------------------------------------
# Projects / Sprints / Tasks / Bugs (Phase 5) — re-exported the same way.
# ---------------------------------------------------------------------------
from app.schemas.project_schema import (  # noqa: E402
    AddProjectMembersRequest,
    BugCreate,
    BugListResponse,
    BugOut,
    BugUpdate,
    ProjectCreate,
    ProjectListResponse,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdate,
    SprintCreate,
    SprintOut,
    SprintSummary,
    SprintUpdate,
    SubTaskCreate,
    SubTaskOut,
    SubTaskUpdate,
    TaskCreate,
    TaskOut,
    TaskSummary,
    TaskUpdate,
    UserSummary,
)

from app.schemas.audit_schema import (  # noqa: E402
    AuditLogListResponse,
    AuditLogOut,
)

__all__ = [
    "UserBase",
    "UserCreate",
    "UserOut",
    "RoleSummary",
    "LoginRequest",
    "Token",
    "TokenPayload",
    "MessageResponse",
    "BugReportAI",
    "GenerateBugRequestMeta",
    "GenerateBugResponse",
    "RoleOut",
    "PermissionOut",
    "AdminUserOut",
    "AdminUserListResponse",
    "InviteUserRequest",
    "InviteUserResponse",
    "AdminUserUpdateRequest",
    "AssignRoleRequest",
    "AssignRolesRequest",
    "AdminSetPasswordRequest",
    "ChangeOwnPasswordRequest",
    "UpdateOwnProfileRequest",
    "UserSummary",
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectOut",
    "ProjectListResponse",
    "ProjectMemberOut",
    "AddProjectMembersRequest",
    "SprintCreate",
    "SprintUpdate",
    "SprintOut",
    "SprintSummary",
    "TaskCreate",
    "TaskUpdate",
    "TaskOut",
    "TaskSummary",
    "SubTaskCreate",
    "SubTaskUpdate",
    "SubTaskOut",
    "BugCreate",
    "BugUpdate",
    "BugOut",
    "BugListResponse",
    "AuditLogOut",
    "AuditLogListResponse",
]
