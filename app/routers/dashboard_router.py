"""
Dashboard route. Replaces the frontend's old utils/dummyData.js with a
single real payload.

Scoping has two independent layers, same as every other module (see
project_access.py):

  1. Team membership — Admin/Lead see every project's data; everyone
     else (HR/QA/Employee) only sees data for projects they're actually
     a member of (app.services.project_access.accessible_project_ids).
     This was previously missing here entirely, which meant any
     non-Employee-only role (QA, HR, or an Employee with a second role)
     saw the org-wide dashboard regardless of team membership, and even
     a plain Employee could see another team's project by passing its
     project_id directly in the query string.
  2. "Whose work" — on top of the team-membership scope, a plain
     Employee's stat cards additionally narrow to work assigned to them
     specifically (assigned_to), matching the existing product framing
     that Employees see "my work" while Lead/QA/HR see the team view.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User
from app.services import dashboard_service, project_access

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard.view")),
):
    # Team-membership scope: None means "no restriction" (Admin/Lead), a
    # set means "only these project IDs". If a specific project_id was
    # requested, verify the caller may actually access it — raises
    # PermissionError -> 403 via the app-wide handler in main.py.
    if project_id is not None:
        project_access.assert_project_access(db, user=current_user, project_id=project_id)
        project_ids = None  # single-project filter below is enough
    else:
        project_ids = project_access.accessible_project_ids(db, user=current_user)

    role_names = {r.name for r in current_user.roles}
    # On top of team-membership scope, a plain Employee narrows further
    # to their own assigned work; every other role sees the whole
    # (membership-scoped) team/project picture.
    assigned_to = current_user.id if role_names == {"Employee"} else None

    return dashboard_service.get_dashboard_summary(
        db, project_id=project_id, assigned_to=assigned_to, project_ids=project_ids
    )
