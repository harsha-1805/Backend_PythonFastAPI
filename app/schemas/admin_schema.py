"""
Pydantic schemas for RBAC (Phase 3) and admin User Management (Phase 4).

Kept in their own file for the same reason bug_schema.py is separate:
one concern per file, re-exported from schemas/__init__.py so every
other import site keeps working unchanged.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Roles & permissions (Phase 3)
# ---------------------------------------------------------------------------
class PermissionOut(BaseModel):
    id: int
    code: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_system: bool
    permissions: List[PermissionOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RoleSummary(BaseModel):
    """Lightweight role shape embedded inside a user object."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Admin — user management (Phase 4)
# ---------------------------------------------------------------------------
class AdminUserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool
    role: Optional[RoleSummary] = None
    roles: List[RoleSummary] = Field(default_factory=list)
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AdminUserOut]


class InviteUserRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role_id: Optional[int] = Field(
        None, description="Role to assign immediately. Defaults to the lowest-privilege role."
    )


class InviteUserResponse(BaseModel):
    user: AdminUserOut
    temporary_password: str = Field(
        ..., description="Shown once. The invited user must change it on first login."
    )


class AdminUserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None


class AssignRoleRequest(BaseModel):
    role_id: int


class AssignRolesRequest(BaseModel):
    """Multi-role assignment: replaces a user's roles with this full set."""

    role_ids: List[int] = Field(default_factory=list)


class AdminSetPasswordRequest(BaseModel):
    """Admin/HR resetting another user's password directly (Settings ->
    User Management "Reset password" action). No current-password check
    needed — the acting user's own permission (`users.reset_password`)
    is the gate here, enforced at the route level.
    """

    new_password: str = Field(min_length=8, max_length=128)


class ChangeOwnPasswordRequest(BaseModel):
    """Self-service password change (Settings -> Profile). Requires the
    current password so a hijacked/left-open session can't take over the
    account just by changing the password.
    """

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UpdateOwnProfileRequest(BaseModel):
    """Self-service profile edit (Settings -> Profile): name/email only.
    Role/permissions can't be self-edited here — that stays admin/HR-only
    via AssignRolesRequest above.
    """

    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None


class MessageResponse(BaseModel):
    message: str
