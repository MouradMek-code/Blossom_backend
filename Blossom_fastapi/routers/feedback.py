from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database import db_feedback
from database.database import get_db
from routers.analytics import optional_user
from routers.schemas import UserAuth

router = APIRouter(
    prefix="/feedback",
    tags=["Feedback"],
)


class FeedbackIn(BaseModel):
    kind: str = Field(max_length=20)  # child_safety | scam | harassment | bug | other
    message: str = Field(max_length=4000)
    email: Optional[str] = Field(default=None, max_length=200)  # visitors, to be answered
    about_profile_id: Optional[int] = None  # opened from someone's profile
    language: Optional[str] = Field(default=None, max_length=8)
    website: Optional[str] = None  # hidden field: bots fill it


class HandledIn(BaseModel):
    handled: bool = True


def _require_admin(user):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("")
def report_problem(payload: FeedbackIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                   user=Depends(optional_user)):
    """"Report a problem" in the app or on the website, logged in or not."""
    if payload.website:
        return {"id": None}  # a bot: pretend it worked
    return db_feedback.create(db, user, payload.model_dump(), background_tasks)


@router.get("/admin")
def admin_list(all: bool = False, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_feedback.list_reports(db, include_handled=all)


@router.post("/admin/{report_id}/handled")
def admin_handled(report_id: int, payload: HandledIn, db: Session = Depends(get_db),
                  user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_feedback.set_handled(db, report_id, payload.handled)


@router.delete("/admin/{report_id}")
def admin_delete(report_id: int, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_feedback.delete(db, report_id)
