"""
Screenshot evidence handling.

Gemini 2.5 Flash performs its own OCR/vision reasoning over the raw
image bytes, so this module's job is validation + light normalization
only — NOT running a separate OCR pass ourselves. Keeping that logic
here (rather than inline in the router) means a future evidence type
that also needs image-like handling (e.g. Screen Recording frames,
Crash Dump screenshots) can reuse this validator.
"""
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status

from app.config import settings


@dataclass
class ParsedScreenshot:
    filename: str
    content_type: str
    size_bytes: int
    data: bytes


def validate_and_read_screenshot(file: UploadFile, raw_bytes: bytes) -> ParsedScreenshot:
    if file.content_type not in settings.allowed_image_content_type_list:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported image type '{file.content_type}'. "
                f"Allowed: {', '.join(settings.allowed_image_content_type_list)}"
            ),
        )

    max_bytes = settings.max_image_size_mb * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Screenshot exceeds the {settings.max_image_size_mb}MB limit.",
        )

    if len(raw_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Screenshot file is empty.")

    return ParsedScreenshot(
        filename=file.filename or "screenshot",
        content_type=file.content_type,
        size_bytes=len(raw_bytes),
        data=raw_bytes,
    )
