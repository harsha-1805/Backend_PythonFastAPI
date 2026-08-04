"""Sprint business logic (Phase 5)."""
import logging

from sqlalchemy.orm import Session

from app.models import Project, Sprint

logger = logging.getLogger(__name__)


def list_sprints(
    db: Session, *, project_id: int | None = None, project_ids: set[int] | None = None
) -> list[Sprint]:
    query = db.query(Sprint)
    if project_ids is not None:
        query = query.filter(Sprint.project_id.in_(project_ids))
    if project_id is not None:
        query = query.filter(Sprint.project_id == project_id)
    return query.order_by(Sprint.created_at.desc()).all()


def get_sprint(db: Session, *, sprint_id: int) -> Sprint | None:
    return db.query(Sprint).filter(Sprint.id == sprint_id).first()


def create_sprint(
    db: Session,
    *,
    project_id: int,
    name: str,
    start_date,
    end_date,
    status: str,
) -> Sprint:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise ValueError("That project does not exist")

    sprint = Sprint(
        project_id=project_id, name=name, start_date=start_date, end_date=end_date, status=status
    )
    db.add(sprint)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create sprint %r on project #%s", name, project_id)
        raise
    db.refresh(sprint)
    logger.info("Sprint #%s %r created on project #%s", sprint.id, name, project_id)
    return sprint


def update_sprint(db: Session, *, sprint_id: int, **fields) -> Sprint:
    sprint = db.query(Sprint).filter(Sprint.id == sprint_id).first()
    if sprint is None:
        raise LookupError("Sprint not found")

    for key, value in fields.items():
        if value is not None:
            setattr(sprint, key, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update sprint #%s", sprint_id)
        raise
    db.refresh(sprint)
    return sprint


def delete_sprint(db: Session, *, sprint_id: int) -> None:
    sprint = db.query(Sprint).filter(Sprint.id == sprint_id).first()
    if sprint is None:
        raise LookupError("Sprint not found")

    try:
        db.delete(sprint)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete sprint #%s", sprint_id)
        raise
    logger.info("Sprint #%s deleted", sprint_id)
