"""
Bug business logic (Phase 5 + Phase 8 project-team-scoped assignment).

`steps_to_reproduce` is stored as a JSON-encoded string in the `bugs`
table (see models.py) so we don't need a separate child table for a
simple list of strings. `_encode`/`_decode` are the only two places
that (de)serialize it — every other layer just deals with a normal
Python list.
"""
import json
import logging

from sqlalchemy.orm import Session, joinedload

from app.models import Bug, Project, Task
from app.services import project_access

logger = logging.getLogger(__name__)


def _encode(steps: list[str] | None) -> str:
    return json.dumps(steps or [])


def decode_steps(bug: Bug) -> list[str]:
    if not bug.steps_to_reproduce:
        return []
    try:
        return json.loads(bug.steps_to_reproduce)
    except (TypeError, ValueError):
        return []


def serialize(bug: Bug) -> dict:
    """Build a plain dict matching BugOut, decoding steps_to_reproduce."""
    return {
        "id": bug.id,
        "project_id": bug.project_id,
        "sprint_id": bug.sprint_id,
        "task_id": bug.task_id,
        "task": bug.task,
        "title": bug.title,
        "severity": bug.severity,
        "priority": bug.priority,
        "status": bug.status,
        "summary": bug.summary,
        "description": bug.description,
        "environment": bug.environment,
        "module": bug.module,
        "bug_type": bug.bug_type,
        "expected_result": bug.expected_result,
        "actual_result": bug.actual_result,
        "possible_root_cause": bug.possible_root_cause,
        "confidence_score": bug.confidence_score,
        "steps_to_reproduce": decode_steps(bug),
        "is_ai_generated": bug.is_ai_generated,
        "image_url": bug.image_url,
        "reporter": bug.reporter,
        "assignee": bug.assignee,
        "created_at": bug.created_at,
        "updated_at": bug.updated_at,
    }


def list_bugs(
    db: Session,
    *,
    project_id: int | None = None,
    sprint_id: int | None = None,
    status: str | None = None,
    assigned_to: int | None = None,
    search: str | None = None,
    project_ids: set[int] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Bug], int]:
    query = db.query(Bug).options(
        joinedload(Bug.reporter), joinedload(Bug.assignee), joinedload(Bug.task).joinedload(Task.sprint)
    )

    if project_ids is not None:
        query = query.filter(Bug.project_id.in_(project_ids))
    if project_id is not None:
        query = query.filter(Bug.project_id == project_id)
    if sprint_id is not None:
        query = query.filter(Bug.sprint_id == sprint_id)
    if status:
        query = query.filter(Bug.status == status)
    if assigned_to is not None:
        query = query.filter(Bug.assigned_to == assigned_to)
    if search:
        query = query.filter(Bug.title.ilike(f"%{search.strip()}%"))

    total = query.count()
    items = (
        query.order_by(Bug.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_bug(db: Session, *, bug_id: int) -> Bug | None:
    return (
        db.query(Bug)
        .options(
            joinedload(Bug.reporter),
            joinedload(Bug.assignee),
            joinedload(Bug.task).joinedload(Task.sprint),
        )
        .filter(Bug.id == bug_id)
        .first()
    )


def create_bug(db: Session, *, reported_by: int, **fields) -> Bug:
    project_id = fields.pop("project_id")
    if not db.query(Project).filter(Project.id == project_id).first():
        raise ValueError("That project does not exist")

    # A bug can only be assigned to someone on this project's team (or
    # Admin/Lead) — same rule as tasks/subtasks.
    project_access.assert_valid_assignee(
        db, project_id=project_id, assignee_id=fields.get("assigned_to")
    )

    steps = fields.pop("steps_to_reproduce", [])
    bug = Bug(project_id=project_id, reported_by=reported_by, steps_to_reproduce=_encode(steps), **fields)
    db.add(bug)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create bug %r on project #%s", fields.get("title"), project_id)
        raise
    db.refresh(bug)
    logger.info("Bug #%s created on project #%s", bug.id, project_id)
    return bug


def update_bug(db: Session, *, bug_id: int, **fields) -> Bug:
    bug = db.query(Bug).filter(Bug.id == bug_id).first()
    if bug is None:
        raise LookupError("Bug not found")

    if "assigned_to" in fields and fields["assigned_to"] is not None:
        project_access.assert_valid_assignee(
            db, project_id=bug.project_id, assignee_id=fields["assigned_to"]
        )

    if "steps_to_reproduce" in fields:
        steps = fields.pop("steps_to_reproduce")
        if steps is not None:
            bug.steps_to_reproduce = _encode(steps)

    for key, value in fields.items():
        if value is not None:
            setattr(bug, key, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update bug #%s", bug_id)
        raise
    db.refresh(bug)
    return bug


def delete_bug(db: Session, *, bug_id: int) -> None:
    bug = db.query(Bug).filter(Bug.id == bug_id).first()
    if bug is None:
        raise LookupError("Bug not found")

    try:
        db.delete(bug)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete bug #%s", bug_id)
        raise
    logger.info("Bug #%s deleted", bug_id)
