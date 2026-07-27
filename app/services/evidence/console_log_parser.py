"""
Console log evidence handling.

Trivial today (trim + length-cap), but isolated in its own module so
console log-specific parsing (e.g. splitting log levels, extracting
timestamps) can be added later without touching the evidence merger
or the prompt builder.
"""
from typing import Optional

from app.config import settings


def parse_console_log(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    return cleaned[: settings.max_text_field_chars]
