"""
Reports: deeper analytics than the Dashboard (date-range filterable),
plus CSV export. CSV building lives here (not in the router) so the
same row-shaping logic backs both the on-screen report and the
downloadable file — they can never drift apart.
"""
import csv
import io
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, Bug, Sprint, SubTask, Task, User


def _date_range(date_from: date | None, date_to: date | None) -> tuple[datetime, datetime]:
    """Defaults to the last 30 days when no range is given — every
    report/export call has a bounded, predictable size instead of
    accidentally full-table-scanning a year of history.
    """
    end = datetime.combine(date_to, datetime.max.time()) if date_to else datetime.utcnow()
    start = (
        datetime.combine(date_from, datetime.min.time())
        if date_from
        else end - timedelta(days=30)
    )
    return start, end


# ---------------------------------------------------------------------------
# Bug Analytics
# ---------------------------------------------------------------------------
def bug_analytics(
    db: Session, *, project_id: int | None, date_from: date | None, date_to: date | None
) -> dict:
    start, end = _date_range(date_from, date_to)
    query = db.query(Bug).filter(Bug.created_at >= start, Bug.created_at <= end)
    if project_id is not None:
        query = query.filter(Bug.project_id == project_id)
    bugs = query.all()

    total = len(bugs)
    resolved = [b for b in bugs if b.status in ("Resolved", "Closed")]
    resolution_rate = round(len(resolved) / total * 100, 1) if total else 0.0

    avg_resolution_hours = None
    if resolved:
        deltas = [(b.updated_at - b.created_at).total_seconds() / 3600 for b in resolved]
        avg_resolution_hours = round(sum(deltas) / len(deltas), 1)

    def _bucket(attr):
        counts: dict[str, int] = {}
        for b in bugs:
            key = getattr(b, attr) or "Unspecified"
            counts[key] = counts.get(key, 0) + 1
        return [{"label": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]

    return {
        "total_bugs": total,
        "resolution_rate_pct": resolution_rate,
        "avg_resolution_hours": avg_resolution_hours,
        "by_severity": _bucket("severity"),
        "by_priority": _bucket("priority"),
        "by_module": _bucket("module"),
        "by_status": _bucket("status"),
        "date_from": start.date().isoformat(),
        "date_to": end.date().isoformat(),
    }


# ---------------------------------------------------------------------------
# Sprint Report (velocity / burndown)
# ---------------------------------------------------------------------------
def sprint_report(db: Session, *, project_id: int | None) -> dict:
    query = db.query(Sprint)
    if project_id is not None:
        query = query.filter(Sprint.project_id == project_id)
    sprints = query.order_by(Sprint.start_date.desc().nullslast()).limit(10).all()

    velocity = []
    for sprint in sprints:
        tasks = db.query(Task).filter(Task.sprint_id == sprint.id).all()
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == "Done")
        velocity.append(
            {
                "sprint_id": sprint.id,
                "sprint_name": sprint.name,
                "status": sprint.status,
                "total_tasks": total,
                "completed_tasks": done,
                "completion_pct": round(done / total * 100, 1) if total else 0.0,
            }
        )

    return {"sprints": list(reversed(velocity))}  # chronological for a burndown-style chart


# ---------------------------------------------------------------------------
# Team Performance — AGGREGATE ONLY, no individual scorecards.
#
# Deliberate scope choice: per-person "who resolved the most / slowest"
# breakdowns read as a surveillance scorecard, not a useful team report,
# and weren't explicitly asked for. This reports workload distribution
# (counts per person) without ranking or resolution-time comparisons
# between individuals. Easy to extend into per-person detail later if
# you decide you want that after all — flag it and I'll add it behind
# an Admin-only permission.
# ---------------------------------------------------------------------------
def team_performance(db: Session, *, project_id: int | None) -> dict:
    bug_query = db.query(Bug.assigned_to, func.count(Bug.id)).filter(Bug.assigned_to.isnot(None))
    task_query = db.query(Task.assigned_to, func.count(Task.id)).filter(Task.assigned_to.isnot(None))
    if project_id is not None:
        bug_query = bug_query.filter(Bug.project_id == project_id)
        task_query = task_query.filter(Task.project_id == project_id)

    bug_counts = dict(bug_query.group_by(Bug.assigned_to).all())
    task_counts = dict(task_query.group_by(Task.assigned_to).all())

    user_ids = set(bug_counts) | set(task_counts)
    users = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}

    workload = [
        {
            "user_id": uid,
            "full_name": users.get(uid, f"User #{uid}"),
            "open_bugs": bug_counts.get(uid, 0),
            "open_tasks": task_counts.get(uid, 0),
        }
        for uid in user_ids
    ]
    workload.sort(key=lambda w: -(w["open_bugs"] + w["open_tasks"]))

    return {"workload": workload}


# ---------------------------------------------------------------------------
# AI Bug Generator ROI
# ---------------------------------------------------------------------------
def ai_bug_stats(db: Session, *, project_id: int | None) -> dict:
    query = db.query(Bug)
    if project_id is not None:
        query = query.filter(Bug.project_id == project_id)
    bugs = query.all()

    ai_bugs = [b for b in bugs if b.is_ai_generated]
    manual_bugs = [b for b in bugs if not b.is_ai_generated]
    scored = [b.confidence_score for b in ai_bugs if b.confidence_score is not None]

    return {
        "ai_generated_count": len(ai_bugs),
        "manual_count": len(manual_bugs),
        "avg_confidence_score": round(sum(scored) / len(scored), 1) if scored else None,
        "low_confidence_count": sum(1 for s in scored if s < 60),
    }


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
def export_bugs_csv(
    db: Session,
    *,
    project_id: int | None,
    date_from: date | None,
    date_to: date | None,
    status: str | None,
    severity: str | None,
) -> str:
    start, end = _date_range(date_from, date_to)
    query = (
        db.query(Bug)
        .options(joinedload(Bug.reporter), joinedload(Bug.assignee), joinedload(Bug.project))
        .filter(Bug.created_at >= start, Bug.created_at <= end)
    )
    if project_id is not None:
        query = query.filter(Bug.project_id == project_id)
    if status:
        query = query.filter(Bug.status == status)
    if severity:
        query = query.filter(Bug.severity == severity)
    bugs = query.order_by(Bug.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ID", "Title", "Project", "Severity", "Priority", "Status", "Module",
            "AI Generated", "Confidence Score", "Reported By", "Assigned To",
            "Created At", "Updated At",
        ]
    )
    for b in bugs:
        writer.writerow(
            [
                b.id,
                b.title,
                b.project.name if b.project else "",
                b.severity,
                b.priority,
                b.status,
                b.module or "",
                "Yes" if b.is_ai_generated else "No",
                b.confidence_score if b.confidence_score is not None else "",
                b.reporter.full_name if b.reporter else "",
                b.assignee.full_name if b.assignee else "",
                b.created_at.isoformat(),
                b.updated_at.isoformat(),
            ]
        )
    return buffer.getvalue()


def export_tasks_csv(
    db: Session, *, project_id: int | None, date_from: date | None, date_to: date | None, status: str | None
) -> str:
    start, end = _date_range(date_from, date_to)
    query = (
        db.query(Task)
        .options(joinedload(Task.assignee), joinedload(Task.project), joinedload(Task.sprint))
        .filter(Task.created_at >= start, Task.created_at <= end)
    )
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if status:
        query = query.filter(Task.status == status)
    tasks = query.order_by(Task.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["ID", "Title", "Project", "Sprint", "Status", "Due Date", "Assigned To", "Created At"]
    )
    for t in tasks:
        writer.writerow(
            [
                t.id,
                t.title,
                t.project.name if t.project else "",
                t.sprint.name if t.sprint else "",
                t.status,
                t.due_date.isoformat() if t.due_date else "",
                t.assignee.full_name if t.assignee else "",
                t.created_at.isoformat(),
            ]
        )
    return buffer.getvalue()


def export_audit_log_csv(
    db: Session,
    *,
    project_id: int | None,
    entity_type: str | None,
    date_from: date | None,
    date_to: date | None,
) -> str:
    start, end = _date_range(date_from, date_to)
    query = db.query(AuditLog).filter(AuditLog.created_at >= start, AuditLog.created_at <= end)
    if project_id is not None:
        query = query.filter(AuditLog.project_id == project_id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    rows = query.order_by(AuditLog.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["When", "Who", "Module", "Action", "Description"])
    for r in rows:
        writer.writerow([r.created_at.isoformat(), r.actor_name or "System", r.entity_type, r.action, r.description])
    return buffer.getvalue()
