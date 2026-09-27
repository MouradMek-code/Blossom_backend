from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database import db_offers, db_push
from database.database import get_db
from database.models import DbProfile
from routers.schemas import MessageDisplay, UserAuth

# Venue promotions for couples: admins publish them on date spots, a matched
# couple gets one by saying yes to an invite there. See database/db_offers.py.
router = APIRouter(
    prefix="/offers",
    tags=["promotions"],
)


class OfferCreate(BaseModel):
    spot_id: int
    title: str = Field(max_length=120)
    details: Optional[str] = Field(default=None, max_length=500)
    max_couples: Optional[int] = None  # empty = no limit
    ends_at: datetime  # open to new couples until then
    valid_hours: int  # then each couple has this long to use it
    staff_code: Optional[str] = Field(default=None, max_length=8)  # generated when empty


class OfferUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)
    details: Optional[str] = Field(default=None, max_length=500)
    max_couples: Optional[int] = None
    ends_at: Optional[datetime] = None
    valid_hours: Optional[int] = None
    staff_code: Optional[str] = Field(default=None, max_length=8)
    active: Optional[bool] = None


class RedeemIn(BaseModel):
    staff_code: str = Field(max_length=8)


def _utc(value: datetime) -> datetime:
    """Stored as naive UTC like every other date here."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _require_admin(user: UserAuth):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")


def _my_profile(db: Session, user: UserAuth) -> DbProfile:
    profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Finish creating your profile first.")
    return profile


# ---- admin ---------------------------------------------------------------------

@router.get("/admin")
def admin_list(db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    """Every promotion, with how many couples got it, used it, let it expire."""
    _require_admin(user)
    return db_offers.list_offers(db)


@router.post("/admin")
def admin_create(payload: OfferCreate, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_offers.create_offer(
        db, payload.spot_id, payload.title, payload.details, payload.max_couples,
        _utc(payload.ends_at), payload.valid_hours, payload.staff_code,
    )


@router.patch("/admin/{offer_id}")
def admin_update(offer_id: int, payload: OfferUpdate, db: Session = Depends(get_db),
                 user: UserAuth = Depends(get_current_user)):
    """Only the fields sent change - e.g. {"active": false} pauses it."""
    _require_admin(user)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("ends_at") is not None:
        changes["ends_at"] = _utc(changes["ends_at"])
    return db_offers.update_offer(db, offer_id, changes)


# ---- couples -------------------------------------------------------------------

@router.post("/invites/{message_id}/accept")
def accept_invite(message_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                  user: UserAuth = Depends(get_current_user)):
    """"I'm in" on a date spot invite. If the spot has a promotion still open,
    the couple gets it (see reason when they don't)."""
    profile = _my_profile(db, user)
    result = db_offers.accept_invite(db, message_id, profile)
    message = result["message"]
    voucher = result["voucher"]
    if result["first_yes"]:
        db_push.notify_invite_accepted(
            db, background_tasks, message.conversation_id, message.sender_profile_id,
            profile.first_name, message.date_spot.name if message.date_spot else "",
            voucher.offer.title if voucher else None,
        )
    db_offers.decorate_messages(db, [message])
    return {
        "message": MessageDisplay.model_validate(message, from_attributes=True),
        "voucher": db_offers.voucher_view(db, voucher, profile.id) if voucher else None,
        "reason": result["reason"],
    }


@router.get("/vouchers")
def my_vouchers(db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    """My promotions: still to use first, then used, then expired."""
    return db_offers.my_vouchers(db, _my_profile(db, user))


@router.post("/vouchers/{voucher_id}/redeem")
def redeem(voucher_id: int, payload: RedeemIn, db: Session = Depends(get_db),
           user: UserAuth = Depends(get_current_user)):
    """At the venue: the staff type their code on the couple's phone."""
    return db_offers.redeem(db, voucher_id, _my_profile(db, user), payload.staff_code)
