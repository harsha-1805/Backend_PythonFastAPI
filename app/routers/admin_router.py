"""
Admin routes: user management (Phase 4).

Every route here is gated by `require_permission(...)`, not just
`get_current_user` — only roles that were granted the relevant
permission in role_service.ROLE_PERMISSIONS (Owner always has every
permission) can call these.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models import User
from app.schemas import (
    AdminSetPasswordRequest,
    AdminUserListResponse,
    AdminUserOut,
    AdminUserUpdateRequest,
    AssignRoleRequest,
    AssignRolesRequest,
    InviteUserRequest,
    InviteUserResponse,
    MessageResponse,
)
from app.services import admin_service

router = APIRouter(prefix="/api/v1/admin/users", tags=["Admin - User Management"])


@router.get("", response_model=AdminUserListResponse)
def list_users(
    search: str | None = Query(None, description="Search by name or email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.view")),
):
    items, total = admin_service.list_users(db, search=search, page=page, page_size=page_size)
    return AdminUserListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[AdminUserOut.model_validate(u) for u in items],
    )


@router.get("/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.view")),
):
    user = admin_service.get_user(db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserOut.model_validate(user)


@router.post("/invite", response_model=InviteUserResponse, status_code=status.HTTP_201_CREATED)
def invite_user(
    payload: InviteUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.invite")),
):
    try:
        user, temp_password = admin_service.invite_user(
            db,
            full_name=payload.full_name,
            email=payload.email,
            role_id=payload.role_id,
            invited_by=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return InviteUserResponse(
        user=AdminUserOut.model_validate(user),
        temporary_password=temp_password,
    )


@router.patch("/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.edit")),
):
    try:
        user = admin_service.update_user(
            db, user_id=user_id, full_name=payload.full_name, email=payload.email
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AdminUserOut.model_validate(user)


@router.patch("/{user_id}/deactivate", response_model=AdminUserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.deactivate")),
):
    try:
        user = admin_service.set_user_active(
            db, user_id=user_id, is_active=False, acting_user=current_user
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AdminUserOut.model_validate(user)


@router.patch("/{user_id}/activate", response_model=AdminUserOut)
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.deactivate")),
):
    try:
        user = admin_service.set_user_active(
            db, user_id=user_id, is_active=True, acting_user=current_user
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return AdminUserOut.model_validate(user)


@router.patch("/{user_id}/role", response_model=AdminUserOut)
def assign_role(
    user_id: int,
    payload: AssignRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.assign_role")),
):
    try:
        user = admin_service.assign_role(
            db, user_id=user_id, role_id=payload.role_id, acting_user=current_user
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AdminUserOut.model_validate(user)


@router.patch("/{user_id}/roles", response_model=AdminUserOut)
def assign_roles(
    user_id: int,
    payload: AssignRolesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.assign_role")),
):
    """Multi-select role assignment: replaces the user's roles with the
    full `role_ids` list in one call (a user can hold several roles at
    once). Kept alongside the single-role `/role` endpoint above for
    backward compatibility with any existing callers."""
    try:
        user = admin_service.assign_roles(
            db, user_id=user_id, role_ids=payload.role_ids, acting_user=current_user
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AdminUserOut.model_validate(user)


@router.patch("/{user_id}/password", response_model=MessageResponse)
def reset_user_password(
    user_id: int,
    payload: AdminSetPasswordRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("users.reset_password")),
):
    """Admin/HR resets another user's password directly — e.g. when
    someone's locked out. The user is flagged `must_change_password` so
    the frontend can prompt them to pick their own on next login.
    """
    try:
        admin_service.admin_set_password(db, user_id=user_id, new_password=payload.new_password)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return MessageResponse(message="Password reset successfully")


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.delete")),
):
    try:
        admin_service.delete_user(db, user_id=user_id, acting_user=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return MessageResponse(message="User deleted successfully")
