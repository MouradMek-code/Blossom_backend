"""Events: members organise a date idea, a group outing or a language
exchange - a set time, a public place.

  * Everyone can see events (visitors too: an event is a reason to join).
  * Members comment (comments are for members only) and say "I'm interested".
  * The organiser sees who's interested and matches the people they'd like to
    meet: a normal Blossom match, with its chat and its rules (in a woman-man
    match the woman writes first). Interest is the member's yes, the
    organiser's "Match" is theirs - nobody is matched without saying yes.
    Declined people are never told.
  * Safety: public places, at most 3 upcoming events per member, blocked
    people never see each other, contacts in comments are hidden, events and
    comments can be reported, women-only events.
"""
import re
import time
from datetime import datetime, timedelta, timezone

import cloudinary.uploader
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from database import db_block, db_offers, db_push
from database.models import (
    DbConversation, DbDateSpot, DbEvent, DbEventComment, DbEventInterest, DbEventReport, DbMatch, DbProfile,
)

KINDS = ("date", "group", "language")
MAX_UPCOMING_PER_MEMBER = 3
MAX_DAYS_AHEAD = 120
COMMENT_MAX = 500
COMMENTS_PER_HOUR = 10
# Listed until a while after it starts (or its end); people can still like
# and be matched for two days after - "who did you meet?".
LISTED_AFTER_START = timedelta(hours=6)
OPEN_AFTER_START = timedelta(days=2)
WOMEN = {"Woman", "Trans Woman"}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LINK = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(com|fr|net|org|io|me|ly|gg|co)\b\S*)", re.I)
PHONE = re.compile(r"\+?\d[\d\s.\-()]{7,}\d")
HIDDEN = "•••"


def _now():
    return datetime.utcnow()


def _iso(value):
    return value.isoformat(timespec="seconds") + "Z" if value else None


def _clean(value, limit):
    value = " ".join(str(value or "").split())
    return value[:limit] or None


def _long(value, limit):
    value = str(value or "").strip()
    return value[:limit] or None


def hide_contacts(text: str) -> str:
    """No phone numbers, emails or links in comments: they're how people get
    taken off Blossom (spam, scams)."""
    text = EMAIL.sub(HIDDEN, text)
    text = LINK.sub(HIDDEN, text)
    return PHONE.sub(HIDDEN, text)


def parse_time(value, field="starts_at"):
    """"2026-10-10T18:30:00Z" (or with an offset) -> naive UTC."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date/time ({field}).")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _profile_of(db: Session, user):
    if user is None:
        return None
    return db.query(DbProfile).options(selectinload(DbProfile.photos)).filter(DbProfile.user_id == user.id).first()


def _require_profile(db: Session, user) -> DbProfile:
    profile = _profile_of(db, user)
    if not profile:
        raise HTTPException(status_code=400, detail="Finish creating your profile first.")
    return profile


def _person(profile: DbProfile):
    if not profile:
        return None
    photos = sorted(profile.photos, key=lambda p: p.id) if profile.photos else []
    return {
        "id": profile.id,
        "first_name": profile.first_name,
        "age": profile.age,
        "gender": profile.gender,
        "city": profile.city,
        "photo": photos[0].image_url if photos else None,
        "languages": [l.language_name for l in (profile.languages or [])],
        "learning_languages": [l.language_name for l in (profile.learning_languages or [])],
    }


def _ends(event: DbEvent):
    return event.ends_at or event.starts_at


def _is_open(event: DbEvent, now=None) -> bool:
    """Interest, matches and comments: until two days after it starts."""
    now = now or _now()
    return event.status == "active" and now <= event.starts_at + OPEN_AFTER_START


def _blocked(db: Session, viewer: DbProfile):
    return db_block.get_block_relation_ids(db, viewer.id) if viewer else set()


def _get(db: Session, event_id: int, viewer: DbProfile = None) -> DbEvent:
    event = (
        db.query(DbEvent).options(selectinload(DbEvent.profile).selectinload(DbProfile.photos))
        .filter(DbEvent.id == event_id).first()
    )
    if not event or event.status == "removed":
        raise HTTPException(status_code=404, detail="This event no longer exists.")
    if viewer and event.profile_id in _blocked(db, viewer):
        raise HTTPException(status_code=404, detail="This event no longer exists.")
    return event


def _check_women_only(event: DbEvent, viewer: DbProfile):
    if event.women_only and viewer.id != event.profile_id and viewer.gender not in WOMEN:
        raise HTTPException(status_code=403, detail="This event is for women only.")


# ---- what clients get --------------------------------------------------------------

def _views(db: Session, events, viewer: DbProfile = None, now=None):
    now = now or _now()
    ids = [e.id for e in events]
    if not ids:
        return []
    interested = dict(
        db.query(DbEventInterest.event_id, func.count(DbEventInterest.id))
        .filter(DbEventInterest.event_id.in_(ids)).group_by(DbEventInterest.event_id).all()
    )
    pending = dict(
        db.query(DbEventInterest.event_id, func.count(DbEventInterest.id))
        .filter(DbEventInterest.event_id.in_(ids), DbEventInterest.status == "pending")
        .group_by(DbEventInterest.event_id).all()
    )
    comments = dict(
        db.query(DbEventComment.event_id, func.count(DbEventComment.id))
        .filter(DbEventComment.event_id.in_(ids), DbEventComment.deleted_at.is_(None))
        .group_by(DbEventComment.event_id).all()
    )
    mine = {}
    if viewer:
        mine = dict(
            db.query(DbEventInterest.event_id, DbEventInterest.status)
            .filter(DbEventInterest.event_id.in_(ids), DbEventInterest.profile_id == viewer.id).all()
        )
    spot_ids = [e.spot_id for e in events if e.spot_id]
    offers = db_offers.public_offers(db, spot_ids) if spot_ids else {}
    spots = {s.id: s for s in db.query(DbDateSpot).filter(DbDateSpot.id.in_(spot_ids)).all()} if spot_ids else {}

    result = []
    for e in events:
        owner = bool(viewer and viewer.id == e.profile_id)
        spot = spots.get(e.spot_id)
        result.append({
            "id": e.id,
            "kind": e.kind,
            "title": e.title,
            "description": e.description,
            "starts_at": _iso(e.starts_at),
            "ends_at": _iso(e.ends_at),
            "place_name": e.place_name,
            "map_url": e.map_url,
            "city": e.city,
            "country": e.country,
            "spot": {"id": spot.id, "name": spot.name, "offer": offers.get(spot.id)} if spot else None,
            "max_people": e.max_people,
            "languages": [x for x in (e.languages or "").split(",") if x],
            "women_only": e.women_only,
            "comments_open": e.comments_open,
            "image_url": e.image_url,
            "status": e.status,
            "organizer": _person(e.profile),
            "interested_count": interested.get(e.id, 0),
            "comment_count": comments.get(e.id, 0),
            "is_owner": owner,
            "pending_count": pending.get(e.id, 0) if owner else None,
            # Declined people are never told: for them it's still "pending".
            "my_interest": "pending" if mine.get(e.id) == "declined" else mine.get(e.id),
            "open": _is_open(e, now),
            "past": now > _ends(e) + LISTED_AFTER_START,
        })
    return result


def view(db: Session, event: DbEvent, viewer: DbProfile = None):
    return _views(db, [event], viewer)[0]


# ---- listing ---------------------------------------------------------------------

def list_events(db: Session, user=None, city=None, country=None, kind=None, spot_id=None, mine=False):
    viewer = _profile_of(db, user)
    now = _now()
    query = db.query(DbEvent).options(selectinload(DbEvent.profile).selectinload(DbProfile.photos))
    if mine:
        if not viewer:
            return []
        interested_in = db.query(DbEventInterest.event_id).filter(DbEventInterest.profile_id == viewer.id)
        query = query.filter(
            (DbEvent.profile_id == viewer.id) | DbEvent.id.in_(interested_in),
            DbEvent.status != "removed",
            DbEvent.starts_at >= now - timedelta(days=7),
        )
    else:
        query = query.filter(
            DbEvent.status == "active",
            DbEvent.starts_at >= now - LISTED_AFTER_START,
        )
        if city:
            query = query.filter(DbEvent.city == city)
        if country:
            query = query.filter(DbEvent.country == country)
        if kind in KINDS:
            query = query.filter(DbEvent.kind == kind)
        if spot_id:
            query = query.filter(DbEvent.spot_id == spot_id)
    events = query.order_by(DbEvent.starts_at).limit(200).all()
    blocked = _blocked(db, viewer)
    events = [e for e in events if e.profile_id not in blocked]
    return _views(db, events, viewer, now)


def locations(db: Session):
    """Countries and cities with upcoming events, for the filters."""
    rows = (
        db.query(DbEvent.country, DbEvent.city)
        .filter(DbEvent.status == "active", DbEvent.starts_at >= _now() - LISTED_AFTER_START)
        .distinct().all()
    )
    grouped = {}
    for country, city in rows:
        grouped.setdefault(country, set()).add(city)
    return [{"country": c, "cities": sorted(cities)} for c, cities in sorted(grouped.items())]


def get_event(db: Session, event_id: int, user=None):
    viewer = _profile_of(db, user)
    return view(db, _get(db, event_id, viewer), viewer)


# ---- creating / editing ---------------------------------------------------------

def _validate(fields: dict, now, creating: bool):
    if "kind" in fields and fields["kind"] not in KINDS:
        raise HTTPException(status_code=400, detail="Choose a type of event.")
    if "title" in fields and (not fields["title"] or len(fields["title"]) < 3):
        raise HTTPException(status_code=400, detail="Give your event a title.")
    if "description" in fields and (not fields["description"] or len(fields["description"]) < 10):
        raise HTTPException(status_code=400, detail="Say a few words about your event (10 characters at least).")
    if "place_name" in fields and not fields["place_name"]:
        raise HTTPException(status_code=400, detail="Say where it happens (a public place).")
    if "starts_at" in fields:
        starts = fields["starts_at"]
        if not starts:
            raise HTTPException(status_code=400, detail="Choose a date and time.")
        if creating and starts < now - timedelta(minutes=5):
            raise HTTPException(status_code=400, detail="The date must be in the future.")
        if starts > now + timedelta(days=MAX_DAYS_AHEAD):
            raise HTTPException(status_code=400, detail=f"Events can be planned up to {MAX_DAYS_AHEAD} days ahead.")
    if fields.get("ends_at") and fields.get("starts_at") and fields["ends_at"] <= fields["starts_at"]:
        raise HTTPException(status_code=400, detail="The end must be after the start.")
    if "map_url" in fields and fields["map_url"] and not fields["map_url"].lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="The Google Maps link should start with https://")
    if "max_people" in fields and fields["max_people"] is not None and not 2 <= fields["max_people"] <= 100:
        raise HTTPException(status_code=400, detail="A group is 2 to 100 people.")


def _languages(value):
    if value is None:
        return None
    items = value if isinstance(value, list) else str(value).split(",")
    seen = []
    for item in items:
        name = _clean(item, 40)
        if name and name.lower() not in {s.lower() for s in seen}:
            seen.append(name)
    return ",".join(seen[:6]) or None


def _upload(image):
    content_type = (image.content_type or "").lower()
    if content_type and content_type != "application/octet-stream" and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please choose a photo (JPG, PNG, HEIC...).")
    try:
        result = cloudinary.uploader.upload(image.file)
    except Exception:
        raise HTTPException(status_code=400, detail="We couldn't upload that photo. Please try another one.")
    return result["secure_url"], result["public_id"]


def create_event(db: Session, user, data: dict, image=None):
    profile = _require_profile(db, user)
    now = _now()
    upcoming = db.query(func.count(DbEvent.id)).filter(
        DbEvent.profile_id == profile.id, DbEvent.status == "active", DbEvent.starts_at >= now,
    ).scalar() or 0
    if upcoming >= MAX_UPCOMING_PER_MEMBER and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=429, detail=f"You already have {MAX_UPCOMING_PER_MEMBER} upcoming events.")

    spot = None
    if data.get("spot_id"):
        spot = db.get(DbDateSpot, data["spot_id"])
        if not spot or spot.status != "published":
            raise HTTPException(status_code=404, detail="That place no longer exists.")

    fields = {
        "kind": data.get("kind") or "group",
        "title": _clean(data.get("title"), 120),
        "description": _long(data.get("description"), 1500),
        "starts_at": parse_time(data.get("starts_at")),
        "ends_at": parse_time(data.get("ends_at"), "ends_at"),
        "place_name": _clean(data.get("place_name"), 150) or (spot.name if spot else None),
        "map_url": _clean(data.get("map_url"), 500) or (spot.map_url if spot else None),
        "max_people": data.get("max_people"),
    }
    _validate(fields, now, creating=True)
    city = _clean(data.get("city"), 120) or (spot.city if spot else None) or profile.city
    country = _clean(data.get("country"), 120) or (spot.country if spot else None) or profile.country
    if not city or not country:
        raise HTTPException(status_code=400, detail="Say which city and country it's in.")

    image_url = public_id = None
    if image is not None:
        image_url, public_id = _upload(image)
    event = DbEvent(
        profile_id=profile.id,
        kind=fields["kind"],
        title=fields["title"],
        description=fields["description"],
        starts_at=fields["starts_at"],
        ends_at=fields["ends_at"],
        place_name=fields["place_name"],
        map_url=fields["map_url"],
        city=city,
        country=country,
        spot_id=spot.id if spot else None,
        max_people=fields["max_people"] if fields["kind"] == "group" else None,
        languages=_languages(data.get("languages")),
        women_only=bool(data.get("women_only")),
        comments_open=data.get("comments_open") is not False,
        image_url=image_url,
        public_id=public_id,
        status="active",
        created_at=now,
    )
    db.add(event)
    db.commit()
    return view(db, _get(db, event.id), profile)


def _require_owner(db: Session, user, event_id: int):
    profile = _require_profile(db, user)
    event = _get(db, event_id)
    if event.profile_id != profile.id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only the organiser can do this.")
    return profile, event


def update_event(db: Session, user, event_id: int, changes: dict):
    profile, event = _require_owner(db, user, event_id)
    if event.status != "active":
        raise HTTPException(status_code=409, detail="This event is cancelled.")
    now = _now()
    fields = {}
    for key in ("title", "place_name", "map_url"):
        if key in changes:
            fields[key] = _clean(changes[key], 150 if key != "map_url" else 500)
    if "title" in fields:
        fields["title"] = (fields["title"] or "")[:120] or None
    if "description" in changes:
        fields["description"] = _long(changes["description"], 1500)
    if "kind" in changes:
        fields["kind"] = changes["kind"]
    if "starts_at" in changes:
        fields["starts_at"] = parse_time(changes["starts_at"])
    if "ends_at" in changes:
        fields["ends_at"] = parse_time(changes["ends_at"], "ends_at")
    if "max_people" in changes:
        fields["max_people"] = changes["max_people"]
    check = dict(fields)
    if "ends_at" in check and "starts_at" not in check:
        check["starts_at"] = event.starts_at
    _validate(check, now, creating="starts_at" in fields)
    for key, value in fields.items():
        setattr(event, key, value)
    if event.kind != "group":
        event.max_people = None
    if "languages" in changes:
        event.languages = _languages(changes["languages"])
    for key in ("women_only", "comments_open"):
        if key in changes and changes[key] is not None:
            setattr(event, key, bool(changes[key]))
    for key in ("city", "country"):
        if key in changes and _clean(changes[key], 120):
            setattr(event, key, _clean(changes[key], 120))
    db.commit()
    return view(db, _get(db, event.id), profile)


def replace_image(db: Session, user, event_id: int, image):
    profile, event = _require_owner(db, user, event_id)
    old = event.public_id
    event.image_url, event.public_id = _upload(image)
    db.commit()
    if old:
        try:
            cloudinary.uploader.destroy(old)
        except Exception:
            pass  # the new photo is saved
    return view(db, _get(db, event.id), profile)


def cancel_event(db: Session, user, event_id: int, background_tasks: BackgroundTasks):
    """The organiser cancels (the people interested are told); an admin
    removes (moderation - it disappears)."""
    profile = _profile_of(db, user)
    event = _get(db, event_id)
    own = profile is not None and event.profile_id == profile.id
    if not own and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only the organiser can do this.")
    if not own:  # an admin, moderating
        event.status = "removed"
        db.commit()
        return {"status": "removed"}
    if event.status == "active":
        event.status = "cancelled"
        db.commit()
        people = [pid for (pid,) in db.query(DbEventInterest.profile_id).filter(
            DbEventInterest.event_id == event.id, DbEventInterest.status != "declined")]
        db_push.notify_event_cancelled(db, background_tasks, event, people)
    return {"status": event.status}


# ---- "I'm interested" and the organiser's answer ------------------------------------

def set_interest(db: Session, user, event_id: int, background_tasks: BackgroundTasks, interested: bool):
    viewer = _require_profile(db, user)
    event = _get(db, event_id, viewer)
    if event.profile_id == viewer.id:
        raise HTTPException(status_code=400, detail="It's your event.")
    existing = db.query(DbEventInterest).filter(
        DbEventInterest.event_id == event.id, DbEventInterest.profile_id == viewer.id).first()
    if not interested:
        if existing and existing.status == "pending":
            db.delete(existing)
            db.commit()
        return view(db, event, viewer)
    if not _is_open(event):
        raise HTTPException(status_code=409, detail="This event is over.")
    _check_women_only(event, viewer)
    if not existing:
        db.add(DbEventInterest(event_id=event.id, profile_id=viewer.id, created_at=_now(), status="pending"))
        db.commit()
        db_push.notify_event_interest(db, background_tasks, event, viewer)
    return view(db, event, viewer)


def interested_people(db: Session, user, event_id: int):
    """For the organiser (and admins): who's interested, newest first."""
    _, event = _require_owner(db, user, event_id)
    rows = (
        db.query(DbEventInterest)
        .options(selectinload(DbEventInterest.profile).selectinload(DbProfile.photos),
                 selectinload(DbEventInterest.profile).selectinload(DbProfile.languages),
                 selectinload(DbEventInterest.profile).selectinload(DbProfile.learning_languages))
        .filter(DbEventInterest.event_id == event.id)
        .order_by(DbEventInterest.created_at.desc()).all()
    )
    blocked = db_block.get_block_relation_ids(db, event.profile_id)
    return [
        {"person": _person(r.profile), "status": r.status, "created_at": _iso(r.created_at)}
        for r in rows if r.profile and r.profile_id not in blocked
    ]


def answer_interest(db: Session, user, event_id: int, profile_id: int, action: str,
                    background_tasks: BackgroundTasks):
    owner, event = _require_owner(db, user, event_id)
    interest = db.query(DbEventInterest).filter(
        DbEventInterest.event_id == event.id, DbEventInterest.profile_id == profile_id).first()
    if not interest:
        raise HTTPException(status_code=404, detail="This person isn't interested (anymore).")
    if db_block.is_blocked_either_direction(db, event.profile_id, profile_id):
        raise HTTPException(status_code=404, detail="This person isn't interested (anymore).")
    if action == "decline":
        interest.status = "declined"
        interest.answered_at = _now()
        db.commit()
        return {"status": "declined"}
    if not _is_open(event):
        raise HTTPException(status_code=409, detail="This event is over.")

    a, b = sorted((event.profile_id, profile_id))
    match = db.query(DbMatch).filter(DbMatch.profile1_id == a, DbMatch.profile2_id == b).first()
    new = match is None
    if new:
        match = DbMatch(profile1_id=a, profile2_id=b, event_id=event.id)
        db.add(match)
        db.flush()
        db.add(DbConversation(match_id=match.id))
    interest.status = "matched"
    interest.answered_at = _now()
    db.commit()
    db.refresh(match)
    conversation_id = match.conversation.id if match.conversation else None
    if new:
        db_push.notify_event_match(db, background_tasks, event, event.profile, profile_id, conversation_id)
    return {"status": "matched", "conversation_id": conversation_id, "already_matched": not new}


# ---- comments --------------------------------------------------------------------

def _comment_view(c: DbEventComment, viewer: DbProfile, event: DbEvent, interested_ids: set):
    deleted = c.deleted_at is not None
    return {
        "id": c.id,
        "parent_id": c.parent_id,
        "text": None if deleted else c.text,
        "deleted": deleted,
        "created_at": _iso(c.created_at),
        "author": None if deleted else _person(c.profile),
        "is_owner": c.profile_id == event.profile_id,
        "interested": c.profile_id in interested_ids,
        "mine": bool(viewer and c.profile_id == viewer.id),
        "can_delete": bool(viewer and not deleted and (c.profile_id == viewer.id or event.profile_id == viewer.id)),
    }


def list_comments(db: Session, user, event_id: int):
    viewer = _require_profile(db, user)
    event = _get(db, event_id, viewer)
    blocked = _blocked(db, viewer)
    rows = (
        db.query(DbEventComment).options(selectinload(DbEventComment.profile).selectinload(DbProfile.photos))
        .filter(DbEventComment.event_id == event.id).order_by(DbEventComment.created_at, DbEventComment.id).all()
    )
    interested_ids = {pid for (pid,) in db.query(DbEventInterest.profile_id).filter(DbEventInterest.event_id == event.id)}
    is_admin = getattr(user, "is_admin", False)
    result = []
    for c in rows:
        if c.profile_id in blocked:
            continue
        item = _comment_view(c, viewer, event, interested_ids)
        if is_admin and not item["deleted"]:
            item["can_delete"] = True
        result.append(item)
    return result


_last_comment_push = {}


def _notify_once(key, wait=300):
    """At most one comment notification per person and event every 5 minutes."""
    now = time.time()
    if now - _last_comment_push.get(key, 0) < wait:
        return False
    _last_comment_push[key] = now
    return True


def add_comment(db: Session, user, event_id: int, text: str, parent_id, background_tasks: BackgroundTasks):
    viewer = _require_profile(db, user)
    event = _get(db, event_id, viewer)
    if not event.comments_open and viewer.id != event.profile_id:
        raise HTTPException(status_code=403, detail="Comments are closed for this event.")
    if not _is_open(event):
        raise HTTPException(status_code=409, detail="This event is over.")
    _check_women_only(event, viewer)
    text = _long(text, COMMENT_MAX)
    if not text:
        raise HTTPException(status_code=400, detail="Write something first.")
    recent = db.query(func.count(DbEventComment.id)).filter(
        DbEventComment.profile_id == viewer.id, DbEventComment.created_at >= _now() - timedelta(hours=1),
    ).scalar() or 0
    if recent >= COMMENTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="You're commenting a lot - take a little break and try again later.")
    parent = None
    if parent_id:
        parent = db.get(DbEventComment, parent_id)
        if not parent or parent.event_id != event.id:
            raise HTTPException(status_code=404, detail="That comment no longer exists.")
        if parent.parent_id:  # one level of replies: answer the thread
            parent = db.get(DbEventComment, parent.parent_id)
    comment = DbEventComment(
        event_id=event.id, profile_id=viewer.id, parent_id=parent.id if parent else None,
        text=hide_contacts(text), created_at=_now(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    told = set()
    if parent and parent.profile_id != viewer.id and parent.deleted_at is None:
        if _notify_once((event.id, parent.profile_id)):
            db_push.notify_event_comment(db, background_tasks, event, viewer, parent.profile_id, reply=True)
        told.add(parent.profile_id)
    if event.profile_id != viewer.id and event.profile_id not in told:
        if _notify_once((event.id, event.profile_id)):
            db_push.notify_event_comment(db, background_tasks, event, viewer, event.profile_id, reply=False)
    interested_ids = {pid for (pid,) in db.query(DbEventInterest.profile_id).filter(DbEventInterest.event_id == event.id)}
    return _comment_view(db.query(DbEventComment).options(selectinload(DbEventComment.profile))
                         .filter(DbEventComment.id == comment.id).first(), viewer, event, interested_ids)


def delete_comment(db: Session, user, comment_id: int):
    viewer = _require_profile(db, user)
    comment = db.get(DbEventComment, comment_id)
    if not comment or comment.deleted_at is not None:
        raise HTTPException(status_code=404, detail="That comment no longer exists.")
    event = db.get(DbEvent, comment.event_id)
    allowed = comment.profile_id == viewer.id or event.profile_id == viewer.id or getattr(user, "is_admin", False)
    if not allowed:
        raise HTTPException(status_code=403, detail="You can't delete this comment.")
    comment.deleted_at = _now()
    db.commit()
    return {"deleted": True}


# ---- reports (admins) --------------------------------------------------------------

def report(db: Session, user, event_id: int, comment_id, reason, background_tasks: BackgroundTasks):
    viewer = _require_profile(db, user)
    event = _get(db, event_id, viewer)
    if comment_id:
        comment = db.get(DbEventComment, comment_id)
        if not comment or comment.event_id != event.id:
            raise HTTPException(status_code=404, detail="That comment no longer exists.")
    already = db.query(DbEventReport.id).filter(
        DbEventReport.event_id == event.id, DbEventReport.comment_id == (comment_id or None),
        DbEventReport.reporter_profile_id == viewer.id).first()
    if not already:
        db.add(DbEventReport(event_id=event.id, comment_id=comment_id or None, reporter_profile_id=viewer.id,
                             reason=_long(reason, 500), created_at=_now()))
        db.commit()
        db_push.notify_event_report(db, background_tasks, event)
    return {"reported": True}


def list_reports(db: Session):
    rows = db.query(DbEventReport).filter(DbEventReport.handled == False).order_by(DbEventReport.created_at).all()  # noqa: E712
    result = []
    for r in rows:
        event = db.query(DbEvent).options(selectinload(DbEvent.profile)).filter(DbEvent.id == r.event_id).first()
        comment = db.get(DbEventComment, r.comment_id) if r.comment_id else None
        reporter = db.get(DbProfile, r.reporter_profile_id)
        result.append({
            "id": r.id,
            "created_at": _iso(r.created_at),
            "reason": r.reason,
            "reporter": reporter.first_name if reporter else None,
            "event": {
                "id": event.id, "title": event.title, "status": event.status, "city": event.city,
                "organizer": event.profile.first_name if event.profile else None,
            } if event else None,
            "comment": {
                "id": comment.id, "text": comment.text, "deleted": comment.deleted_at is not None,
                "author": comment.profile.first_name if comment.profile else None,
            } if comment else None,
        })
    return result


def mark_report_handled(db: Session, report_id: int):
    row = db.get(DbEventReport, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found.")
    row.handled = True
    db.commit()
    return {"handled": True}


def match_event(db: Session, match: DbMatch):
    """For the chat header: the event a match was made through."""
    if not match or not match.event_id:
        return None
    event = db.get(DbEvent, match.event_id)
    if not event:
        return None
    return {"id": event.id, "title": event.title, "starts_at": _iso(event.starts_at), "place_name": event.place_name}
