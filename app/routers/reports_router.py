"""
Reports routes: on-screen analytics (JSON) + CSV export, both filterable
by project and date range. "reports.view" gates the JSON endpoints the
same way it already gates the Reports nav item; CSV export reuses the
same permission — exporting is just a different rendering of the same
data someone's already allowed to see on screen.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.services import reports_service

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.get("/bug-analytics")
def bug_analytics(
    project_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports.view")),
):
    return reports_service.bug_analytics(db, project_id=project_id, date_from=date_from, date_to=date_to)


@router.get("/sprint-report")
def sprint_report(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports.view")),
):
    return reports_service.sprint_report(db, project_id=project_id)


@router.get("/team-performance")
def team_performance(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports.view")),
):
    return reports_service.team_performance(db, project_id=project_id)


@router.get("/ai-bug-stats")
def ai_bug_stats(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports.view")),
):
    return reports_service.ai_bug_stats(db, project_id=project_id)


@router.get("/export")
def export_report(
    type: str = Query(..., description="bugs | tasks | audit"),
    project_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status: str | None = Query(None, description="Filter (bugs/tasks only)"),
    severity: str | None = Query(None, description="Filter (bugs only)"),
    entity_type: str | None = Query(None, description="Filter (audit only)"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports.view")),
):
    if type == "bugs":
        csv_text = reports_service.export_bugs_csv(
            db, project_id=project_id, date_from=date_from, date_to=date_to, status=status, severity=severity
        )
        filename = "bugs_report.csv"
    elif type == "tasks":
        csv_text = reports_service.export_tasks_csv(
            db, project_id=project_id, date_from=date_from, date_to=date_to, status=status
        )
        filename = "tasks_report.csv"
    else:  # "audit" — and safe fallback for any unrecognized value
        csv_text = reports_service.export_audit_log_csv(
            db, project_id=project_id, entity_type=entity_type, date_from=date_from, date_to=date_to
        )
        filename = "audit_log_report.csv"

    # Prefix with a UTF-8 BOM before encoding. Excel doesn't assume UTF-8
    # for CSV by default — without the BOM it falls back to the system
    # codepage and any non-ASCII character (curly quotes, accented
    # names, etc.) in a title/description renders as garbled symbols
    # instead of the original character.
    csv_bytes = ("\ufeff" + csv_text).encode("utf-8")

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
