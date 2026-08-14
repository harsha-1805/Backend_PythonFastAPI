"""
FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload
"""
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.logging_config import configure_logging
from app.routers import (
    admin_router,
    ai_assistant_router,
    ai_bug,
    audit_router,
    auth_router,
    bugs_router,
    dashboard_router,
    projects_router,
    reports_router,
    roles_router,
    sprints_router,
    subtasks_router,
    tasks_router,
    test_cases_router,
)
from app.services.role_service import seed_roles_and_permissions

configure_logging()
logger = logging.getLogger(__name__)

# Table creation: with Alembic wired up (see alembic/ + `alembic upgrade
# head`), migrations are the source of truth for schema changes. This
# create_all() call is kept only as a harmless safety net for a fresh
# dev DB someone forgot to migrate — it no-ops on any table that already
# exists, so it never conflicts with Alembic-managed tables.
Base.metadata.create_all(bind=engine)

# Make sure the uploads directory (and its "bugs" subfolder, used by the
# AI Bug Generator to persist evidence screenshots) exists before we try
# to mount it as static files below.
Path(settings.upload_dir, "bugs").mkdir(parents=True, exist_ok=True)
Path(settings.upload_dir, "tasks").mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    description="AI-powered Bug Intelligence and QA Management Platform API",
    version="1.0.0",
)

#allow_origins=settings.cors_origin_list,

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging — every request gets a short ID (also attached to the
# response headers) so a specific failed call can be grepped straight
# out of the logs, including in the error handlers below.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    request.state.request_id = request_id
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 — logged then re-raised to the handlers below
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.exception(
            "[%s] %s %s failed after %sms", request_id, request.method, request.url.path, duration_ms
        )
        raise
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    logger.info(
        "[%s] %s %s -> %s (%sms)",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Global exception handlers — the professional alternative to wrapping
# every single route in try/except. Every router already raises
# ValueError ("bad email domain"), LookupError ("project not found"),
# or (new, for project team-membership checks) PermissionError for
# expected business-rule failures; some routers translate these to
# HTTPException locally for a custom message, but any route that
# doesn't gets a correct, clean response here instead of a raw 500 or
# an unhandled crash. A genuinely unexpected exception (a real bug)
# still gets logged with a full traceback and a request ID, but the
# client only ever sees a safe, generic message — never internals.
# ---------------------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.exception_handler(LookupError)
async def lookup_error_handler(request: Request, exc: LookupError):
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "-")
    logger.info("[%s] Validation error on %s: %s", request_id, request.url.path, exc.errors())
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(request: Request, exc: SQLAlchemyError):
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("[%s] Database error on %s", request_id, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "A database error occurred. This has been logged — please try again."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("[%s] Unhandled error on %s", request_id, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong on our end. This has been logged — please try again."},
    )


# Serves uploaded evidence images (e.g. /uploads/bugs/<uuid>.png) so the
# frontend can render them directly as <img src="{API_BASE}/uploads/...">.
app.mount(settings.upload_url_prefix, StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(auth_router.router)
app.include_router(ai_bug.router)
app.include_router(admin_router.router)
app.include_router(roles_router.router)
app.include_router(projects_router.router)
app.include_router(bugs_router.router)
app.include_router(tasks_router.router)
app.include_router(subtasks_router.router)
app.include_router(sprints_router.router)
app.include_router(audit_router.router)
app.include_router(dashboard_router.router)
app.include_router(reports_router.router)
app.include_router(ai_assistant_router.router)
app.include_router(test_cases_router.router)


@app.on_event("startup")
def seed_defaults() -> None:
    """Idempotently seed the default RBAC roles + permissions (Phase 3).

    Runs on every startup; only inserts rows that don't exist yet, so
    it's safe against being called repeatedly (every `uvicorn --reload`).
    """
    db = SessionLocal()
    try:
        seed_roles_and_permissions(db)
    except SQLAlchemyError:
        logger.exception("Failed to seed default roles/permissions on startup")
    finally:
        db.close()


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": settings.app_name}
