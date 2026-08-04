"""
Persists uploaded evidence images (currently: AI Bug Generator
screenshots) to disk so they can be shown as a preview later, wherever
the bug is displayed — not just during the single generate-bug request.

Before this module existed, the uploaded image was read into memory,
sent to Gemini for analysis, and then discarded — nothing was ever
saved, so there was nothing to preview once the bug was stored.
"""
import uuid
from pathlib import Path

from app.config import settings

_EXT_BY_CONTENT_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def save_bug_image(image_bytes: bytes, content_type: str | None, original_filename: str | None) -> str:
    """Writes the bytes to `<upload_dir>/bugs/<uuid><ext>` and returns the
    public URL path (`<upload_url_prefix>/bugs/<uuid><ext>`) the
    frontend can use directly as an <img src>.
    """
    ext = _EXT_BY_CONTENT_TYPE.get((content_type or "").lower())
    if not ext and original_filename and "." in original_filename:
        ext = "." + original_filename.rsplit(".", 1)[-1].lower()
    if not ext:
        ext = ".png"

    bugs_dir = Path(settings.upload_dir) / "bugs"
    bugs_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    (bugs_dir / filename).write_bytes(image_bytes)

    return f"{settings.upload_url_prefix}/bugs/{filename}"
