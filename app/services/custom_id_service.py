"""
Custom ID generation for projects, bugs, tasks and subtasks.

Each project gets a 2-4 character shortcode derived from its name:
  "Mumbai Development"  -> "MD"
  "Payments"            -> "PAY"
  "QA Testing"          -> "QT"

Bugs in that project are numbered sequentially: MD-1, MD-2, MD-3 ...
Tasks:    MD-1T, MD-2T ...
Subtasks: MD-1T-1S, MD-1T-2S ...

Shortcodes are generated once at project creation and stored on the
Project row so renames don't silently invalidate old IDs.
"""
import re

from sqlalchemy.orm import Session

from app.models import Bug, Project, SubTask, Task


# ---------------------------------------------------------------------------
# Shortcode derivation
# ---------------------------------------------------------------------------

def _derive_shortcode(name: str) -> str:
    """Produce a 2-4 letter uppercased shortcode from a project name.

    Strategy:
    1. Take the first letter of each word (initials) — capped at 4.
    2. If only one word, take up to the first 4 alphanumeric characters.
    3. Ensure at least 2 chars by padding from the first word.
    """
    words = re.split(r"[\s\-_]+", name.strip())
    words = [w for w in words if w]

    if not words:
        return "PR"

    initials = "".join(w[0].upper() for w in words)[:4]

    if len(initials) < 2:
        # Single-word project — take more characters
        initials = re.sub(r"[^A-Za-z0-9]", "", words[0]).upper()[:4]
        if len(initials) < 2:
            initials = (initials + "PR")[:2]

    return initials


def generate_shortcode(db: Session, name: str) -> str:
    """Return a unique shortcode for *name*, appending a digit if there is a clash."""
    base = _derive_shortcode(name)
    candidate = base
    suffix = 1
    existing_codes = {
        row[0]
        for row in db.query(Project.shortcode).filter(Project.shortcode.isnot(None)).all()
    }
    while candidate in existing_codes:
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


# ---------------------------------------------------------------------------
# Sequential counters per project
# ---------------------------------------------------------------------------

def next_bug_custom_id(db: Session, project: Project) -> str:
    """Return the next bug custom ID for the project, e.g. 'MD-3'."""
    shortcode = project.shortcode or _derive_shortcode(project.name)
    count = db.query(Bug).filter(Bug.project_id == project.id).count()
    return f"{shortcode}-{count + 1}"


def next_task_custom_id(db: Session, project: Project) -> str:
    """Return the next task custom ID for the project, e.g. 'MD-2T'."""
    shortcode = project.shortcode or _derive_shortcode(project.name)
    count = db.query(Task).filter(Task.project_id == project.id).count()
    return f"{shortcode}-{count + 1}T"


def next_subtask_custom_id(db: Session, parent_task: Task) -> str:
    """Return the next subtask custom ID under parent_task, e.g. 'MD-2T-1S'."""
    task_prefix = parent_task.custom_id or f"T{parent_task.id}"
    count = db.query(SubTask).filter(SubTask.task_id == parent_task.id).count()
    return f"{task_prefix}-{count + 1}S"
