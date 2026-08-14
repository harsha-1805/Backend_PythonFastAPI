"""
AI Test Case Generator + persistence layer.

Turns a Task (or a Bug) into a set of structured test cases via Gemini,
formats them as CSV, and optionally saves / lists them from the DB.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Bug, SavedTestCase, SubTask, Task
from app.services.llm.gemini_client import GeminiClient

_gemini_client = GeminiClient()

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

CSV_FIELDS = [
    "Test Case ID",
    "Title",
    "Type",
    "Priority",
    "Preconditions",
    "Steps",
    "Test Data",
    "Expected Result",
]


def _strip_code_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def _image_bytes(image_url: str | None) -> tuple[bytes, str] | None:
    if not image_url or not image_url.startswith(settings.upload_url_prefix):
        return None
    relative = image_url[len(settings.upload_url_prefix):].lstrip("/")
    path = Path(settings.upload_dir) / relative
    if not path.is_file():
        return None
    ext = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        ext, "image/png"
    )
    return path.read_bytes(), mime


def _task_context(db: Session, task: Task) -> tuple[str, list[tuple[bytes, str]]]:
    subtasks = db.query(SubTask).filter(SubTask.task_id == task.id).all()
    subtask_lines = (
        "\n".join(f"  - {st.title} ({st.status})" + (f': {st.description}' if st.description else "") for st in subtasks)
        or "  (none)"
    )

    text = (
        f"Item type: Task\n"
        f"Project: {task.project.name if task.project else 'n/a'}\n"
        f"Sprint: {task.sprint.name if task.sprint else 'n/a'}\n"
        f"Title: {task.title}\n"
        f"Detailed description: {task.description or 'n/a'}\n"
        f"Acceptance criteria: {task.acceptance_criteria or 'n/a'}\n"
        f"Status: {task.status}\n"
        f"Subtasks:\n{subtask_lines}\n"
        f"Reference screenshots attached: {len(task.attachments)}"
    )

    images = []
    for att in task.attachments:
        img = _image_bytes(att.image_url)
        if img:
            images.append(img)
    return text, images


def _subtask_context(subtask: SubTask) -> tuple[str, list[tuple[bytes, str]]]:
    """Build AI context for a SubTask. A subtask has no acceptance
    criteria or attachments of its own — it inherits project/sprint
    context from its parent Task, whose title/description/acceptance
    criteria are included too so the generator understands what the
    subtask is contributing to.
    """
    task = subtask.task
    text = (
        f"Item type: SubTask\n"
        f"Project: {task.project.name if task and task.project else 'n/a'}\n"
        f"Sprint: {task.sprint.name if task and task.sprint else 'n/a'}\n"
        f"Parent task: {task.title if task else 'n/a'}\n"
        f"Parent task description: {task.description or 'n/a' if task else 'n/a'}\n"
        f"Parent task acceptance criteria: {task.acceptance_criteria or 'n/a' if task else 'n/a'}\n"
        f"Title: {subtask.title}\n"
        f"Detailed description: {subtask.description or 'n/a'}\n"
        f"Status: {subtask.status}"
    )
    return text, []


def _bug_context(bug: Bug) -> tuple[str, list[tuple[bytes, str]]]:
    text = (
        f"Item type: Bug\n"
        f"Project: {bug.project.name if bug.project else 'n/a'}\n"
        f"Sprint: {bug.sprint.name if bug.sprint else 'n/a'}\n"
        f"Title: {bug.title}\n"
        f"Module: {bug.module or 'n/a'}\n"
        f"Severity: {bug.severity} / Priority: {bug.priority}\n"
        f"Description: {bug.description or 'n/a'}\n"
        f"Expected result: {bug.expected_result or 'n/a'}\n"
        f"Actual result: {bug.actual_result or 'n/a'}\n"
        f"Existing repro steps: {bug.steps_to_reproduce or 'n/a'}\n"
        f"Screenshot attached: {'yes' if bug.image_url else 'no'}"
    )
    images = []
    img = _image_bytes(bug.image_url)
    if img:
        images.append(img)
    return text, images


def _build_prompt(context_text: str) -> str:
    return (
        "You are a senior QA engineer writing a test case suite for the item described below. "
        "Analyze the title, detailed description, acceptance criteria, subtasks, and any attached "
        "screenshots together — do not invent functionality that isn't implied by them.\n\n"
        "Produce 5 to 12 test cases that give strong, non-redundant coverage:\n"
        "- Include positive (happy path), negative (invalid input/error handling), and edge cases.\n"
        "- Derive cases directly from each acceptance criterion where given — every criterion should "
        "be covered by at least one case.\n"
        "- If screenshots are attached, ground UI-related steps in what's actually visible in them.\n"
        "- Steps must be concrete and numbered (e.g. \"1. Navigate to... 2. Enter... 3. Click...\").\n"
        "- Keep each field concise — this will be exported to CSV.\n\n"
        "Return ONLY a JSON array (no markdown, no commentary) where each element has exactly these "
        "string keys: \"title\", \"type\" (Positive | Negative | Edge Case), "
        "\"priority\" (High | Medium | Low), \"preconditions\", \"steps\", \"test_data\", "
        "\"expected_result\".\n\n"
        f"{context_text}"
    )


def _build_regenerate_prompt(context_text: str, feedback: str) -> str:
    return (
        "You are a senior QA engineer revising a test case suite based on reviewer feedback.\n\n"
        "ORIGINAL ITEM CONTEXT:\n"
        f"{context_text}\n\n"
        "REVIEWER FEEDBACK (what was wrong / what to change or add):\n"
        f"{feedback}\n\n"
        "Produce a REVISED set of 5 to 12 test cases that:\n"
        "- Directly address every point raised in the reviewer feedback.\n"
        "- Keep valid test cases from the implied original set where they still apply.\n"
        "- Include positive (happy path), negative (invalid input/error handling), and edge cases.\n"
        "- Derive cases from each acceptance criterion where given.\n"
        "- Use concrete, numbered steps.\n\n"
        "Return ONLY a JSON array (no markdown, no commentary) where each element has exactly these "
        "string keys: \"title\", \"type\" (Positive | Negative | Edge Case), "
        "\"priority\" (High | Medium | Low), \"preconditions\", \"steps\", \"test_data\", "
        "\"expected_result\"."
    )


def _parse_test_cases(raw_text: str) -> list[dict]:
    cleaned = _strip_code_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = data.get("test_cases") or data.get("testCases") or []
    if not isinstance(data, list):
        return []

    rows = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Test Case ID": f"TC-{i:03d}",
                "Title": str(item.get("title") or "").strip(),
                "Type": str(item.get("type") or "").strip() or "Functional",
                "Priority": str(item.get("priority") or "").strip() or "Medium",
                "Preconditions": str(item.get("preconditions") or "").strip(),
                "Steps": str(item.get("steps") or "").strip(),
                "Test Data": str(item.get("test_data") or item.get("testData") or "").strip(),
                "Expected Result": str(item.get("expected_result") or item.get("expectedResult") or "").strip(),
            }
        )
    return [r for r in rows if r["Title"]]


def generate(db: Session, *, entity_type: str, entity_id: int) -> tuple[str, list[dict]]:
    """Returns (entity_title, rows) — rows already normalized to
    CSV_FIELDS keys, ready for either JSON preview or `to_csv()`.
    """
    if entity_type == "task":
        task = db.query(Task).filter(Task.id == entity_id).first()
        if task is None:
            raise LookupError("Task not found")
        context_text, images = _task_context(db, task)
        entity_title = task.title
    elif entity_type == "bug":
        bug = db.query(Bug).filter(Bug.id == entity_id).first()
        if bug is None:
            raise LookupError("Bug not found")
        context_text, images = _bug_context(bug)
        entity_title = bug.title
    elif entity_type == "subtask":
        subtask = db.query(SubTask).filter(SubTask.id == entity_id).first()
        if subtask is None:
            raise LookupError("Subtask not found")
        context_text, images = _subtask_context(subtask)
        entity_title = subtask.title
    else:
        raise ValueError("entity_type must be 'task', 'bug', or 'subtask'")

    prompt = _build_prompt(context_text)
    raw = _gemini_client.generate_json(prompt=prompt, images=images)
    rows = _parse_test_cases(raw)
    return entity_title, rows


def regenerate(db: Session, *, entity_type: str, entity_id: int, feedback: str) -> tuple[str, list[dict]]:
    """Like generate() but incorporates user feedback to fix/improve
    the previous result — the model sees the full item context again
    PLUS the reviewer's notes, so it can correct specific problems."""
    if entity_type == "task":
        task = db.query(Task).filter(Task.id == entity_id).first()
        if task is None:
            raise LookupError("Task not found")
        context_text, images = _task_context(db, task)
        entity_title = task.title
    elif entity_type == "bug":
        bug = db.query(Bug).filter(Bug.id == entity_id).first()
        if bug is None:
            raise LookupError("Bug not found")
        context_text, images = _bug_context(bug)
        entity_title = bug.title
    elif entity_type == "subtask":
        subtask = db.query(SubTask).filter(SubTask.id == entity_id).first()
        if subtask is None:
            raise LookupError("Subtask not found")
        context_text, images = _subtask_context(subtask)
        entity_title = subtask.title
    else:
        raise ValueError("entity_type must be 'task', 'bug', or 'subtask'")

    prompt = _build_regenerate_prompt(context_text, feedback)
    raw = _gemini_client.generate_json(prompt=prompt, images=images)
    rows = _parse_test_cases(raw)
    return entity_title, rows


def save_test_cases(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    entity_title: str,
    project_id: int,
    test_cases: list[dict],
    csv_data: str,
    saved_by_id: int,
) -> SavedTestCase:
    """Persist a generated test case set to the DB so it can be accessed
    later from the Test Cases Library (Tasks page and dedicated view)."""
    task_id = entity_id if entity_type == "task" else None
    bug_id = entity_id if entity_type == "bug" else None
    subtask_id = entity_id if entity_type == "subtask" else None

    record = SavedTestCase(
        project_id=project_id,
        task_id=task_id,
        bug_id=bug_id,
        subtask_id=subtask_id,
        entity_type=entity_type,
        entity_title=entity_title,
        csv_data=csv_data,
        test_cases_json=json.dumps(test_cases),
        saved_by=saved_by_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_saved_test_cases(
    db: Session,
    *,
    project_id: int | None = None,
    task_id: int | None = None,
    bug_id: int | None = None,
    subtask_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[SavedTestCase]:
    q = db.query(SavedTestCase)
    if project_id:
        q = q.filter(SavedTestCase.project_id == project_id)
    if task_id:
        q = q.filter(SavedTestCase.task_id == task_id)
    if bug_id:
        q = q.filter(SavedTestCase.bug_id == bug_id)
    if subtask_id:
        q = q.filter(SavedTestCase.subtask_id == subtask_id)
    return q.order_by(SavedTestCase.created_at.desc()).offset(skip).limit(limit).all()


def delete_saved_test_case(db: Session, *, record_id: int) -> bool:
    record = db.query(SavedTestCase).filter(SavedTestCase.id == record_id).first()
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True


def to_csv(entity_title: str, rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
