"""Task business logic (Phase 5 + Phase 8 project-team-scoped assignment)."""
import logging

from sqlalchemy.orm import Session, joinedload

from app.models import Project, Sprint, Task
from app.services import project_access

logger = logging.getLogger(__name__)


def list_tasks(
    db: Session,
    *,
    project_id: int | None = None,
    assigned_to: int | None = None,
    sprint_id: int | None = None,
    project_ids: set[int] | None = None,
) -> list[Task]:
    query = db.query(Task).options(
        joinedload(Task.assignee), joinedload(Task.reporter), joinedload(Task.sprint)
    )
    if project_ids is not None:
        query = query.filter(Task.project_id.in_(project_ids))
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if assigned_to is not None:
        query = query.filter(Task.assigned_to == assigned_to)
    if sprint_id is not None:
        query = query.filter(Task.sprint_id == sprint_id)
    return query.order_by(Task.created_at.desc()).all()


def get_task(db: Session, *, task_id: int) -> Task | None:
    return (
        db.query(Task)
        .options(joinedload(Task.assignee), joinedload(Task.reporter), joinedload(Task.sprint))
        .filter(Task.id == task_id)
        .first()
    )


def create_task(
    db: Session,
    *,
    project_id: int,
    title: str,
    description: str | None,
    status: str,
    due_date,
    assigned_to: int | None,
    sprint_id: int | None,
    reported_by: int | None,
) -> Task:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise ValueError("That project does not exist")

    if sprint_id is not None:
        sprint = db.query(Sprint).filter(Sprint.id == sprint_id).first()
        if sprint is None:
            raise ValueError("That sprint does not exist")
        if sprint.project_id != project_id:
            raise ValueError("That sprint does not belong to this project")

    # A task can only be assigned to someone on this project's team (or
    # Admin/Lead) — see project_access.assert_valid_assignee.
    project_access.assert_valid_assignee(db, project_id=project_id, assignee_id=assigned_to)

    task = Task(
        project_id=project_id,
        title=title,
        description=description,
        status=status,
        due_date=due_date,
        assigned_to=assigned_to,
        sprint_id=sprint_id,
        reported_by=reported_by,
    )
    db.add(task)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create task %r on project #%s", title, project_id)
        raise
    db.refresh(task)
    logger.info("Task #%s %r created on project #%s", task.id, title, project_id)
    return task


def update_task(db: Session, *, task_id: int, **fields) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise LookupError("Task not found")

    if "assigned_to" in fields and fields["assigned_to"] is not None:
        project_access.assert_valid_assignee(
            db, project_id=task.project_id, assignee_id=fields["assigned_to"]
        )

    for key, value in fields.items():
        if value is not None:
            setattr(task, key, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update task #%s", task_id)
        raise
    db.refresh(task)
    return task


def delete_task(db: Session, *, task_id: int) -> None:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise LookupError("Task not found")

    try:
        db.delete(task)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete task #%s", task_id)
        raise
    logger.info("Task #%s deleted", task_id)
