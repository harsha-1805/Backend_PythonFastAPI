"""
Authentication routes: signup, login, current-user, and self-service
profile/password management (Settings -> Profile).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import (
    ChangeOwnPasswordRequest,
    LoginRequest,
    MessageResponse,
    Token,
    UpdateOwnProfileRequest,
    UserCreate,
    UserOut,
)
from app.services import user_service

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = user_service.get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    try:
        user_service.create_user(db, user_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Account created successfully. You can now log in.")


@router.post("/login", response_model=Token)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = user_service.authenticate_user(db, credentials.email, credentials.password)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Contact your admin or HR.",
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.email)
    return Token(access_token=access_token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
def update_my_profile(
    payload: UpdateOwnProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Settings -> Profile: the logged-in user editing their own
    name/email. Anyone can do this for themselves — no special
    permission needed beyond being logged in.
    """
    try:
        user = user_service.update_own_profile(
            db, user=current_user, full_name=payload.full_name, email=payload.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UserOut.model_validate(user)


@router.patch("/me/password", response_model=MessageResponse)
def change_my_password(
    payload: ChangeOwnPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Settings -> Profile: self-service password change. Requires the
    current password (unlike the admin/HR reset endpoint at
    PATCH /api/v1/admin/users/{id}/password, which doesn't).
    """
    try:
        user_service.change_own_password(
            db,
            user=current_user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Password changed successfully")
