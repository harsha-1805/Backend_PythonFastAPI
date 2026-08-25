"""
Admin user-management business logic (Phase 4).

Kept separate from the HTTP layer (admin_router.py) exactly like
user_service.py is for auth — routers stay thin, this stays testable
without FastAPI in the loop.

Note on "invite": there's no email/SMTP configured yet, so "inviting" a
user creates their account immediately with a random temporary password
and returns that password once in the API response for the admin to
share with them out-of-band. `must_change_password` is set so the
frontend can prompt them to change it after their first login (the
password-change endpoint itself is a good Phase 2.5/5 follow-up once
you want it — not wired up yet to keep this change focused).
"""
import secrets
import string

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Role, User
from app.services.email_validator import validate_email_domain
from app.services.role_service import DEFAULT_SIGNUP_ROLE, get_role_by_name, set_user_roles


def _generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def list_users(
    db: Session,
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[User], int]:
    query = db.query(User)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter((User.full_name.ilike(like)) | (User.email.ilike(like)))

    total = query.count()
    items = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_user(db: Session, *, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def invite_user(
    db: Session, *, full_name: str, email: str, role_id: int | None, invited_by: User
) -> tuple[User, str]:
    validate_email_domain(email)

    if db.query(User).filter(User.email == email).first():
        raise ValueError("An account with this email already exists")

    role: Role | None
    if role_id is not None:
        role = db.query(Role).filter(Role.id == role_id).first()
        if role is None:
            raise ValueError("That role does not exist")
    else:
        role = get_role_by_name(db, DEFAULT_SIGNUP_ROLE)

    temp_password = _generate_temp_password()
    user = User(
        full_name=full_name,
        email=email,
        hashed_password=hash_password(temp_password),
        invited_by_id=invited_by.id,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if role is not None:
        set_user_roles(db, user=user, role_ids=[role.id])

    return user, temp_password


def update_user(db: Session, *, user_id: int, full_name: str | None, email: str | None) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise LookupError("User not found")

    if email and email != user.email:
        validate_email_domain(email)
        if db.query(User).filter(User.email == email, User.id != user_id).first():
            raise ValueError("Another account already uses this email")
        user.email = email

    if full_name:
        user.full_name = full_name

    db.commit()
    db.refresh(user)
    return user


def set_user_active(db: Session, *, user_id: int, is_active: bool, acting_user: User) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise LookupError("User not found")
    if user.id == acting_user.id and not is_active:
        raise ValueError("You can't deactivate your own account")

    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, *, user_id: int, acting_user: User) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise LookupError("User not found")
    if user.id == acting_user.id:
        raise ValueError("You can't delete your own account")

    db.delete(user)
    db.commit()


def assign_role(db: Session, *, user_id: int, role_id: int, acting_user: User) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise LookupError("User not found")

    role = db.query(Role).filter(Role.id == role_id).first()
    if role is None:
        raise ValueError("That role does not exist")

    acting_user_is_admin = any(r.name == "Admin" for r in acting_user.roles)
    if user.id == acting_user.id and acting_user_is_admin and role.name != "Admin":
        raise ValueError("You can't demote yourself away from Admin")

    set_user_roles(db, user=user, role_ids=[role.id])
    return user


def assign_roles(db: Session, *, user_id: int, role_ids: list[int], acting_user: User) -> User:
    """Multi-select version of assign_role: replaces a user's full set of
    roles with `role_ids` (a user can hold more than one role at once,
    per the `user_roles` join table)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise LookupError("User not found")

    if not role_ids:
        raise ValueError("Select at least one role")

    unique_role_ids = list(dict.fromkeys(role_ids))  # de-dupe, keep order
    roles = db.query(Role).filter(Role.id.in_(unique_role_ids)).all()
    if len(roles) != len(unique_role_ids):
        raise ValueError("One or more selected roles do not exist")

    role_names = {r.name for r in roles}
    # Guards against the one scenario this check exists for: an Admin
    # removing their own Admin role (which could leave the system with
    # no Admin at all). It must only fire when the acting user currently
    # HAS Admin and is about to lose it — not for any user touching
    # their own roles. The old check fired for anyone editing their own
    # roles (e.g. an HR user, who never had Admin to begin with), which
    # made every self role-change fail with a nonsensical "demote
    # yourself away from Admin" error.
    acting_user_is_admin = any(r.name == "Admin" for r in acting_user.roles)
    if user.id == acting_user.id and acting_user_is_admin and "Admin" not in role_names:
        raise ValueError("You can't demote yourself away from Admin")

    set_user_roles(db, user=user, role_ids=unique_role_ids)
    return user


def admin_set_password(db: Session, *, user_id: int, new_password: str) -> User:
    """Admin/HR resets another user's password directly (no knowledge of
    their current password needed — that's the point of this endpoint
    vs. the self-service change_own_password in user_service.py). The
    user is flagged `must_change_password` so the frontend can prompt
    them to pick their own password after logging in.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise LookupError("User not found")

    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters")

    user.hashed_password = hash_password(new_password)
    user.must_change_password = True
    db.commit()
    db.refresh(user)
    return user
