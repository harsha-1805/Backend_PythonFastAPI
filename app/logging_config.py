"""
Centralized logging setup, imported once from main.py at startup.

Professional pattern used here (rather than sprinkling
try/except+print in every single route): configure one root logger
format, let every module get its own logger via
`logging.getLogger(__name__)`, and catch truly unexpected exceptions
at TWO layers:

  1. Service layer (project_service.py, bug_service.py, etc.) — wraps
     the actual DB write (commit) in try/except SQLAlchemyError, logs
     the real error with a traceback, rolls back the session, and
     raises a clean RuntimeError so the caller never sees a raw DB
     error. Business-rule errors (ValueError/LookupError/
     PermissionError — "that project doesn't exist", "bad email
     domain", etc.) are NOT swallowed here; they're expected, already
     handled explicitly by each router, and turned into proper 400/
     404/403 responses.
  2. main.py's global exception handler — the final safety net. Any
     exception that isn't one of the expected ValueError/LookupError/
     PermissionError types (i.e. a genuine bug) is caught here, logged
     with a full traceback and a request ID, and turned into a generic
     500 response that never leaks internals to the client.

This avoids the anti-pattern of copy-pasting the same try/except
boilerplate into 30+ endpoint functions while still guaranteeing every
API call is logged and never returns a raw traceback.
"""
import logging
import sys


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. reloaded by uvicorn --reload)

    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    # Quiet down noisy third-party loggers so ours are easy to spot.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
