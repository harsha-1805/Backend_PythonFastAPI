"""
Dashboard aggregation queries.

Everything here backs GET /api/v1/dashboard/summary — a single payload
that replaces the frontend's old utils/dummyData.js entirely. Kept as
plain SQLAlchemy aggregate queries (COUNT/GROUP BY) rather than loading
full ORM objects and summing in Python, since dashboard load time
matters and these tables can get large.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import AuditLog, Bug, Sprint, SubTask, Task, User

OPEN_BUG_STATUSES = ("Open", "In Progress")


def _scope_bugs(query, *, project_id: int | None, assigned_to: int | None, project_ids: set[int] | None = None):
    if project_id is not None:
        query = query.filter(Bug.project_id == project_id)
    elif project_ids is not None:
        query = query.filter(Bug.project_id.in_(project_ids))
    if assigned_to is not None:
        query = query.filter(Bug.assigned_to == assigned_to)
    return query


def _scope_tasks(query, *, project_id: int | None, assigned_to: int | None, project_ids: set[int] | None = None):
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    elif project_ids is not None:
        query = query.filter(Task.project_id.in_(project_ids))
    if assigned_to is not None:
        query = query.filter(Task.assigned_to == assigned_to)
    return query


def _scope_sprints(query, *, project_id: int | None, project_ids: set[int] | None = None):
    if project_id is not None:
        query = query.filter(Sprint.project_id == project_id)
    elif project_ids is not None:
        query = query.filter(Sprint.project_id.in_(project_ids))
    return query


def get_stat_cards(
    db: Session,
    *,
    project_id: int | None,
    assigned_to: int | None,
    project_ids: set[int] | None = None,
) -> dict:
    today = date.today()
    week_ago = datetime.utcnow() - timedelta(days=7)

    bug_q = _scope_bugs(db.query(Bug), project_id=project_id, assigned_to=assigned_to, project_ids=project_ids)
    task_q = _scope_tasks(db.query(Task), project_id=project_id, assigned_to=assigned_to, project_ids=project_ids)

    total_bugs = bug_q.count()
    critical_open = bug_q.filter(
        Bug.severity == "Critical", Bug.status.in_(OPEN_BUG_STATUSES)
    ).count()
    resolved_this_week = bug_q.filter(
        Bug.status.in_(("Resolved", "Closed")), Bug.updated_at >= week_ago
    ).count()
    open_bugs = bug_q.filter(Bug.status.in_(OPEN_BUG_STATUSES)).count()
    in_progress_bugs = bug_q.filter(Bug.status == "In Progress").count()

    overdue_tasks = task_q.filter(
        Task.due_date.isnot(None), Task.due_date < today, Task.status != "Done"
    ).count()

    sprint_q = _scope_sprints(db.query(Sprint), project_id=project_id, project_ids=project_ids)
    active_sprints = sprint_q.filter(Sprint.status == "Active").count()

    return {
        "total_bugs": total_bugs,
        "critical_open": critical_open,
        "resolved_this_week": resolved_this_week,
        "open_bugs": open_bugs,
        "in_progress_bugs": in_progress_bugs,
        "overdue_tasks": overdue_tasks,
        "active_sprints": active_sprints,
    }


def get_bug_status_breakdown(
    db: Session,
    *,
    project_id: int | None,
    assigned_to: int | None,
    project_ids: set[int] | None = None,
) -> list[dict]:
    query = _scope_bugs(
        db.query(Bug.status, func.count(Bug.id)),
        project_id=project_id,
        assigned_to=assigned_to,
        project_ids=project_ids,
    ).group_by(Bug.status)
    counts = dict(query.all())
    # Always return all four buckets (even at 0) so the pie chart/legend
    # doesn't jump around as statuses appear/disappear.
    return [
        {"status": s, "count": counts.get(s, 0)}
        for s in ("Open", "In Progress", "Resolved", "Closed")
    ]


def get_bug_trend(
    db: Session, *, project_id: int | None, days: int = 30, project_ids: set[int] | None = None
) -> list[dict]:
    """Bugs created vs. resolved per day, over the last `days` days."""
    since = datetime.utcnow() - timedelta(days=days)

    created_q = db.query(func.date(Bug.created_at), func.count(Bug.id)).filter(
        Bug.created_at >= since
    )
    resolved_q = db.query(func.date(Bug.updated_at), func.count(Bug.id)).filter(
        Bug.updated_at >= since, Bug.status.in_(("Resolved", "Closed"))
    )
    if project_id is not None:
        created_q = created_q.filter(Bug.project_id == project_id)
        resolved_q = resolved_q.filter(Bug.project_id == project_id)
    elif project_ids is not None:
        created_q = created_q.filter(Bug.project_id.in_(project_ids))
        resolved_q = resolved_q.filter(Bug.project_id.in_(project_ids))

    created_by_day = dict(created_q.group_by(func.date(Bug.created_at)).all())
    resolved_by_day = dict(resolved_q.group_by(func.date(Bug.updated_at)).all())

    days_list = [(since + timedelta(days=i)).date() for i in range(days + 1)]
    return [
        {
            "date": d.isoformat(),
            "created": created_by_day.get(d, 0),
            "resolved": resolved_by_day.get(d, 0),
        }
        for d in days_list
    ]


def get_top_buggy_modules(
    db: Session, *, project_id: int | None, limit: int = 5, project_ids: set[int] | None = None
) -> list[dict]:
    query = db.query(Bug.module, func.count(Bug.id)).filter(Bug.module.isnot(None))
    if project_id is not None:
        query = query.filter(Bug.project_id == project_id)
    elif project_ids is not None:
        query = query.filter(Bug.project_id.in_(project_ids))
    rows = (
        query.group_by(Bug.module)
        .order_by(func.count(Bug.id).desc())
        .limit(limit)
        .all()
    )
    return [{"module": m, "count": c} for m, c in rows]


def get_recent_activity(
    db: Session, *, project_id: int | None, limit: int = 8, project_ids: set[int] | None = None
) -> list[dict]:
    query = db.query(AuditLog)
    if project_id is not None:
        query = query.filter(AuditLog.project_id == project_id)
    elif project_ids is not None:
        # AuditLog.project_id is nullable (SET NULL on project delete) —
        # exclude those orphaned rows when scoping to a member's projects
        # so they don't leak into a restricted view.
        query = query.filter(AuditLog.project_id.in_(project_ids))
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "description": r.description,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def get_ai_insights(db: Session, *, project_id: int | None, project_ids: set[int] | None = None) -> list[dict]:
    """Rule-based, computed-from-real-data insights — deliberately NOT an
    LLM call (dashboard load needs to be fast and free every time it's
    opened). This is the "basic AI Assistant"-adjacent feature: genuine
    signal surfaced automatically, no user has to ask for it.
    """
    insights: list[dict] = []

    modules = get_top_buggy_modules(db, project_id=project_id, limit=1, project_ids=project_ids)
    if modules:
        insights.append(
            {
                "text": f"\"{modules[0]['module']}\" has the most reported bugs ({modules[0]['count']}). Consider prioritizing it next sprint.",
                "meta": "Based on bug module tags",
            }
        )

    bug_q = _scope_bugs(db.query(Bug), project_id=project_id, assigned_to=None, project_ids=project_ids)
    low_conf = bug_q.filter(
        Bug.is_ai_generated.is_(True), Bug.confidence_score.isnot(None), Bug.confidence_score < 60
    ).count()
    if low_conf:
        insights.append(
            {
                "text": f"{low_conf} AI-generated bug{'s' if low_conf != 1 else ''} have low confidence scores and may need manual review.",
                "meta": "AI Bug Generator",
            }
        )

    today = date.today()
    task_q = _scope_tasks(db.query(Task), project_id=project_id, assigned_to=None, project_ids=project_ids)
    overdue = task_q.filter(
        Task.due_date.isnot(None), Task.due_date < today, Task.status != "Done"
    ).count()
    if overdue:
        insights.append(
            {
                "text": f"{overdue} task{'s are' if overdue != 1 else ' is'} overdue. Check the Tasks board to reassign or reschedule.",
                "meta": "Task tracking",
            }
        )

    critical = bug_q.filter(Bug.severity == "Critical", Bug.status.in_(OPEN_BUG_STATUSES)).count()
    if critical:
        insights.append(
            {
                "text": f"{critical} Critical severity bug{'s are' if critical != 1 else ' is'} still open.",
                "meta": "Severity tracking",
            }
        )

    if not insights:
        insights.append({"text": "No urgent signals right now — things look steady.", "meta": "Auto-generated"})

    return insights


def get_dashboard_summary(
    db: Session,
    *,
    project_id: int | None,
    assigned_to: int | None,
    project_ids: set[int] | None = None,
) -> dict:
    """`project_ids` is the team-membership scope (None = Admin/Lead, see
    every project; a set = restrict to exactly those project IDs — see
    app.services.project_access.accessible_project_ids). When `project_id`
    is also given (a specific project picked in the UI), it takes
    precedence per-query since dashboard_router has already verified via
    project_access.assert_project_access that the caller may see it.
    """
    return {
        "stat_cards": get_stat_cards(db, project_id=project_id, assigned_to=assigned_to, project_ids=project_ids),
        "bug_status_breakdown": get_bug_status_breakdown(
            db, project_id=project_id, assigned_to=assigned_to, project_ids=project_ids
        ),
        "bug_trend": get_bug_trend(db, project_id=project_id, project_ids=project_ids),
        "top_buggy_modules": get_top_buggy_modules(db, project_id=project_id, project_ids=project_ids),
        "recent_activity": get_recent_activity(db, project_id=project_id, project_ids=project_ids),
        "ai_insights": get_ai_insights(db, project_id=project_id, project_ids=project_ids),
    }
