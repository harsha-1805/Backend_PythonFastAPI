"""
Project business logic (Phase 5), kept separate from the HTTP layer
exactly like admin_service.py / user_service.py are.

Phase 8 adds team membership: who a project is visible to / whose work
can be assigned within it. See app/services/project_access.py for the
access-check helpers; this module owns the actual membership rows.
"""
import logging

from sqlalchemy.orm import Session, joinedload

from app.models import Project, ProjectMember, User

logger = logging.getLogger(__name__)


def list_projects(
    db: Session,
    *,
    search: str | None = None,
    project_ids: set[int] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Project], int]:
    """`project_ids=None` means no restriction (Admin/Lead see everything);
    an empty/non-empty set restricts to exactly those projects — see
    project_access.accessible_project_ids, which routers pass straight
    through here.
    """
    query = db.query(Project).options(joinedload(Project.owner))
    if project_ids is not None:
        query = query.filter(Project.id.in_(project_ids))
    if search:
        query = query.filter(Project.name.ilike(f"%{search.strip()}%"))

    total = query.count()
    items = (
        query.order_by(Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_project(db: Session, *, project_id: int) -> Project | None:
    return (
        db.query(Project)
        .options(joinedload(Project.owner))
        .filter(Project.id == project_id)
        .first()
    )


def create_project(
    db: Session,
    *,
    name: str,
    description: str | None,
    owner_id: int | None,
    member_ids: list[int] | None = None,
) -> Project:
    """Creates the project and immediately seeds its team: the owner is
    always a member, plus whichever `member_ids` the creator (Admin/
    Lead) picked. This is the "assign the project to team members" step
    happening right at creation — members can still be added/removed
    later via add_project_members / remove_project_member.
    """
    project = Project(name=name, description=description, owner_id=owner_id)
    db.add(project)
    try:
        db.flush()  # get project.id without a full commit yet

        member_id_set = set(member_ids or [])
        if owner_id is not None:
            member_id_set.add(owner_id)

        if member_id_set:
            valid_user_ids = {
                u.id for u in db.query(User.id).filter(User.id.in_(member_id_set)).all()
            }
            for uid in member_id_set & valid_user_ids:
                db.add(ProjectMember(project_id=project.id, user_id=uid))

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create project %r", name)
        raise
    db.refresh(project)
    logger.info("Project #%s %r created (owner_id=%s, %s members)", project.id, name, owner_id, len(member_id_set))
    return project


def update_project(
    db: Session,
    *,
    project_id: int,
    name: str | None,
    description: str | None,
    owner_id: int | None,
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise LookupError("Project not found")

    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if owner_id is not None:
        project.owner_id = owner_id
        # The new owner is always a team member too, same as at creation.
        if not db.query(ProjectMember).filter_by(project_id=project_id, user_id=owner_id).first():
            db.add(ProjectMember(project_id=project_id, user_id=owner_id))

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update project #%s", project_id)
        raise
    db.refresh(project)
    return project


def delete_project(db: Session, *, project_id: int) -> None:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise LookupError("Project not found")

    try:
        db.delete(project)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete project #%s", project_id)
        raise
    logger.info("Project #%s deleted", project_id)


# ---------------------------------------------------------------------------
# Team membership
# ---------------------------------------------------------------------------
def list_project_members(db: Session, *, project_id: int) -> list[ProjectMember]:
    return (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.added_at.asc())
        .all()
    )


def add_project_members(db: Session, *, project_id: int, user_ids: list[int]) -> list[ProjectMember]:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise LookupError("Project not found")

    existing = {
        m.user_id
        for m in db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    }
    valid_user_ids = {u.id for u in db.query(User.id).filter(User.id.in_(user_ids)).all()}
    to_add = valid_user_ids - existing

    try:
        for uid in to_add:
            db.add(ProjectMember(project_id=project_id, user_id=uid))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to add members to project #%s", project_id)
        raise

    logger.info("Added %s member(s) to project #%s", len(to_add), project_id)
    return list_project_members(db, project_id=project_id)


def remove_project_member(db: Session, *, project_id: int, user_id: int) -> None:
    member = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
    )
    if member is None:
        raise LookupError("That user isn't a member of this project")

    try:
        db.delete(member)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to remove member %s from project #%s", user_id, project_id)
        raise
    logger.info("Removed member %s from project #%s", user_id, project_id)
