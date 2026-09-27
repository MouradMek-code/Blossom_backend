"""Venue promotions for couples ("-20% for Blossom couples" at a date spot).

How it works:
  * an admin publishes a venue's promotion on a date spot: what it is, for
    how many couples at most (or no limit), until when, how long a couple has
    to use it, and a staff code the venue keeps;
  * one of a matched couple invites the other to the spot in their chat, the
    other taps "I'm in": the couple gets the promotion, first come first
    served, with a code of their own;
  * at the venue they show the code, and the staff type their code on the
    couple's phone to mark it used - once only;
  * a code not used before its deadline is lost; one promotion per person per
    30 days; both profiles must be finished (photos in).
"""
import secrets
from collections import Counter
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database.models import DbDateSpot, DbMessage, DbProfile, DbSpotOffer, DbSpotVoucher

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
ONE_PER = timedelta(days=30)  # one promotion per person per 30 days
MAX_WRONG_STAFF_CODES = 5


def _status(voucher: DbSpotVoucher, now: datetime) -> str:
    if voucher.used_at:
        return "used"
    return "expired" if voucher.expires_at <= now else "active"


def _iso(value):
    return value.isoformat() if value else None


def _claimed_counts(db: Session, offer_ids):
    if not offer_ids:
        return Counter()
    rows = (
        db.query(DbSpotVoucher.offer_id, func.count(DbSpotVoucher.id))
        .filter(DbSpotVoucher.offer_id.in_(offer_ids))
        .group_by(DbSpotVoucher.offer_id)
        .all()
    )
    return Counter(dict(rows))


def public_offers(db: Session, spot_ids, now: datetime = None):
    """{spot_id: what everyone may see of its current promotion} - only
    promotions still open to new couples."""
    now = now or datetime.utcnow()
    spot_ids = list(spot_ids)
    if not spot_ids:
        return {}
    offers = (
        db.query(DbSpotOffer)
        .filter(DbSpotOffer.spot_id.in_(spot_ids), DbSpotOffer.active == True,  # noqa: E712
                DbSpotOffer.ends_at > now)
        .order_by(DbSpotOffer.created_at.desc())
        .all()
    )
    claimed = _claimed_counts(db, [o.id for o in offers])
    result = {}
    for offer in offers:
        if offer.spot_id in result:
            continue  # the newest open one per spot
        remaining = None if offer.max_couples is None else offer.max_couples - claimed[offer.id]
        if remaining is not None and remaining <= 0:
            continue
        result[offer.spot_id] = {
            "id": offer.id,
            "title": offer.title,
            "details": offer.details,
            "remaining": remaining,
            "ends_at": offer.ends_at,
            "valid_hours": offer.valid_hours,
        }
    return result


def voucher_brief(voucher: DbSpotVoucher, now: datetime = None):
    now = now or datetime.utcnow()
    return {
        "id": voucher.id,
        "code": voucher.code,
        "title": voucher.offer.title,
        "details": voucher.offer.details,
        "created_at": voucher.created_at,
        "expires_at": voucher.expires_at,
        "used_at": voucher.used_at,
        "status": _status(voucher, now),
    }


def decorate_messages(db: Session, messages, now: datetime = None):
    """Invite cards in a chat: the spot's current promotion, and the couple's
    code on the invite it came from."""
    now = now or datetime.utcnow()
    invites = [m for m in messages if m.date_spot_id and m.date_spot is not None]
    if not invites:
        return messages
    offers = public_offers(db, {m.date_spot_id for m in invites}, now)
    vouchers = {
        v.message_id: v for v in db.query(DbSpotVoucher)
        .filter(DbSpotVoucher.message_id.in_([m.id for m in invites])).all()
    }
    for m in invites:
        m.date_spot.offer = offers.get(m.date_spot_id)
        voucher = vouchers.get(m.id)
        m.voucher = voucher_brief(voucher, now) if voucher else None
    return messages


def _new_code(db: Session) -> str:
    while True:
        code = "BLSM-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        if not db.query(DbSpotVoucher.id).filter(DbSpotVoucher.code == code).first():
            return code


def accept_invite(db: Session, message_id: int, profile: DbProfile, now: datetime = None):
    """The invited person says "I'm in". Returns {"message", "voucher",
    "reason"}; reason says why there's no promotion (None when there is one,
    or "no_offer" when the spot has none)."""
    from database.db_message import get_conversation_for_profile

    now = now or datetime.utcnow()
    message = db.get(DbMessage, message_id)
    if not message or not message.date_spot_id:
        raise HTTPException(status_code=404, detail="Invite not found.")
    if not get_conversation_for_profile(db, message.conversation_id, profile.id):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation.")
    if message.sender_profile_id == profile.id:
        raise HTTPException(status_code=400, detail="You sent this invite - the other person says yes.")

    first_yes = message.accepted_at is None
    if first_yes:
        message.accepted_at = now
    p1, p2 = sorted((message.sender_profile_id, profile.id))
    result = {"message": message, "voucher": None, "reason": None, "first_yes": first_yes}

    # Lock the promotion so two couples can't take its last place at once.
    offer = (
        db.query(DbSpotOffer)
        .filter(DbSpotOffer.spot_id == message.date_spot_id, DbSpotOffer.active == True,  # noqa: E712
                DbSpotOffer.ends_at > now)
        .order_by(DbSpotOffer.created_at.desc())
        .with_for_update()
        .first()
    )
    if offer is None:
        result["reason"] = "no_offer"
    else:
        existing = (
            db.query(DbSpotVoucher)
            .filter(DbSpotVoucher.offer_id == offer.id, DbSpotVoucher.profile1_id == p1,
                    DbSpotVoucher.profile2_id == p2)
            .first()
        )
        if existing:
            result["voucher"] = existing
        else:
            reason = _cannot_claim(db, offer, p1, p2, now)
            if reason:
                result["reason"] = reason
            else:
                voucher = DbSpotVoucher(
                    offer_id=offer.id, profile1_id=p1, profile2_id=p2, message_id=message.id,
                    code=_new_code(db), created_at=now,
                    # Their own deadline, counted from now (even if the
                    # promotion closes to new couples sooner).
                    expires_at=now + timedelta(hours=offer.valid_hours),
                )
                db.add(voucher)
                result["voucher"] = voucher
    db.commit()
    if result["voucher"] is not None:
        db.refresh(result["voucher"])
    return result


def _cannot_claim(db: Session, offer: DbSpotOffer, p1: int, p2: int, now: datetime):
    if offer.max_couples is not None:
        taken = db.query(func.count(DbSpotVoucher.id)).filter(DbSpotVoucher.offer_id == offer.id).scalar()
        if taken >= offer.max_couples:
            return "all_taken"
    finished = db.query(func.count(DbProfile.id)).filter(
        DbProfile.id.in_([p1, p2]), DbProfile.completed_at.isnot(None)).scalar()
    if finished < 2:
        return "unfinished"
    recent = db.query(DbSpotVoucher.id).filter(
        DbSpotVoucher.created_at > now - ONE_PER,
        or_(DbSpotVoucher.profile1_id.in_([p1, p2]), DbSpotVoucher.profile2_id.in_([p1, p2])),
    ).first()
    if recent:
        return "monthly_limit"
    return None


def _partner_and_spot(db: Session, voucher: DbSpotVoucher, profile_id: int):
    partner_id = voucher.profile2_id if voucher.profile1_id == profile_id else voucher.profile1_id
    partner = db.get(DbProfile, partner_id)
    spot = voucher.offer.spot
    return partner, spot


def voucher_view(db: Session, voucher: DbSpotVoucher, profile_id: int, now: datetime = None):
    partner, spot = _partner_and_spot(db, voucher, profile_id)
    return {
        **voucher_brief(voucher, now),
        "spot": {
            "id": spot.id, "name": spot.name, "city": spot.city, "neighborhood": spot.neighborhood,
            "image_url": spot.image_url, "map_url": spot.map_url,
        } if spot else None,
        "partner": {
            "id": partner.id, "first_name": partner.first_name,
            "photo": partner.photos[0].image_url if partner and partner.photos else None,
        } if partner else None,
    }


def my_vouchers(db: Session, profile: DbProfile, now: datetime = None):
    now = now or datetime.utcnow()
    vouchers = (
        db.query(DbSpotVoucher)
        .filter(or_(DbSpotVoucher.profile1_id == profile.id, DbSpotVoucher.profile2_id == profile.id))
        .order_by(DbSpotVoucher.created_at.desc())
        .all()
    )
    order = {"active": 0, "used": 1, "expired": 2}
    views = [voucher_view(db, v, profile.id, now) for v in vouchers]
    return sorted(views, key=lambda v: order[v["status"]])


def redeem(db: Session, voucher_id: int, profile: DbProfile, staff_code: str, now: datetime = None):
    """The venue's staff type their code on the couple's phone."""
    now = now or datetime.utcnow()
    voucher = db.get(DbSpotVoucher, voucher_id)
    if not voucher or profile.id not in (voucher.profile1_id, voucher.profile2_id):
        raise HTTPException(status_code=404, detail="Promotion not found.")
    if voucher.used_at:
        raise HTTPException(status_code=409, detail="This code was already used.")
    if voucher.expires_at <= now:
        raise HTTPException(status_code=410, detail="This code has expired.")
    if voucher.failed_attempts >= MAX_WRONG_STAFF_CODES:
        raise HTTPException(status_code=429, detail="Too many wrong staff codes. Please contact Blossom.")
    if (staff_code or "").strip() != voucher.offer.staff_code:
        voucher.failed_attempts += 1
        db.commit()
        raise HTTPException(status_code=400, detail="Wrong staff code.")
    voucher.used_at = now
    db.commit()
    return voucher_view(db, voucher, profile.id, now)


# ---- admin -------------------------------------------------------------------

def _clean_text(value, limit):
    value = " ".join(str(value or "").split())
    return value[:limit] or None


def _check(title, ends_at, valid_hours, max_couples, staff_code, now, creating):
    if title is not None and len(title) < 3:
        raise HTTPException(status_code=400, detail="Describe the promotion, e.g. \"-20% on the bill\".")
    if ends_at is not None and creating and ends_at <= now:
        raise HTTPException(status_code=400, detail="The end date must be in the future.")
    if valid_hours is not None and not 1 <= valid_hours <= 24 * 365:
        raise HTTPException(status_code=400, detail="Couples need between 1 hour and a year to use it.")
    if max_couples is not None and not 1 <= max_couples <= 100000:
        raise HTTPException(status_code=400, detail="Number of couples: leave empty for no limit, or 1 or more.")
    if staff_code is not None and not (staff_code.isdigit() and 4 <= len(staff_code) <= 8):
        raise HTTPException(status_code=400, detail="The staff code is 4 to 8 digits.")


def create_offer(db: Session, spot_id: int, title, details, max_couples, ends_at: datetime,
                 valid_hours: int, staff_code=None, now: datetime = None):
    now = now or datetime.utcnow()
    if not db.get(DbDateSpot, spot_id):
        raise HTTPException(status_code=404, detail="Date spot not found.")
    title = _clean_text(title, 120)
    staff_code = (staff_code or "").strip() or "".join(secrets.choice("0123456789") for _ in range(4))
    _check(title or "", ends_at, valid_hours, max_couples, staff_code, now, creating=True)
    offer = DbSpotOffer(
        spot_id=spot_id, title=title, details=_clean_text(details, 500), max_couples=max_couples,
        ends_at=ends_at, valid_hours=valid_hours, staff_code=staff_code, active=True, created_at=now,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return admin_view(db, offer, now)


def update_offer(db: Session, offer_id: int, changes: dict, now: datetime = None):
    now = now or datetime.utcnow()
    offer = db.get(DbSpotOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Promotion not found.")
    if "title" in changes:
        changes["title"] = _clean_text(changes["title"], 120) or ""
    if "details" in changes:
        changes["details"] = _clean_text(changes["details"], 500)
    _check(changes.get("title"), changes.get("ends_at"), changes.get("valid_hours"),
           changes.get("max_couples"), changes.get("staff_code"), now, creating=False)
    for key in ("title", "details", "max_couples", "ends_at", "valid_hours", "staff_code", "active"):
        if key in changes:
            setattr(offer, key, changes[key])
    db.commit()
    return admin_view(db, offer, now)


def admin_view(db: Session, offer: DbSpotOffer, now: datetime = None):
    now = now or datetime.utcnow()
    vouchers = (
        db.query(DbSpotVoucher).filter(DbSpotVoucher.offer_id == offer.id)
        .order_by(DbSpotVoucher.created_at.desc()).all()
    )
    names = {
        pid: name for pid, name in db.query(DbProfile.id, DbProfile.first_name).filter(
            DbProfile.id.in_({v.profile1_id for v in vouchers} | {v.profile2_id for v in vouchers})
        ).all()
    } if vouchers else {}
    statuses = Counter(_status(v, now) for v in vouchers)
    if not offer.active:
        state = "paused"
    elif offer.ends_at <= now:
        state = "ended"
    elif offer.max_couples is not None and len(vouchers) >= offer.max_couples:
        state = "full"
    else:
        state = "open"
    return {
        "id": offer.id,
        "spot": {"id": offer.spot.id, "name": offer.spot.name, "city": offer.spot.city} if offer.spot else None,
        "title": offer.title,
        "details": offer.details,
        "max_couples": offer.max_couples,
        "ends_at": offer.ends_at,
        "valid_hours": offer.valid_hours,
        "staff_code": offer.staff_code,
        "active": offer.active,
        "state": state,
        "created_at": offer.created_at,
        "stats": {
            "claimed": len(vouchers),
            "used": statuses["used"],
            "waiting": statuses["active"],
            "expired": statuses["expired"],
            "remaining": None if offer.max_couples is None else max(0, offer.max_couples - len(vouchers)),
        },
        "couples": [
            {
                "code": v.code,
                "names": [names.get(v.profile1_id, "?"), names.get(v.profile2_id, "?")],
                "created_at": v.created_at,
                "expires_at": v.expires_at,
                "used_at": v.used_at,
                "status": _status(v, now),
            }
            for v in vouchers
        ],
    }


def list_offers(db: Session, now: datetime = None):
    now = now or datetime.utcnow()
    offers = db.query(DbSpotOffer).order_by(DbSpotOffer.created_at.desc()).all()
    return [admin_view(db, o, now) for o in offers]
