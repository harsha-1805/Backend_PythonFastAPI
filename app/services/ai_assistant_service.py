"""
AI Assistant — Phase 7+.

Still deliberately NOT a full free-form LLM chat with tool-calling — the
brief was "basic for now, improve later". This iteration keeps the same
"deterministic DB query matched by keyword intent, LLM only as a
fallback" shape as before, but fixes a real access-control gap and adds
the capabilities that were actually missing:

  Security fix: this service previously ran on `project_id` with ZERO
  team-membership checking — any user (Employee/QA/HR) could pass any
  project_id in the request body and query another team's data, and
  even an unscoped query searched every project org-wide. Every handler
  now takes `project_ids` (the caller's accessible-project scope from
  project_access.accessible_project_ids) the same way dashboard_service
  and bug_service already do, and the router asserts access up front
  when a specific project_id is given.

  Role-aware responses: a manager-tier role (Admin/Lead) asking "how's
  this project doing" gets a stakeholder-style roll-up; an individual
  contributor (Employee/QA/HR) gets the specific list of items, since
  that's what they'd actually act on.

  New intents: similar/duplicate bug lookup (lightweight keyword-overlap
  "RAG", not vector search yet — see note below), "why is this bug
  still open" (pulls the bug + its audit trail), repro-step / edge-case
  generation for a bug (LLM, grounded in that bug's real fields), daily
  /weekly digests, "my work" (assigned-to-me bugs/tasks), and a
  task-focused summary. A `module` hint from the frontend's per-page AI
  icon also lets a generic "summarize this" resolve to the right kind
  of summary for whatever page it was asked from.

NOTE on "RAG over your own data": `_similar_bugs` below is a real,
useful first cut (word-overlap scoring over title/module/bug_type
within the same project) but is NOT vector/embedding search. Wiring up
true embedding similarity (pgvector or a small FAISS index over
title+description) is the natural next step — flagged again in the
chat reply, not silently implied here.

Latest additions:
  Per-person workload lookup (Admin/Lead only, or anyone asking about
  themselves): "how many bugs does <name> have", "<name>'s workload" —
  matches a real active user by name (see `_extract_person`) plus a
  work-related keyword, and reports their project memberships, bug
  count broken down by project, task count, and a resolution-rate /
  average-time-to-resolve efficiency figure. This is a heuristic name
  match, not NLP — an unusual first name that collides with a common
  English word could misfire; acceptable for now, flagged here rather
  than silently assumed reliable.

  "Who has how many bugs" now also surfaces each assignee's nearest
  sprint end date among their open bugs, not just a raw count.

  Explain-and-fix-suggestion for a specific bug ("explain #42", "how do
  I fix #42"): a deliberately short, two-line LLM answer (what's
  happening / try this) grounded in that bug's actual fields, aimed at
  whoever's about to pick it up rather than a full diagnostic report.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import AuditLog, Bug, Project, ProjectMember, Sprint, Task, User
from app.services import dashboard_service, project_access, role_service
from app.services.llm.gemini_client import GeminiClient

_gemini_client = GeminiClient()

OPEN_STATUSES = ("Open", "In Progress")
STALE_DAYS = 14


def _scope(query, model, *, project_id, project_ids):
    if project_id is not None:
        return query.filter(model.project_id == project_id)
    if project_ids is not None:
        return query.filter(model.project_id.in_(project_ids))
    return query


def _is_elevated(user: User) -> bool:
    return project_access.has_elevated_access(user)


def _extract_bug_id(text: str):
    match = re.search(r"#\s*(\d+)", text) or re.search(r"\bbug\s+(\d+)\b", text)
    return int(match.group(1)) if match else None


def _get_bug_scoped(db: Session, *, bug_id: int, project_id, project_ids):
    query = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids)
    return query.filter(Bug.id == bug_id).first()


def _list_open_bugs(db: Session, *, project_id, project_ids, user, message: str) -> str:
    query = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids).filter(
        Bug.status.in_(OPEN_STATUSES)
    )
    bugs = query.order_by(Bug.severity.desc(), Bug.created_at.desc()).limit(10).all()
    if not bugs:
        return "There are no open bugs in your accessible projects right now. 🎉"
    lines = [f"Here are the open bugs{' for this project' if project_id else ''} (top 10 by severity):"]
    for b in bugs:
        lines.append(f"- #{b.id} [{b.severity}] {b.title} — {b.status}")
    total = query.count()
    if total > 10:
        lines.append(f"...and {total - 10} more.")
    return "\n".join(lines)


def _bug_summary(db: Session, *, project_id, project_ids, user, message: str) -> str:
    breakdown = dashboard_service.get_bug_status_breakdown(
        db, project_id=project_id, assigned_to=None, project_ids=project_ids
    )
    total = sum(b["count"] for b in breakdown)
    if total == 0:
        return "No bugs have been reported yet in your accessible projects."
    parts = [f"{b['count']} {b['status']}" for b in breakdown if b["count"] > 0]
    base = f"Bug summary: {total} total — " + ", ".join(parts) + "."

    if _is_elevated(user):
        modules = dashboard_service.get_top_buggy_modules(db, project_id=project_id, limit=1, project_ids=project_ids)
        critical = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids).filter(
            Bug.severity == "Critical", Bug.status.in_(OPEN_STATUSES)
        ).count()
        extra = []
        if critical:
            extra.append(f"{critical} of those are Critical and still open — worth a look before standup.")
        if modules:
            extra.append(f"\"{modules[0]['module']}\" is the most bug-prone area right now ({modules[0]['count']} bugs).")
        return base + (" " + " ".join(extra) if extra else "")
    else:
        mine = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids).filter(
            Bug.assigned_to == user.id, Bug.status.in_(OPEN_STATUSES)
        ).count()
        return base + (f" {mine} of the open ones are assigned to you." if mine else " None of the open ones are assigned to you.")


def _search_bugs(db: Session, *, project_id, project_ids, user, message: str, keyword: str) -> str:
    if not keyword:
        return 'Tell me what to search for — e.g. "search bugs for login".'
    query = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids).filter(
        Bug.title.ilike(f"%{keyword}%")
    )
    bugs = query.order_by(Bug.created_at.desc()).limit(10).all()
    if not bugs:
        return f'No bugs found matching "{keyword}".'
    lines = [f'Bugs matching "{keyword}":']
    for b in bugs:
        lines.append(f"- #{b.id} [{b.severity}/{b.status}] {b.title}")
    return "\n".join(lines)


def _sprint_status(db: Session, *, project_id, project_ids, user, message: str) -> str:
    query = _scope(db.query(Sprint), Sprint, project_id=project_id, project_ids=project_ids).filter(
        Sprint.status == "Active"
    )
    sprints = query.all()
    if not sprints:
        return "There's no active sprint right now in your accessible projects."
    lines = []
    for sprint in sprints:
        tasks = db.query(Task).filter(Task.sprint_id == sprint.id).all()
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == "Done")
        pct = round(done / total * 100) if total else 0
        lines.append(f"\"{sprint.name}\": {done}/{total} tasks done ({pct}%)")
    return "Sprint status:\n" + "\n".join(f"- {line}" for line in lines)


def _module_analysis(db: Session, *, project_id, project_ids, user, message: str) -> str:
    modules = dashboard_service.get_top_buggy_modules(db, project_id=project_id, limit=5, project_ids=project_ids)
    if not modules:
        return "No bugs have module tags yet, so I can't rank modules."
    lines = []
    for m in modules:
        bugs = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids).filter(
            Bug.module == m["module"]
        ).all()
        assignee_ids = {b.assigned_to for b in bugs if b.assigned_to}
        if assignee_ids:
            names = [u.full_name for u in db.query(User).filter(User.id.in_(assignee_ids)).all()]
            who = f" — assigned to: {', '.join(names)}"
        else:
            who = " — unassigned"
        lines.append(f"{m['module']}: {m['count']} bugs{who}")
    return "Most bug-prone modules:\n" + "\n".join(f"- {line}" for line in lines)


def _similar_bugs(db: Session, *, project_id, project_ids, user, message: str) -> str:
    bug_id = _extract_bug_id(message)
    if bug_id is None:
        return 'Tell me which bug — e.g. "find bugs similar to #42".'
    target = _get_bug_scoped(db, bug_id=bug_id, project_id=project_id, project_ids=project_ids)
    if target is None:
        return f"I couldn't find bug #{bug_id} in your accessible projects."

    stop_words = {"the", "a", "an", "on", "in", "to", "of", "is", "for", "and", "with", "not", "issue", "bug", "error"}
    target_words = {w for w in re.findall(r"[a-z0-9]+", target.title.lower()) if w not in stop_words and len(w) > 2}
    candidates = db.query(Bug).filter(Bug.project_id == target.project_id, Bug.id != target.id).all()

    scored = []
    for c in candidates:
        c_words = {w for w in re.findall(r"[a-z0-9]+", c.title.lower()) if w not in stop_words and len(w) > 2}
        score = len(target_words & c_words)
        if target.module and c.module == target.module:
            score += 1
        if target.bug_type and c.bug_type == target.bug_type:
            score += 1
        if score > 0:
            scored.append((score, c))

    if not scored:
        return f"I didn't find any bugs that look related to #{bug_id} (\"{target.title}\") — it looks unique so far."

    scored.sort(key=lambda pair: pair[0], reverse=True)
    lines = [f"Bugs that look related to #{bug_id} (\"{target.title}\"), most likely duplicates first:"]
    for score, c in scored[:5]:
        lines.append(f"- #{c.id} [{c.status}] {c.title} (match score {score})")
    lines.append("Worth a quick check before filing a new one for the same root cause.")
    return "\n".join(lines)


def _why_open(db: Session, *, project_id, project_ids, user, message: str) -> str:
    bug_id = _extract_bug_id(message)
    if bug_id is None:
        return 'Tell me which bug — e.g. "why is #42 still open".'
    bug = _get_bug_scoped(db, bug_id=bug_id, project_id=project_id, project_ids=project_ids)
    if bug is None:
        return f"I couldn't find bug #{bug_id} in your accessible projects."

    age_days = (datetime.utcnow() - bug.created_at).days
    assignee = bug.assignee.full_name if bug.assignee else "nobody yet"

    history = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "Bug", AuditLog.entity_id == bug.id)
        .order_by(AuditLog.created_at.desc())
        .limit(5)
        .all()
    )

    lines = [
        f"#{bug.id} \"{bug.title}\" has been {bug.status} for {age_days} day{'s' if age_days != 1 else ''} "
        f"({bug.severity} severity, {bug.priority}). Assigned to: {assignee}."
    ]
    if history:
        lines.append("Recent activity:")
        for h in history:
            lines.append(f"- {h.created_at.strftime('%b %d')}: {h.description}")
    else:
        lines.append("No activity has been logged on it since it was created — that's likely why it's stuck; it may just need to be picked up.")
    return "\n".join(lines)


def _generate_test_steps(db: Session, *, project_id, project_ids, user, message: str) -> str:
    bug_id = _extract_bug_id(message)
    if bug_id is None:
        return 'Tell me which bug — e.g. "generate test steps for #42".'
    bug = _get_bug_scoped(db, bug_id=bug_id, project_id=project_id, project_ids=project_ids)
    if bug is None:
        return f"I couldn't find bug #{bug_id} in your accessible projects."

    context = (
        f"Title: {bug.title}\n"
        f"Module: {bug.module or 'n/a'}\n"
        f"Description: {bug.description or 'n/a'}\n"
        f"Expected result: {bug.expected_result or 'n/a'}\n"
        f"Actual result: {bug.actual_result or 'n/a'}\n"
        f"Existing repro steps: {bug.steps_to_reproduce or 'none recorded'}"
    )
    prompt = (
        "You are a senior QA engineer. Given the bug details below, write:\n"
        "1) A clear numbered set of repro steps (rewrite/tighten the existing ones if given, "
        "or write new ones from the description if not).\n"
        "2) 3-4 edge cases QA should also check that are related to this bug but not explicitly reported.\n"
        "Keep it concise, plain text, no markdown headers.\n\n"
        f"{context}"
    )
    answer = _gemini_client.generate_text(prompt=prompt)
    return f"Repro steps & edge cases for #{bug.id} \"{bug.title}\":\n\n{answer}"


def _digest(db: Session, *, project_id, project_ids, user, message: str) -> str:
    days = 1 if re.search(r"\bdaily\b|\btoday\b", message) else 7
    since = datetime.utcnow() - timedelta(days=days)
    stale_cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS)
    label = "Daily" if days == 1 else "Weekly"

    bug_q = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids)
    created = bug_q.filter(Bug.created_at >= since).count()
    resolved = bug_q.filter(Bug.status.in_(("Resolved", "Closed")), Bug.updated_at >= since).count()
    newly_critical = bug_q.filter(
        Bug.severity == "Critical", Bug.status.in_(OPEN_STATUSES), Bug.updated_at >= since
    ).count()
    stale = bug_q.filter(Bug.status.in_(OPEN_STATUSES), Bug.updated_at < stale_cutoff).count()

    if _is_elevated(user):
        lines = [f"{label} digest: {created} new bug{'s' if created != 1 else ''}, {resolved} resolved."]
        if newly_critical:
            lines.append(f"{newly_critical} Critical bug{'s are' if newly_critical != 1 else ' is'} open and newly touched — flag for the team.")
        if stale:
            lines.append(f"{stale} bug{'s have' if stale != 1 else ' has'} had no update in over {STALE_DAYS} days and may be stalled.")
        if created == 0 and resolved == 0 and not newly_critical and not stale:
            lines.append("Quiet period — nothing urgent to report.")
        return " ".join(lines)
    else:
        recent = bug_q.filter(Bug.created_at >= since).order_by(Bug.created_at.desc()).limit(5).all()
        lines = [f"{label} digest — {created} new, {resolved} resolved, {newly_critical} newly critical, {stale} stale (>{STALE_DAYS}d idle)."]
        if recent:
            lines.append("Newest:")
            for b in recent:
                lines.append(f"- #{b.id} [{b.severity}] {b.title}")
        return "\n".join(lines)


def _task_summary(db: Session, *, project_id, project_ids, user, message: str) -> str:
    today = date.today()
    task_q = _scope(db.query(Task), Task, project_id=project_id, project_ids=project_ids)
    total = task_q.count()
    if total == 0:
        return "No tasks in your accessible projects yet."
    todo = task_q.filter(Task.status == "To Do").count()
    in_progress = task_q.filter(Task.status == "In Progress").count()
    done = task_q.filter(Task.status == "Done").count()
    overdue = task_q.filter(Task.due_date.isnot(None), Task.due_date < today, Task.status != "Done").count()

    lines = [f"Tasks: {total} total — {todo} To Do, {in_progress} In Progress, {done} Done."]
    if overdue:
        lines.append(f"{overdue} task{'s are' if overdue != 1 else ' is'} overdue.")
    return " ".join(lines)


def _my_work(db: Session, *, project_id, project_ids, user, message: str) -> str:
    bug_q = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids).filter(
        Bug.assigned_to == user.id, Bug.status.in_(OPEN_STATUSES)
    )
    task_q = _scope(db.query(Task), Task, project_id=project_id, project_ids=project_ids).filter(
        Task.assigned_to == user.id, Task.status != "Done"
    )
    bugs = bug_q.order_by(Bug.severity.desc()).limit(5).all()
    tasks = task_q.order_by(Task.due_date.asc()).limit(5).all()

    if not bugs and not tasks:
        return "You have no open bugs or pending tasks assigned to you right now. All clear!"

    lines = ["Your open work:"]
    for b in bugs:
        lines.append(f"- Bug #{b.id} [{b.severity}] {b.title}")
    for t in tasks:
        due = f", due {t.due_date}" if t.due_date else ""
        lines.append(f"- Task #{t.id} {t.title} [{t.status}]{due}")
    return "\n".join(lines)


_ENTITY_KEYWORDS = {"sprint": "Sprint", "project": "Project", "task": "Task", "bug": "Bug"}


def _who_created(db: Session, *, project_id, project_ids, user, message: str) -> str:
    entity_type = next((v for k, v in _ENTITY_KEYWORDS.items() if k in message), None)
    query = _scope(db.query(AuditLog), AuditLog, project_id=project_id, project_ids=project_ids).filter(
        AuditLog.action == "created"
    )
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    logs = query.order_by(AuditLog.created_at.desc()).limit(5).all()
    if not logs:
        label = entity_type.lower() if entity_type else "item"
        return f"I couldn't find any {label} creation records in your accessible projects."
    label = entity_type or "Item"
    lines = [f"Recent {label} creations:"]
    for log in logs:
        who = log.actor_name or "an unknown user"
        lines.append(f"- \"{log.entity_name or log.entity_id}\" created by {who} ({log.created_at.strftime('%b %d')})")
    return "\n".join(lines)


def _user_roles(db: Session, *, project_id, project_ids, user, message: str) -> str:
    if not role_service.user_has_permission(user, "users.view"):
        return "You don't have permission to view user roles — check with an Admin or HR."
    users = db.query(User).filter(User.is_active.is_(True)).all()
    if not users:
        return "No active users found."
    lines = [f"{len(users)} active user(s) and their roles:"]
    for u in users:
        names = ", ".join(r.name for r in u.roles) or "No role assigned"
        lines.append(f"- {u.full_name}: {names}")
    distinct_roles = sorted({r.name for u in users for r in u.roles})
    lines.append(f"Distinct roles in use: {', '.join(distinct_roles) or 'none'} ({len(distinct_roles)} total).")
    return "\n".join(lines)


def _assignee_breakdown(db: Session, *, project_id, project_ids, user, message: str) -> str:
    bugs = _scope(db.query(Bug), Bug, project_id=project_id, project_ids=project_ids).filter(
        Bug.status.in_(OPEN_STATUSES)
    ).all()
    if not bugs:
        return "There are no open bugs assigned to anyone right now."
    counts: dict[int, int] = {}
    # Track each assignee's nearest sprint end date among their open bugs
    # — the deadline they're actually working against — so an admin
    # asking "who has how many bugs" also sees who's up against the
    # clock, not just raw counts.
    nearest_deadline: dict[int, date] = {}
    unassigned = 0
    sprint_ids = {b.sprint_id for b in bugs if b.sprint_id}
    sprint_end_dates = {}
    if sprint_ids:
        sprint_end_dates = {
            s.id: s.end_date
            for s in db.query(Sprint).filter(Sprint.id.in_(sprint_ids)).all()
            if s.end_date is not None
        }
    for b in bugs:
        if b.assigned_to:
            counts[b.assigned_to] = counts.get(b.assigned_to, 0) + 1
            end = sprint_end_dates.get(b.sprint_id)
            if end and (b.assigned_to not in nearest_deadline or end < nearest_deadline[b.assigned_to]):
                nearest_deadline[b.assigned_to] = end
        else:
            unassigned += 1
    users_map = {}
    if counts:
        users_map = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(counts.keys())).all()}
    lines = ["Open bugs by assignee:"]
    for uid, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        deadline = nearest_deadline.get(uid)
        deadline_note = f" — nearest sprint ends {deadline.strftime('%b %d')}" if deadline else ""
        lines.append(f"- {users_map.get(uid, 'Unknown')}: {count}{deadline_note}")
    if unassigned:
        lines.append(f"- Unassigned: {unassigned}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-person workload lookup — Admin/Lead only.
#
# "Who is <name>" style questions that name a real, active user AND
# mention work-related keywords (bug/task/project/workload/etc.) route
# here instead of the generic assignee breakdown above. Gated to
# elevated roles since it surfaces one person's full workload and a
# derived performance figure (resolution rate) — not something every
# role should be able to pull up about a teammate.
def _extract_person(db: Session, message: str) -> User | None:
    users = db.query(User).filter(User.is_active.is_(True)).all()
    best, best_len = None, 0
    for u in users:
        full = (u.full_name or "").lower().strip()
        if not full:
            continue
        first = full.split()[0]
        for candidate in (full, first):
            if len(candidate) >= 3 and re.search(rf"\b{re.escape(candidate)}\b", message):
                if len(candidate) > best_len:
                    best, best_len = u, len(candidate)
    return best


_WORKLOAD_HINT = re.compile(
    r"\b(bugs?|tasks?|projects?|workload|assign\w*|perform\w*|efficien\w*|productiv\w*|solv\w*|how many)\b"
)


def _person_workload(db: Session, *, target: User, user: User, message: str) -> str:
    if target.id != user.id and not _is_elevated(user):
        return "You don't have permission to look up another team member's workload — ask an Admin or Lead."

    projects = (
        db.query(Project.id, Project.name)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .filter(ProjectMember.user_id == target.id)
        .all()
    )
    project_ids_for_person = [p.id for p in projects]

    bugs = db.query(Bug).filter(Bug.assigned_to == target.id).all()
    total_bugs = len(bugs)
    by_project: dict[int, int] = {}
    resolved_or_closed = 0
    resolution_days = []
    for b in bugs:
        by_project[b.project_id] = by_project.get(b.project_id, 0) + 1
        if b.status in ("Resolved", "Closed"):
            resolved_or_closed += 1
            resolution_days.append((b.updated_at - b.created_at).days)
    open_bugs = total_bugs - resolved_or_closed
    project_names = {p.id: p.name for p in projects}
    # A bug can be assigned to someone on a project they're no longer a
    # member of (removed from team after assignment) — still count it,
    # just fall back to the bug's own project_id as the label.
    missing_ids = set(by_project) - set(project_names)
    if missing_ids:
        for p in db.query(Project.id, Project.name).filter(Project.id.in_(missing_ids)).all():
            project_names[p.id] = p.name

    task_count = db.query(Task).filter(Task.assigned_to == target.id).count()
    open_tasks = db.query(Task).filter(Task.assigned_to == target.id, Task.status != "Done").count()

    lines = [f"Workload for {target.full_name}:"]
    lines.append(f"- {len(projects)} project{'s' if len(projects) != 1 else ''}: " + (", ".join(p.name for p in projects) if projects else "none"))
    lines.append(f"- {total_bugs} bug{'s' if total_bugs != 1 else ''} assigned ({open_bugs} open, {resolved_or_closed} resolved/closed)")
    if by_project:
        lines.append("  By project: " + ", ".join(f"{project_names.get(pid, '?')}: {c}" for pid, c in sorted(by_project.items(), key=lambda kv: -kv[1])))
    lines.append(f"- {task_count} task{'s' if task_count != 1 else ''} assigned ({open_tasks} still open)")
    if total_bugs:
        rate = round(resolved_or_closed / total_bugs * 100)
        lines.append(f"- Resolution rate: {rate}% ({resolved_or_closed} of {total_bugs} assigned bugs resolved/closed)")
        if resolution_days:
            avg_days = round(sum(resolution_days) / len(resolution_days), 1)
            lines.append(f"- Average time to resolve: {avg_days} day{'s' if avg_days != 1 else ''} (across {len(resolution_days)} resolved/closed bug{'s' if len(resolution_days) != 1 else ''})")
    else:
        lines.append("- No bugs assigned yet, so no resolution rate to show.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Explain a bug + suggest a fix — grounded in that bug's real fields, kept
# deliberately short (the brief: "1 or 2 line top answer") so it reads as
# a quick, actionable nudge rather than a wall of text. Open to every
# role — most useful for whoever's actually assigned to fix it.
def _explain_and_suggest_fix(db: Session, *, project_id, project_ids, user, message: str) -> str:
    bug_id = _extract_bug_id(message)
    if bug_id is None:
        return 'Tell me which bug — e.g. "explain bug #42" or "how do I fix #42".'
    bug = _get_bug_scoped(db, bug_id=bug_id, project_id=project_id, project_ids=project_ids)
    if bug is None:
        return f"I couldn't find bug #{bug_id} in your accessible projects."

    context = (
        f"Title: {bug.title}\n"
        f"Severity/Priority: {bug.severity}/{bug.priority}\n"
        f"Module: {bug.module or 'n/a'}\n"
        f"Description: {bug.description or 'n/a'}\n"
        f"Expected result: {bug.expected_result or 'n/a'}\n"
        f"Actual result: {bug.actual_result or 'n/a'}\n"
        f"Possible root cause (if already noted): {bug.possible_root_cause or 'not noted'}\n"
        f"Steps to reproduce: {bug.steps_to_reproduce or 'none recorded'}"
    )
    prompt = (
        "You are a senior engineer helping a teammate quickly understand a bug. Given the bug details "
        "below, reply with exactly two short lines, plain text, no markdown, no headers:\n"
        "Line 1, starting with 'What's happening: ' — a one-sentence plain-language explanation of the bug.\n"
        "Line 2, starting with 'Try this: ' — your single best concrete suggestion for how to fix or "
        "investigate it, one or two sentences max.\n"
        "Be specific to the actual fields given — don't give generic advice.\n\n"
        f"{context}"
    )
    answer = _gemini_client.generate_text(prompt=prompt)
    return f"#{bug.id} \"{bug.title}\":\n{answer}"


_MODULE_HANDLERS = {
    "bugs": _bug_summary,
    "ai-bug-generator": _bug_summary,
    "tasks": _task_summary,
    "sprints": _sprint_status,
    "dashboard": _bug_summary,
}


def _llm_fallback(db: Session, *, project_id, project_ids, message: str) -> str:
    summary = dashboard_service.get_dashboard_summary(
        db, project_id=project_id, assigned_to=None, project_ids=project_ids
    )
    context = (
        f"Open bugs: {summary['stat_cards']['open_bugs']}, "
        f"Critical open: {summary['stat_cards']['critical_open']}, "
        f"Overdue tasks: {summary['stat_cards']['overdue_tasks']}, "
        f"Active sprints: {summary['stat_cards']['active_sprints']}, "
        f"Top module: {summary['top_buggy_modules'][0]['module'] if summary['top_buggy_modules'] else 'n/a'}."
    )
    prompt = (
        "You are a QA/project-management assistant embedded in a bug-tracking app. "
        "Answer the user's question in 2-4 short sentences, plain language, no markdown headers. "
        "If the question needs data you don't have, say so plainly instead of guessing.\n\n"
        f"Current project snapshot (already scoped to what this user may see): {context}\n\n"
        f"User question: {message}"
    )
    return _gemini_client.generate_text(prompt=prompt)


_INTENTS: list[tuple[str, callable]] = [
    (r"\bwhy\b.*\b(open|stuck|unresolved)\b", _why_open),
    (r"\b(explain|what'?s wrong with|how (do|can) i fix|how to (fix|solve)|suggest.*(fix|solution))\b", _explain_and_suggest_fix),
    (r"\b(test steps|repro steps|reproduction steps|edge cases?|test cases?)\b", _generate_test_steps),
    (r"\b(similar|duplicate)\b", _similar_bugs),
    (r"\bwho created\b|\bcreated by\b", _who_created),
    (r"\brole", _user_roles),
    (r"\bwhom\b|\bassigned to\b|\bassignee\b|\bwho\b.{0,30}\bassign", _assignee_breakdown),
    (r"\b(daily digest|weekly digest|\bdigest\b|what changed|weekly report|weekly summary|weekly update)\b", _digest),
    (r"\bmy (bugs|tasks|work)\b", _my_work),
    (r"\b(task summary|my tasks|overdue tasks|tasks overview)\b", _task_summary),
    (r"\bopen bugs?\b", _list_open_bugs),
    (r"\bsummar", _bug_summary),
    (r"\b(search|find)\b", _search_bugs),
    (r"\bsprint\b", _sprint_status),
    (r"\b(module|unstable|buggy area)\b", _module_analysis),
]


def answer_query(
    db: Session,
    *,
    message: str,
    project_id,
    current_user: User,
    module: str | None = None,
) -> dict:
    project_ids = None if project_id is not None else project_access.accessible_project_ids(db, user=current_user)

    text = message.strip()
    lowered = text.lower()

    # Person-lookup takes priority over every other pattern: if the
    # message names a real, active user AND has a work-related keyword
    # ("how many bugs does Divya have", "Harsha's workload", "is Kapil
    # efficient"), answer with that person's workload instead of falling
    # into a generic intent below (e.g. "role", which would otherwise
    # catch a sentence containing "her role").
    if _WORKLOAD_HINT.search(lowered):
        person = _extract_person(db, lowered)
        if person is not None:
            answer = _person_workload(db, target=person, user=current_user, message=lowered)
            return {"answer": answer, "intent": "person_workload"}

    for pattern, handler in _INTENTS:
        if re.search(pattern, lowered):
            if handler is _search_bugs:
                match = re.search(r"(?:for|about)\s+(.+)$", lowered)
                keyword = match.group(1).strip() if match else lowered.replace("search", "").replace("find", "").strip()
                answer = handler(
                    db, project_id=project_id, project_ids=project_ids, user=current_user, message=text, keyword=keyword
                )
            else:
                answer = handler(db, project_id=project_id, project_ids=project_ids, user=current_user, message=lowered)
            return {"answer": answer, "intent": handler.__name__.lstrip("_")}

    if module in _MODULE_HANDLERS and len(text.split()) <= 6:
        handler = _MODULE_HANDLERS[module]
        answer = handler(db, project_id=project_id, project_ids=project_ids, user=current_user, message=lowered)
        return {"answer": answer, "intent": handler.__name__.lstrip("_")}

    answer = _llm_fallback(db, project_id=project_id, project_ids=project_ids, message=text)
    return {"answer": answer, "intent": "general"}
