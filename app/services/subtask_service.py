"""SubTask business logic — nested under a Task (Project -> Sprint -> Task -> SubTask)."""
import logging

from sqlalchemy.orm import Session, joinedload

from app.models import SubTask, Task
from app.services import project_access

logger = logging.getLogger(__name__)


def list_subtasks(
    db: Session, *, task_id: int | None = None, project_ids: set[int] | None = None
) -> list[SubTask]:
    query = db.query(SubTask).options(joinedload(SubTask.assignee), joinedload(SubTask.reporter))
    if project_ids is not None:
        query = query.join(Task, SubTask.task_id == Task.id).filter(Task.project_id.in_(project_ids))
    if task_id is not None:
        query = query.filter(SubTask.task_id == task_id)
    return query.order_by(SubTask.created_at.desc()).all()


def get_subtask(db: Session, *, subtask_id: int) -> SubTask | None:
    return (
        db.query(SubTask)
        .options(joinedload(SubTask.assignee), joinedload(SubTask.reporter))
        .filter(SubTask.id == subtask_id)
        .first()
    )


def create_subtask(
    db: Session,
    *,
    task_id: int,
    title: str,
    description: str | None,
    status: str,
    due_date,
    assigned_to: int | None,
    reported_by: int | None,
) -> SubTask:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise ValueError("That task does not exist")

    # A subtask can only be assigned to someone on the PARENT TASK's
    # project team (or Admin/Lead) — a subtask never has its own
    # project, it always inherits the task's.
    project_access.assert_valid_assignee(db, project_id=task.project_id, assignee_id=assigned_to)

    subtask = SubTask(
        task_id=task_id,
        title=title,
        description=description,
        status=status,
        due_date=due_date,
        assigned_to=assigned_to,
        reported_by=reported_by,
    )
    db.add(subtask)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create subtask %r on task #%s", title, task_id)
        raise
    db.refresh(subtask)
    logger.info("SubTask #%s %r created on task #%s", subtask.id, title, task_id)
    return subtask


def update_subtask(db: Session, *, subtask_id: int, **fields) -> SubTask:
    subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
    if subtask is None:
        raise LookupError("Subtask not found")

    if "assigned_to" in fields and fields["assigned_to"] is not None:
        parent_task = db.query(Task).filter(Task.id == subtask.task_id).first()
        project_access.assert_valid_assignee(
            db, project_id=parent_task.project_id, assignee_id=fields["assigned_to"]
        )

    for key, value in fields.items():
        if value is not None:
            setattr(subtask, key, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update subtask #%s", subtask_id)
        raise
    db.refresh(subtask)
    return subtask


def delete_subtask(db: Session, *, subtask_id: int) -> None:
    subtask = db.query(SubTask).filter(SubTask.id == subtask_id).first()
    if subtask is None:
        raise LookupError("Subtask not found")

    try:
        db.delete(subtask)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete subtask #%s", subtask_id)
        raise
    logger.info("SubTask #%s deleted", subtask_id)
