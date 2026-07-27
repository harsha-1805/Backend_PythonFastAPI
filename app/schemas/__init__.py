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

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

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

__all__ = [
    "UserBase",
    "UserCreate",
    "UserOut",
    "LoginRequest",
    "Token",
    "TokenPayload",
    "MessageResponse",
    "BugReportAI",
    "GenerateBugRequestMeta",
    "GenerateBugResponse",
]
