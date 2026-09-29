from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database import db_analytics
from database.database import get_db
from routers.schemas import UserAuth

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
)


class VisitIn(BaseModel):
    device_id: str
    platform: str = "web"
    entry: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None


def optional_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """The logged-in user if the request carries a valid token, else None -
    visits are recorded for everyone, logged in or not."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token or token in ("null", "undefined"):
        return None
    try:
        return get_current_user(token=token, db=db)
    except HTTPException:
        return None


@router.post("/visit")
def record_visit(
    payload: VisitIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(optional_user),
):
    """Sent by the app and the website when they're opened (and on login).
    Admins are never counted; see database/db_analytics.py for the rules."""
    return db_analytics.record_visit(
        db, user, payload.device_id, payload.platform,
        entry=payload.entry, language=payload.language, timezone=payload.timezone,
        user_agent=request.headers.get("user-agent", ""),
    )


@router.get("/dashboard")
def get_dashboard(
    days: int = Query(30, ge=1, le=365),
    tz_offset: int = Query(0, description="Minutes ahead of UTC, e.g. 120 for Paris in summer"),
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Admins only: visitors, new members and where they come from."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return db_analytics.dashboard(db, days, tz_offset)


@router.get("/day")
def get_day(
    day: Optional[date] = Query(None, description="YYYY-MM-DD in the admin's time zone; today when empty"),
    tz_offset: int = Query(0, description="Minutes ahead of UTC, e.g. 120 for Paris in summer"),
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Admins only: one day in detail - each person, the pages they saw and
    what members did (counts only)."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return db_analytics.day_detail(db, day, tz_offset)
