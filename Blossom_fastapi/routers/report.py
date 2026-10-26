from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database.database import get_db
from database import db_report
from routers.schemas import UserAuth, ReportCreate

router = APIRouter(
    prefix="/reports",
    tags=["Reports"]
)


def _require_admin(user):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("")
def report_profile(
    request: ReportCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    """A member reports another; the admins get a notification."""
    return db_report.create_report(db, current_user.id, request.reported_profile_id, request.reason, background_tasks)


@router.get("/admin")
def admin_reports(all: bool = False, db: Session = Depends(get_db), current_user: UserAuth = Depends(get_current_user)):
    """Admin: reports not handled yet (all=true: every report)."""
    _require_admin(current_user)
    return db_report.list_reports(db, include_handled=all)


@router.post("/admin/{report_id}/handled")
def report_handled(report_id: int, db: Session = Depends(get_db), current_user: UserAuth = Depends(get_current_user)):
    _require_admin(current_user)
    return db_report.set_handled(db, report_id, True)
