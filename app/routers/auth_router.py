"""
Authentication routes: signup, login, current-user.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginRequest, MessageResponse, Token, UserCreate, UserOut
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

    user_service.create_user(db, user_in)
    return MessageResponse(message="Account created successfully. You can now log in.")


@router.post("/login", response_model=Token)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    user = user_service.authenticate_user(db, credentials.email, credentials.password)
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
