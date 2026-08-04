"""
Reusable FastAPI dependencies.

`get_current_user` is the single choke point every protected route
depends on. Future routers (projects, bugs, tasks, ...) reuse this same
dependency instead of re-implementing token parsing.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.database import get_db
from app.models import User
from app.services.role_service import user_has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    email: str | None = payload.get("sub")
    if email is None:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return user


def require_permission(permission_code: str):
    """Dependency factory: `Depends(require_permission("users.invite"))`.

    Every RBAC-gated route (admin router, and later project/bug routers)
    reuses this instead of re-implementing a role check. Keeping the
    check as a single function (`user_has_permission`) means role<->
    permission logic only has to be right in one place.
    """

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        if not user_has_permission(current_user, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You don't have permission to perform this action ({permission_code}).",
            )
        return current_user

    return _checker
