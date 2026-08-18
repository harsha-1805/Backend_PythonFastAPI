"""
Email address validation: local-part shape + domain allow-list.

`EmailStr` (pydantic) already guarantees the address is *shaped* like an
email — it does NOT stop someone from signing up / being invited with a
throwaway or unknown domain like "name@ok.lol", nor does it restrict which
characters are allowed before the "@" (RFC 5321 technically permits many
special characters there). This module is the single place that enforces
both extra rules — local-part character set and domain allow-list — so
signup, self-service profile edit, invite, and "edit user" all share one
rule instead of drifting apart.

Raises ValueError (not HTTPException) so it composes the same way every
other validation error in the service layer does — routers already
translate ValueError -> HTTP 400/409/422 with the message as-is.
"""
import re

from app.config import settings

# The part before "@" — letters, numbers, and dots only. No #, _, -, +,
# or any other special character.
_LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9.]+$")


def validate_email_domain(email: str) -> None:
    if not email or "@" not in email:
        raise ValueError("Enter a valid email address")

    local_part, _, domain = email.rpartition("@")
    domain = domain.strip().lower()

    if not local_part or not _LOCAL_PART_RE.match(local_part):
        raise ValueError(
            "The part of the email before '@' can only contain letters, "
            "numbers, and dots (no #, _, -, or other special characters)"
        )

    allowed = settings.allowed_email_domain_list

    if not allowed:
        return  # allow-list disabled entirely (empty config) — accept anything

    if domain not in allowed:
        pretty = ", ".join(f"@{d}" for d in allowed)
        raise ValueError(
            f"'@{domain}' isn't an accepted email domain. Please use one of: {pretty}"
        )
