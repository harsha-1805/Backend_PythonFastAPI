"""
User-related business logic, kept separate from the HTTP layer (routers)
so it can be reused or unit-tested independently of FastAPI.
"""
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.models import User
from app.schemas import UserCreate
from app.services.email_validator import validate_email_domain
from app.services.role_service import DEFAULT_SIGNUP_ROLE, get_role_by_name, set_user_roles


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, user_in: UserCreate) -> User:
    """Create a user via public self-signup.

    RBAC bootstrap rule (Phase 3): the very first account ever created in
    the system becomes "Admin" (so there's always at least one admin who
    can manage everyone else). Every signup after that gets the default,
    lowest-privilege role instead. Roles can be changed later by an Admin
    via the admin User Management screen (Phase 4). Role assignment goes
    through the `user_roles` join table (a user can hold more than one
    role), not a single column on `users`.
    """
    validate_email_domain(user_in.email)

    is_first_user = db.query(User).count() == 0
    role_name = "Admin" if is_first_user else DEFAULT_SIGNUP_ROLE
    role = get_role_by_name(db, role_name)

    user = User(
        full_name=user_in.full_name,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if role is not None:
        set_user_roles(db, user=user, role_ids=[role.id])

    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        raise PermissionError("This account has been deactivated")
    return user


def update_own_profile(
    db: Session, *, user: User, full_name: str | None, email: str | None
) -> User:
    """Self-service profile edit (Settings page): the logged-in user
    changing their own name/email. Kept separate from
    admin_service.update_user (an admin/HR editing *someone else's*
    profile) even though the logic is nearly identical, because the two
    are gated by different permissions and it's clearer for each caller
    to have its own entry point than to thread an `is_self` flag through
    the shared one.
    """
    if email and email != user.email:
        validate_email_domain(email)
        if db.query(User).filter(User.email == email, User.id != user.id).first():
            raise ValueError("Another account already uses this email")
        user.email = email

    if full_name:
        user.full_name = full_name.strip()

    db.commit()
    db.refresh(user)
    return user


def change_own_password(
    db: Session, *, user: User, current_password: str, new_password: str
) -> User:
    """Self-service password change (Settings page). Requires the
    current password so a stolen/left-open session can't silently take
    over the account by just changing the password.
    """
    if not verify_password(current_password, user.hashed_password):
        raise ValueError("Current password is incorrect")
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters")
    if verify_password(new_password, user.hashed_password):
        raise ValueError("New password must be different from your current password")

    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    return user
