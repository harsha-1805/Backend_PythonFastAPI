"""
Evidence merger.

Single place that assembles every piece of uploaded evidence (today:
screenshot + optional text fields) into one normalized `MergedEvidence`
object. `prompt_builder.py` consumes this object and never talks to
the individual parsers directly — so adding a new evidence type later
(Screen Recording, HAR File, Playwright Trace, ...) only means: write a
new parser module in this package, add one field here, and extend the
prompt builder. Nothing else in the AI pipeline needs to change.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import UploadFile

from app.services.evidence.console_log_parser import parse_console_log
from app.services.evidence.screenshot_parser import ParsedScreenshot, validate_and_read_screenshot
from app.services.evidence.stacktrace_parser import parse_stack_trace


@dataclass
class MergedEvidence:
    screenshot: ParsedScreenshot
    console_log: Optional[str]
    stack_trace: Optional[str]
    user_description: Optional[str]
    browser_url: Optional[str]

    # --- Architecture placeholders for future evidence types --------------
    # Not implemented yet (see project brief). Adding one of these later
    # is: add the field here + a parser module in services/evidence/ +
    # a section in prompt_builder.py. Nothing else changes.
    screen_recording: Optional[bytes] = None
    har_file: Optional[bytes] = None
    playwright_trace: Optional[bytes] = None
    cypress_report: Optional[bytes] = None
    selenium_report: Optional[bytes] = None
    api_response: Optional[str] = None
    crash_dump: Optional[bytes] = None
    pdf_document: Optional[bytes] = None


def merge_evidence(
    *,
    image: UploadFile,
    image_bytes: bytes,
    console_log: Optional[str],
    stack_trace: Optional[str],
    user_description: Optional[str],
    browser_url: Optional[str],
) -> MergedEvidence:
    screenshot = validate_and_read_screenshot(image, image_bytes)

    return MergedEvidence(
        screenshot=screenshot,
        console_log=parse_console_log(console_log),
        stack_trace=parse_stack_trace(stack_trace),
        user_description=(user_description or "").strip() or None,
        browser_url=(browser_url or "").strip() or None,
    )
