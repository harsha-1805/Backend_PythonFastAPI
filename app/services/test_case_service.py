"""
AI Test Case Generator.

Turns a Task (or a Bug) — plus everything attached to it that actually
helps a QA engineer write accurate cases: its acceptance criteria,
subtasks, sprint/project context, and any reference screenshots — into
a set of structured test cases via Gemini, then formats them as CSV
for direct download.

Deliberately grounded, not free-generated: the prompt is built entirely
from real fields already on the Task/Bug (see `_task_context` /
`_bug_context` below) so the output reflects what was actually
specified, not a generic guess at what the feature probably does. This
is exactly why `Task.acceptance_criteria` and `Task.attachments` were
added — a plain title/description alone produces vague, low-signal
cases; acceptance criteria + real screenshots produce specific ones.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Bug, SubTask, Task
from app.services.llm.gemini_client import GeminiClient

_gemini_client = GeminiClient()

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# The columns every generated CSV has, in this order — also doubles as
# the set of keys every row is normalized to before writing, so a
# short/malformed model response never produces a ragged CSV.
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
    """Reads a previously-uploaded screenshot back off disk given its
    public URL path (e.g. "/uploads/tasks/<uuid>.png"), for sending to
    Gemini as multimodal input. Returns None (skips it) rather than
    raising if the file is somehow missing — a missing screenshot
    shouldn't block generation, just reduce its visual grounding.
    """
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
    else:
        raise ValueError("entity_type must be 'task' or 'bug'")

    prompt = _build_prompt(context_text)
    raw = _gemini_client.generate_json(prompt=prompt, images=images)
    rows = _parse_test_cases(raw)
    return entity_title, rows


def to_csv(entity_title: str, rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
