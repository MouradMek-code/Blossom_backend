from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database.database import get_db
from database import db_report
from routers.schemas import UserAuth, ReportCreate

router = APIRouter(
    prefix="/reports",
    tags=["Reports"]
)


@router.post("")
def report_profile(
    request: ReportCreate,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    return db_report.create_report(db, current_user.id, request.reported_profile_id, request.reason)
