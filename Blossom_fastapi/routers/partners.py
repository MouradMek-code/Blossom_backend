from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database import db_partners
from database.database import get_db
from routers.schemas import UserAuth

# "Partner with Blossom": venues ask to offer a promotion to couples; admins
# approve or refuse; each venue manages its offers with a private link.
# See database/db_partners.py.
router = APIRouter(
    prefix="/partners",
    tags=["partners"],
)


def _utc(value: Optional[datetime]):
    if value is not None and value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class PartnerRequestIn(BaseModel):
    venue_name: str = Field(max_length=150)
    map_url: Optional[str] = Field(default=None, max_length=500)
    city: str = Field(max_length=120)
    country: str = Field(max_length=120)
    about: Optional[str] = Field(default=None, max_length=1000)
    offer_title: str = Field(max_length=120)
    offer_details: Optional[str] = Field(default=None, max_length=500)
    max_couples: Optional[int] = None
    ends_at: Optional[datetime] = None
    valid_hours: Optional[int] = None
    contact_name: Optional[str] = Field(default=None, max_length=120)
    contact_email: str = Field(max_length=200)
    contact_phone: Optional[str] = Field(default=None, max_length=40)
    message: Optional[str] = Field(default=None, max_length=1000)
    language: Optional[str] = Field(default=None, max_length=8)
    # Left empty by people; bots fill every field.
    website: Optional[str] = None


class NewOfferIn(BaseModel):
    offer_title: str = Field(max_length=120)
    offer_details: Optional[str] = Field(default=None, max_length=500)
    max_couples: Optional[int] = None
    ends_at: Optional[datetime] = None
    valid_hours: Optional[int] = None
    message: Optional[str] = Field(default=None, max_length=1000)


class ApproveIn(BaseModel):
    """Anything the admin corrects before publishing; spot_id links an
    existing spot instead of creating one."""
    venue_name: Optional[str] = Field(default=None, max_length=150)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    about: Optional[str] = Field(default=None, max_length=1000)
    offer_title: Optional[str] = Field(default=None, max_length=120)
    offer_details: Optional[str] = Field(default=None, max_length=500)
    max_couples: Optional[int] = None
    ends_at: Optional[datetime] = None
    valid_hours: Optional[int] = None
    spot_id: Optional[int] = None


class RefuseIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class ManagerOfferUpdate(BaseModel):
    active: Optional[bool] = None
    max_couples: Optional[int] = None
    ends_at: Optional[datetime] = None


def _require_admin(user: UserAuth):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")


# ---- the public form ------------------------------------------------------------

@router.post("/requests")
def send_request(payload: PartnerRequestIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """blossom-date.com/partner - no account needed."""
    if payload.website:
        return {"id": None, "status": "pending"}  # a bot: pretend it worked
    data = payload.model_dump()
    data["ends_at"] = _utc(data.get("ends_at"))
    return db_partners.create_request(db, background_tasks, data)


# ---- admins ----------------------------------------------------------------------

@router.get("/requests")
def list_requests(db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_partners.list_requests(db)


@router.post("/requests/{request_id}/approve")
def approve(request_id: int, payload: ApproveIn, background_tasks: BackgroundTasks,
            db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("ends_at") is not None:
        changes["ends_at"] = _utc(changes["ends_at"])
    return db_partners.approve(db, background_tasks, request_id, changes)


@router.post("/requests/{request_id}/refuse")
def refuse(request_id: int, payload: RefuseIn, background_tasks: BackgroundTasks,
           db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_partners.refuse(db, background_tasks, request_id, payload.reason)


@router.get("/venues")
def list_venues(db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_partners.list_venues(db)


@router.post("/venues/{venue_id}/new_link")
def new_link(venue_id: int, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    """The old manager link stops working at once."""
    _require_admin(user)
    return db_partners.new_link(db, venue_id)


# ---- the venue's manager page (the private link is the key) ----------------------

@router.get("/manage/{token}")
def manage(token: str, db: Session = Depends(get_db)):
    return db_partners.manager_view(db, db_partners.venue_by_token(db, token))


@router.patch("/manage/{token}/offers/{offer_id}")
def manage_offer(token: str, offer_id: int, payload: ManagerOfferUpdate, db: Session = Depends(get_db)):
    """Pause, resume, add places, change the end date - at once."""
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("ends_at") is not None:
        changes["ends_at"] = _utc(changes["ends_at"])
    return db_partners.manager_update_offer(db, db_partners.venue_by_token(db, token), offer_id, changes)


@router.post("/manage/{token}/requests")
def manage_new_offer(token: str, payload: NewOfferIn, background_tasks: BackgroundTasks,
                     db: Session = Depends(get_db)):
    """A new offer: comes to the admins as a request."""
    venue = db_partners.venue_by_token(db, token)
    data = payload.model_dump()
    data["ends_at"] = _utc(data.get("ends_at"))
    return db_partners.create_request(db, background_tasks, data, venue=venue)
