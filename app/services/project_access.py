"""
Project team-membership access control.

Single source of truth for two closely related rules, used by every
router that touches Projects/Sprints/Tasks/SubTasks/Bugs:

  1. "Can this user see/use this project at all?" — Admin and Lead
     always can (they manage projects org-wide); everyone else only if
     they're a member of that specific project's team.
  2. "Can this user be assigned this task/bug/subtask?" — the assignee
     must be a member of the project's team (or Admin/Lead, who can
     always be assigned work directly).

Kept as one small module (not duplicated per-router) so the membership
rule can't drift between Tasks/Bugs/SubTasks — exactly the same
reasoning as role_service.user_has_permission being the one place
permission checks go through.
"""
from sqlalchemy.orm import Session

from app.models import Project, ProjectMember, User

# Admin manages everything org-wide; Lead is the "Project Manager" role
# and also isn't scoped to a single project's team list.
ELEVATED_ROLES = {"Admin", "Lead"}


def role_names(user: User) -> set[str]:
    return {r.name for r in user.roles}


def has_elevated_access(user: User) -> bool:
    return bool(role_names(user) & ELEVATED_ROLES)


def is_project_member(db: Session, *, project_id: int, user_id: int) -> bool:
    return (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
        is not None
    )


def assert_project_access(db: Session, *, user: User, project_id: int) -> None:
    """Raises PermissionError if `user` shouldn't be able to see/use this
    project. Routers catch PermissionError the same way they already
    catch ValueError/LookupError, translating it to HTTP 403.
    """
    if has_elevated_access(user):
        return
    if not is_project_member(db, project_id=project_id, user_id=user.id):
        raise PermissionError(
            "You're not a member of this project's team, so you don't have access to it."
        )


def assert_valid_assignee(db: Session, *, project_id: int, assignee_id: int | None) -> None:
    """Raises ValueError if `assignee_id` isn't allowed to be assigned
    work on this project — i.e. isn't a team member and isn't
    Admin/Lead. None (unassigned) always passes.
    """
    if assignee_id is None:
        return

    assignee = db.query(User).filter(User.id == assignee_id).first()
    if assignee is None:
        raise ValueError("That user doesn't exist")

    if has_elevated_access(assignee):
        return
    if not is_project_member(db, project_id=project_id, user_id=assignee_id):
        raise ValueError(
            f"{assignee.full_name} isn't a member of this project's team — "
            "add them to the project first, or assign someone who's already on the team."
        )


def accessible_project_ids(db: Session, *, user: User) -> set[int] | None:
    """Returns None to mean "no restriction, see every project"
    (Admin/Lead), otherwise the set of project IDs this user is a
    member of. Callers do:
        ids = accessible_project_ids(db, user=current_user)
        if ids is not None:
            query = query.filter(Model.project_id.in_(ids))
    """
    if has_elevated_access(user):
        return None
    rows = db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id).all()
    return {r[0] for r in rows}
