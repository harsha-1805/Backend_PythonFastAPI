"""
Email domain allow-list validation.

`EmailStr` (pydantic) already guarantees the address is *shaped* like an
email — it does NOT stop someone from signing up / being invited with a
throwaway or unknown domain like "name@ok.lol". This module is the single
place that enforces the *domain* allow-list (configured via
`settings.allowed_email_domains`) so signup, invite, and "edit user" all
share one rule instead of drifting apart.

Raises ValueError (not HTTPException) so it composes the same way every
other validation error in the service layer does — routers already
translate ValueError -> HTTP 400/409/422 with the message as-is.
"""
from app.config import settings


def validate_email_domain(email: str) -> None:
    if not email or "@" not in email:
        raise ValueError("Enter a valid email address")

    domain = email.rsplit("@", 1)[-1].strip().lower()
    allowed = settings.allowed_email_domain_list

    if not allowed:
        return  # allow-list disabled entirely (empty config) — accept anything

    if domain not in allowed:
        pretty = ", ".join(f"@{d}" for d in allowed)
        raise ValueError(
            f"'@{domain}' isn't an accepted email domain. Please use one of: {pretty}"
        )
