"""
RBAC business logic (Phase 3, revised for module-based permissions).

This module owns:
  1. The full catalog of permission codes, one group per app module
     (Dashboard, Projects, AI Bug Generator, Bugs, Tasks, Sprints,
     Releases, Reports, AI Assistant, Settings, User Management).
  2. The default roles (Admin, Lead, HR, QA, Employee) and which
     permissions each one gets, seeded once (idempotently) at startup
     via `seed_roles_and_permissions`.
  3. `user_has_permission` — the single place that decides whether a
     given user's role grants a given permission code. Everything else
     (the `require_permission` FastAPI dependency, every router) goes
     through this function instead of re-implementing the check.

Adding a new permission later = add one line to PERMISSIONS and one
line to whichever ROLE_PERMISSIONS entry should get it. No migration
needed for the permission catalog itself; only role<->permission
*assignments* live in the database (role_permissions table) so they can
be changed at runtime later via an admin "manage roles" screen without
a code deploy.
"""
from sqlalchemy.orm import Session

from app.models import Permission, Role, User, UserRole

# ---------------------------------------------------------------------------
# Permission catalog — one block per module shown in the sidebar.
# Format: code -> human description. Namespaced as "<module>.<action>".
# ---------------------------------------------------------------------------
PERMISSIONS: dict[str, str] = {
    # Dashboard
    "dashboard.view": "View the dashboard / home overview",

    # Projects
    "projects.view": "View projects",
    "projects.create": "Create new projects",
    "projects.edit": "Edit project details",
    "projects.delete": "Delete projects",

    # AI Bug Generator
    "ai_bug_generator.use": "Generate bug reports from screenshots/logs using AI",

    # Bugs
    "bugs.view": "View bugs",
    "bugs.create": "Report/create bugs",
    "bugs.edit": "Edit bug details (status, severity, assignment, etc.)",
    "bugs.delete": "Delete bugs",
    "bugs.assign": "Assign bugs to a team member",

    # Tasks
    "tasks.view": "View tasks",
    "tasks.create": "Create tasks",
    "tasks.edit": "Edit tasks (status, details)",
    "tasks.delete": "Delete tasks",
    "tasks.assign": "Assign tasks to a team member",

    # Sprints
    "sprints.view": "View sprints",
    "sprints.create": "Create sprints",
    "sprints.edit": "Edit sprint details",
    "sprints.delete": "Delete sprints",

    # SubTasks (nested under Tasks)
    "subtasks.view": "View subtasks",
    "subtasks.create": "Create subtasks",
    "subtasks.edit": "Edit subtasks (status, details)",
    "subtasks.delete": "Delete subtasks",

    # Releases
    "releases.view": "View releases",
    "releases.manage": "Create/edit/delete releases",

    # Reports
    "reports.view": "View analytics & reports",

    # AI Assistant
    "ai_assistant.use": "Use the AI Assistant (chat / Q&A over project data)",

    # Settings
    "settings.view": "View workspace settings",
    "settings.manage": "Change workspace settings",

    # User Management
    "users.view": "View the list of users and their profiles",
    "users.invite": "Invite new users to the workspace",
    "users.edit": "Edit another user's name/email",
    "users.deactivate": "Activate or deactivate a user account",
    "users.delete": "Permanently delete a user account",
    "users.assign_role": "Change a user's global role",
    "users.reset_password": "Reset another user's password",
    "roles.view": "View available roles and their permissions",

    # Audit Log
    "audit.view": "View the audit trail of who did what, and when",
}

# Default roles, in the order they should be created. "Admin" always gets
# every permission in PERMISSIONS (see seed function) so it never needs to
# be listed explicitly and can't accidentally fall out of sync.
DEFAULT_ROLES: dict[str, str] = {
    "Admin": "Full access to every module in the workspace.",
    "Lead": "Manages projects, sprints, tasks and bugs for their team.",
    "HR": "Manages users/onboarding; read-only on delivery modules.",
    "QA": "Reports, triages and verifies bugs; runs the AI Bug Generator.",
    "Employee": "Works on assigned tasks and bugs day to day.",
}

# Which non-Admin roles get which permissions. Admin is intentionally
# omitted here — it's granted the full PERMISSIONS set in the seed function.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Lead": [
        "dashboard.view",
        "projects.view", "projects.create", "projects.edit", "projects.delete",
        "ai_bug_generator.use",
        "bugs.view", "bugs.create", "bugs.edit", "bugs.delete", "bugs.assign",
        "tasks.view", "tasks.create", "tasks.edit", "tasks.delete", "tasks.assign",
        "subtasks.view", "subtasks.create", "subtasks.edit", "subtasks.delete",
        "sprints.view", "sprints.create", "sprints.edit", "sprints.delete",
        "releases.view", "releases.manage",
        "reports.view",
        "ai_assistant.use",
        "settings.view",
        "users.view",
        "roles.view",
        "audit.view",
    ],
    "HR": [
        "dashboard.view",
        "projects.view", "projects.create",
        "bugs.view", "bugs.create",
        "reports.view",
        "ai_assistant.use",
        "settings.view",
        "users.view", "users.invite", "users.edit", "users.deactivate",
        "users.assign_role", "users.reset_password",
        "roles.view",
    ],
    "QA": [
        "dashboard.view",
        "projects.view",
        "ai_bug_generator.use",
        "bugs.view", "bugs.create", "bugs.edit", "bugs.assign",
        "tasks.view", "tasks.edit",
        "subtasks.view", "subtasks.edit",
        "sprints.view",
        "releases.view",
        "reports.view",
        "ai_assistant.use",
        "audit.view",
    ],
    "Employee": [
        "dashboard.view",
        "projects.view",
        "ai_bug_generator.use",
        "bugs.view", "bugs.create",
        "tasks.view", "tasks.edit",
        "subtasks.view", "subtasks.edit",
        "sprints.view",
        "releases.view",
        "ai_assistant.use",
    ],
}

# The role newly self-registered (public /signup) users receive once an
# Admin already exists. The very first user in the whole system instead
# becomes "Admin" automatically — see user_service.create_user.
DEFAULT_SIGNUP_ROLE = "Employee"


def seed_roles_and_permissions(db: Session) -> None:
    """Idempotently ensure every permission/role/mapping above exists.

    Safe to call on every app startup: existing rows are left untouched,
    only missing ones are inserted. Role<->permission assignments are
    re-synced every startup so editing ROLE_PERMISSIONS above and
    restarting the app is enough to change what a role can do.
    """
    # 1. Permissions
    existing_perm_codes = {p.code for p in db.query(Permission).all()}
    for code, description in PERMISSIONS.items():
        if code not in existing_perm_codes:
            db.add(Permission(code=code, description=description))
    db.commit()

    all_permissions = {p.code: p for p in db.query(Permission).all()}

    # 2. Roles
    existing_role_names = {r.name for r in db.query(Role).all()}
    for name, description in DEFAULT_ROLES.items():
        if name not in existing_role_names:
            db.add(Role(name=name, description=description, is_system=True))
    db.commit()

    roles_by_name = {r.name: r for r in db.query(Role).all()}

    # 3. Role -> permission mappings
    admin_role = roles_by_name.get("Admin")
    if admin_role is not None:
        admin_role.permissions = list(all_permissions.values())

    for role_name, codes in ROLE_PERMISSIONS.items():
        role = roles_by_name.get(role_name)
        if role is None:
            continue
        role.permissions = [all_permissions[c] for c in codes if c in all_permissions]

    db.commit()


def get_role_by_name(db: Session, name: str) -> Role | None:
    return db.query(Role).filter(Role.name == name).first()


def set_user_roles(db: Session, *, user: User, role_ids: list[int]) -> User:
    """Replace a user's role assignments with exactly `role_ids`.

    Writes to the `user_roles` join table (adds/removes UserRole rows)
    rather than touching a single `role_id` column, since a user can now
    hold more than one role at once per the ER diagram. The admin "assign
    role" UI currently sends a single role_id, so in practice this call
    clears any existing roles and assigns just that one — but the table
    itself supports a user holding several roles simultaneously, e.g. via
    a future "add role" endpoint that appends instead of replacing.
    """
    db.query(UserRole).filter(UserRole.user_id == user.id).delete()
    for role_id in role_ids:
        db.add(UserRole(user_id=user.id, role_id=role_id))
    db.commit()
    db.refresh(user)
    return user


def user_has_permission(user: User, permission_code: str) -> bool:
    if user is None:
        return False
    return any(permission_code == p.code for role in user.roles for p in role.permissions)


def user_has_any_role(user: User, *role_names: str) -> bool:
    if user is None:
        return False
    return any(role.name in role_names for role in user.roles)