"""
Comment business logic (Phase 7 — closes the biggest functional gap
flagged against real-world trackers: no way to discuss a bug/task
in-app at all, forcing conversations out to Slack/email and losing
the context).

Deliberately kept simple for v1: plain text, no threading/replies, no
@mention parsing yet (see notify_on_comment's docstring for how
@mentions would slot in later without a schema change). One row per
comment, polymorphic via (entity_type, entity_id) — same pattern as
AuditLog, so Bugs/Tasks/SubTasks all share one table instead of three.
"""
from sqlalchemy.orm import Session, joinedload

from app.models import Bug, Comment, SubTask, Task, User
from app.services import notification_service, project_access
from app.services.role_service import user_has_permission

ENTITY_MODELS = {"Bug": Bug, "Task": Task, "SubTask": SubTask}


def _resolve_project_id(db: Session, *, entity_type: str, entity_id: int) -> int | None:
    """Bugs/Tasks carry project_id directly; a SubTask inherits it
    through its parent Task (see SubTask's docstring in models.py)."""
    if entity_type == "SubTask":
        subtask = db.query(SubTask).filter(SubTask.id == entity_id).first()
        if subtask is None:
            return None
        task = db.query(Task).filter(Task.id == subtask.task_id).first()
        return task.project_id if task else None
    entity = db.query(ENTITY_MODELS[entity_type]).filter(ENTITY_MODELS[entity_type].id == entity_id).first()
    return entity.project_id if entity else None


def _entity_title(db: Session, *, entity_type: str, entity_id: int) -> str | None:
    if entity_type == "SubTask":
        e = db.query(SubTask).filter(SubTask.id == entity_id).first()
    else:
        e = db.query(ENTITY_MODELS[entity_type]).filter(ENTITY_MODELS[entity_type].id == entity_id).first()
    return e.title if e else None


def _entity_watchers(db: Session, *, entity_type: str, entity_id: int) -> list[int]:
    """Who should be notified about activity on this entity: whoever's
    assigned to it and whoever reported/created it — the two people with
    an obvious stake, without needing a separate "watchers" table yet.
    """
    if entity_type == "SubTask":
        e = db.query(SubTask).filter(SubTask.id == entity_id).first()
    else:
        e = db.query(ENTITY_MODELS[entity_type]).filter(ENTITY_MODELS[entity_type].id == entity_id).first()
    if e is None:
        return []
    ids = set()
    if getattr(e, "assigned_to", None):
        ids.add(e.assigned_to)
    reporter_id = getattr(e, "reported_by", None)
    if reporter_id:
        ids.add(reporter_id)
    return list(ids)


def assert_entity_access(db: Session, *, user: User, entity_type: str, entity_id: int) -> None:
    if entity_type not in ENTITY_MODELS:
        raise ValueError(f"Unknown entity type: {entity_type}")
    project_id = _resolve_project_id(db, entity_type=entity_type, entity_id=entity_id)
    if project_id is None:
        raise LookupError(f"{entity_type} not found")
    project_access.assert_project_access(db, user=user, project_id=project_id)


def list_comments(db: Session, *, entity_type: str, entity_id: int) -> list[Comment]:
    return (
        db.query(Comment)
        .options(joinedload(Comment.author))
        .filter(Comment.entity_type == entity_type, Comment.entity_id == entity_id)
        .order_by(Comment.created_at.asc())
        .all()
    )


def create_comment(db: Session, *, entity_type: str, entity_id: int, author: User, body: str) -> Comment:
    body = body.strip()
    if not body:
        raise ValueError("Comment can't be empty")
    if len(body) > 3000:
        raise ValueError("Comment is too long (max 3000 characters)")

    comment = Comment(
        entity_type=entity_type,
        entity_id=entity_id,
        author_id=author.id,
        author_name=author.full_name,
        body=body,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    # Notify whoever's assigned/reported the entity (except the author
    # themselves — no need to notify people about their own comment).
    # NOTE on future @mentions: when that's added, parse `body` for
    # "@Full Name" patterns, resolve to user IDs, and fold them into the
    # `recipients` set below alongside the watchers — the notification
    # plumbing here doesn't need to change, just who's in this set.
    title = _entity_title(db, entity_type=entity_type, entity_id=entity_id) or f"{entity_type} #{entity_id}"
    recipients = [uid for uid in _entity_watchers(db, entity_type=entity_type, entity_id=entity_id) if uid != author.id]
    for recipient_id in recipients:
        notification_service.create_notification(
            db,
            recipient_id=recipient_id,
            kind="comment",
            message=f'{author.full_name} commented on "{title}"',
            link_path=_link_path_for(entity_type),
            entity_type=entity_type,
            entity_id=entity_id,
        )
    return comment


def delete_comment(db: Session, *, comment: Comment, actor: User) -> None:
    can_delete_any = user_has_permission(actor, "comments.delete_any")
    if comment.author_id != actor.id and not can_delete_any:
        raise PermissionError("You can only delete your own comments")
    db.delete(comment)
    db.commit()


def _link_path_for(entity_type: str) -> str:
    return {"Bug": "/bugs", "Task": "/tasks", "SubTask": "/tasks"}.get(entity_type, "/dashboard")
