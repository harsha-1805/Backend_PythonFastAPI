"""
Stack trace evidence handling.

Same shape as console_log_parser.py on purpose — kept as a separate
module because stack traces will likely need their own structured
parsing later (frame extraction, language detection) independent of
console log handling.
"""
from typing import Optional

from app.config import settings


def parse_stack_trace(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    return cleaned[: settings.max_text_field_chars]
