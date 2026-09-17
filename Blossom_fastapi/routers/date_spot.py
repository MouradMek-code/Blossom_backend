import os
import unicodedata
from typing import List, Optional, Union
from urllib.parse import quote_plus, urlparse

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from auth.oauth2 import get_current_user
from database import db_message, db_profile, db_push
from database.database import get_db
from database.models import DbDateSpot, DbMatch, DbProfile, DbUser
from database.starter_spots import STARTER_CITY, STARTER_COUNTRY, STARTER_SPOTS
from routers.schemas import (
    DateSpotDisplay,
    DateSpotInvite,
    DateSpotInviteResult,
    DateSpotStatsUpdate,
    DateSpotUpdate,
    MessageDisplay,
    UserAuth,
)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

router = APIRouter(
    prefix="/date_spots",
    tags=["date spots"],
)

# Only allow genuine Google Maps links. This is user-generated content shown to
# everyone, so accepting arbitrary URLs would turn the page into a phishing
# vector; restricting the host keeps the "Open in Maps" button trustworthy.
_MAP_HOSTS = ("google.com", "goo.gl", "maps.app.goo.gl", "maps.google.com")

# Vibe tags. Deliberately the place-shaped subset of a profile's
# first_date_preference options, so a spot's tag and a person's preference are
# directly comparable later on.
CATEGORIES = [
    "Coffee",
    "Restaurant",
    "Drinks / Bar",
    "Walk / Outdoors",
    "Hiking / Nature",
    "Bowling",
    "Mini Golf",
    "Arcade / Gaming",
    "Movie",
    "Museum / Art Gallery",
    "Beach",
    "Concert / Live Music",
]

# Rough cost per person. Canonical values - clients translate "Free" for display.
PRICES = ["Free", "€", "€€", "€€€"]

# What kind of date a place suits. A spot can have several.
BEST_FOR = ["First date", "Romantic", "Casual", "Adventurous"]


def _clean_map_url(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Please paste a valid Google Maps link, or leave it empty.",
        )
    host = parsed.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    allowed = (
        host in _MAP_HOSTS
        or host.endswith(".google.com")
        or host.startswith("google.")          # google.fr, google.co.uk, ...
        or host.endswith(".goo.gl")
    )
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail="Please paste a valid Google Maps link, or leave it empty.",
        )
    return value[:500]


def _maps_search_url(query: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)


def _fold(value: Optional[str]) -> str:
    """Comparison key ignoring case, accents and extra spaces: "Châtelet" == "chatelet "."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def _tidy(value: Optional[str], max_len: int) -> str:
    """Trim and collapse runs of whitespace."""
    return " ".join((value or "").split())[:max_len]


def _capitalize(value: str) -> str:
    return value[:1].upper() + value[1:]


def _canonical_place(db: Session, city: str, country: str):
    """Reuse the spelling already on file for a city/country.

    Without this, "paris", "PARIS" and "Paris" each became a separate entry in
    the filters. Brand-new places just get a capital first letter.
    """
    city = _capitalize(_tidy(city, 120))
    country = _capitalize(_tidy(country, 120))
    known = db.query(DbDateSpot.country, DbDateSpot.city).distinct().all()
    for known_country, _ in known:
        if _fold(known_country) == _fold(country):
            country = known_country
            break
    for known_country, known_city in known:
        if known_country == country and _fold(known_city) == _fold(city):
            city = known_city
            break
    return city, country


def _clean_neighborhood(raw: Optional[str], city: str) -> Optional[str]:
    value = _capitalize(_tidy(raw, 120))
    # "Paris" typed as the neighborhood of Paris adds nothing.
    if not value or _fold(value) == _fold(city):
        return None
    return value


def _clean_category(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    if value not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Please pick a valid category.")
    return value


def _clean_price(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    if value not in PRICES:
        raise HTTPException(status_code=400, detail="Please pick a valid price.")
    return value


def _clean_best_for(raw: Union[str, List[str], None]) -> Optional[str]:
    """Accepts "First date,Casual" (multipart forms) or a list (JSON).

    Returns the stored form - comma-separated, in BEST_FOR order - or None.
    """
    parts = raw.split(",") if isinstance(raw, str) else (raw or [])
    picked = {part.strip() for part in parts if part and part.strip()}
    if picked - set(BEST_FOR):
        raise HTTPException(status_code=400, detail="Please pick valid 'best for' tags.")
    return ",".join(tag for tag in BEST_FOR if tag in picked) or None


def _require_admin(current_user: UserAuth):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")


def _can_manage(db: Session, spot: DbDateSpot, current_user: UserAuth) -> bool:
    """Authors manage their own spots; admins manage any (moderation, fixes)."""
    if getattr(current_user, "is_admin", False):
        return True
    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user.id).first()
    return profile is not None and spot.profile_id == profile.id


def _get_spot(db: Session, spot_id: int) -> DbDateSpot:
    spot = db.query(DbDateSpot).filter(DbDateSpot.id == spot_id).first()
    if not spot:
        raise HTTPException(status_code=404, detail="That place no longer exists.")
    return spot


def _upload_image(image: UploadFile):
    try:
        result = cloudinary.uploader.upload(image.file)
        return result["secure_url"], result["public_id"]
    except Exception:
        raise HTTPException(status_code=400, detail="We couldn't upload that photo. Please try another one.")


@router.get("", response_model=List[DateSpotDisplay])
def list_date_spots(
    country: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    price: Optional[str] = None,
    best_for: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Public listing so the city pages are browsable (and indexable)."""
    query = db.query(DbDateSpot).options(selectinload(DbDateSpot.profile))
    if country:
        query = query.filter(DbDateSpot.country == country)
    if city:
        query = query.filter(DbDateSpot.city == city)
    if category:
        query = query.filter(DbDateSpot.category == category)
    if price:
        query = query.filter(DbDateSpot.price == price)
    if best_for in BEST_FOR:
        # Tags never contain one another, so a substring match is exact enough.
        query = query.filter(DbDateSpot.best_for.ilike(f"%{best_for}%"))
    # Spots with a photo first - it's a visual page and the first spot becomes
    # the featured hero - then newest first.
    return query.order_by(
        DbDateSpot.image_url.is_(None),
        DbDateSpot.created_at.desc(),
    ).all()


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    """Countries (with their cities) that actually have spots, for the filters."""
    rows = db.query(DbDateSpot.country, DbDateSpot.city).distinct().all()
    grouped = {}
    for country, city in rows:
        grouped.setdefault(country, set()).add(city)
    return [
        {"country": country, "cities": sorted(cities)}
        for country, cities in sorted(grouped.items())
    ]


@router.get("/categories")
def list_categories():
    """The allowed vibe tags, so clients don't hardcode their own list."""
    return CATEGORIES


def _bump(db: Session, spot_id: int, column):
    """Increment a counter in SQL so concurrent hits don't overwrite each other."""
    updated = (
        db.query(DbDateSpot)
        .filter(DbDateSpot.id == spot_id)
        .update({column: column + 1}, synchronize_session=False)
    )
    db.commit()
    return updated


@router.post("/{spot_id}/view")
def track_view(spot_id: int, db: Session = Depends(get_db)):
    """Someone opened this spot's detail view. Fire-and-forget from the client."""
    if not _bump(db, spot_id, DbDateSpot.view_count):
        raise HTTPException(status_code=404, detail="That place no longer exists.")
    return {"ok": True}


@router.post("/{spot_id}/map_click")
def track_map_click(spot_id: int, db: Session = Depends(get_db)):
    """Someone tapped through to Google Maps - i.e. intends to actually go."""
    if not _bump(db, spot_id, DbDateSpot.map_click_count):
        raise HTTPException(status_code=404, detail="That place no longer exists.")
    return {"ok": True}


@router.get("/admin/stats")
def date_spot_stats(
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Engagement per spot, admin only, best performers first."""
    _require_admin(current_user)

    spots = (
        db.query(DbDateSpot)
        .order_by(DbDateSpot.map_click_count.desc(), DbDateSpot.view_count.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "name": s.name,
            "city": s.city,
            "country": s.country,
            "category": s.category,
            "views": s.view_count or 0,
            "map_clicks": s.map_click_count or 0,
        }
        for s in spots
    ]


@router.post("/admin/seed")
def seed_starter_spots(
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Admin: add the curated starter spots from database/starter_spots.py.

    Safe to run more than once - places already listed in the city (by name,
    ignoring case and accents) are skipped. Seeded spots have no author.
    """
    _require_admin(current_user)

    city, country = _canonical_place(db, STARTER_CITY, STARTER_COUNTRY)
    existing = {
        (_fold(name), _fold(spot_city))
        for name, spot_city in db.query(DbDateSpot.name, DbDateSpot.city).all()
    }

    added = 0
    for item in STARTER_SPOTS:
        key = (_fold(item["name"]), _fold(city))
        if key in existing:
            continue
        db.add(DbDateSpot(
            name=item["name"],
            city=city,
            country=country,
            neighborhood=_clean_neighborhood(item.get("neighborhood"), city),
            description=item["description"],
            category=_clean_category(item.get("category")),
            price=_clean_price(item.get("price")),
            best_for=_clean_best_for(item.get("best_for")),
            map_url=_maps_search_url(item.get("maps_query") or f"{item['name']}, {city}"),
        ))
        existing.add(key)
        added += 1

    db.commit()
    return {"added": added, "skipped": len(STARTER_SPOTS) - added}


@router.patch("/{spot_id}/stats", response_model=DateSpotDisplay)
def set_date_spot_stats(
    spot_id: int,
    payload: DateSpotStatsUpdate,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Admin: set a spot's counters directly (seeding, corrections)."""
    _require_admin(current_user)
    spot = _get_spot(db, spot_id)

    if payload.view_count is not None:
        spot.view_count = payload.view_count
    if payload.map_click_count is not None:
        spot.map_click_count = payload.map_click_count

    db.commit()
    db.refresh(spot)
    return spot


@router.post("/{spot_id}/invite", response_model=DateSpotInviteResult)
def invite_to_date_spot(
    spot_id: int,
    payload: DateSpotInvite,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Send this spot to a match as a chat message ("let's go here?").

    Goes through the normal message path, so blocks and the rule that the
    woman writes first in a man/woman match still apply.
    """
    spot = _get_spot(db, spot_id)

    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Finish creating your profile first.")

    other_id = payload.profile_id
    matched = (
        db.query(DbMatch)
        .filter(
            ((DbMatch.profile1_id == profile.id) & (DbMatch.profile2_id == other_id))
            | ((DbMatch.profile1_id == other_id) & (DbMatch.profile2_id == profile.id))
        )
        .first()
    )
    if not matched:
        raise HTTPException(status_code=403, detail="You can only invite people you've matched with.")

    conversation_id = db_profile.get_or_create_conversation(db, current_user, other_id)["conversation_id"]
    content = _tidy(payload.content, 500) or f"Want to go to {spot.name} together?"
    message = db_message.send_message(
        db, conversation_id, profile.id, content, date_spot_id=spot.id
    )
    db_push.notify_new_message(db, background_tasks, conversation_id, profile.id)
    return {
        "conversation_id": conversation_id,
        # from_attributes must be explicit: Pydantic 2 ignores the legacy
        # orm_mode config when validating by hand.
        "message": MessageDisplay.model_validate(message, from_attributes=True),
    }


@router.post("", response_model=DateSpotDisplay)
async def create_date_spot(
    name: str = Form(...),
    city: str = Form(...),
    country: str = Form(...),
    description: str = Form(...),
    neighborhood: Optional[str] = Form(None),
    map_url: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    price: Optional[str] = Form(None),
    best_for: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    name = _tidy(name, 150)
    description = (description or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Please give the place a name.")
    if not _tidy(city, 120) or not _tidy(country, 120):
        raise HTTPException(status_code=400, detail="Please say which city and country it's in.")
    if len(description) < 10:
        raise HTTPException(
            status_code=400,
            detail="Please add a short description (at least 10 characters).",
        )

    city, country = _canonical_place(db, city, country)
    map_link = _clean_map_url(map_url)
    spot_category = _clean_category(category)
    spot_price = _clean_price(price)
    spot_best_for = _clean_best_for(best_for)

    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="Finish creating your profile before sharing a place.",
        )

    image_url = None
    public_id = None
    if image is not None:
        image_url, public_id = _upload_image(image)

    spot = DbDateSpot(
        name=name,
        city=city,
        country=country,
        neighborhood=_clean_neighborhood(neighborhood, city),
        description=description,
        image_url=image_url,
        public_id=public_id,
        map_url=map_link,
        category=spot_category,
        price=spot_price,
        best_for=spot_best_for,
        profile_id=profile.id,
    )
    db.add(spot)
    db.commit()
    db.refresh(spot)
    return spot


@router.patch("/{spot_id}", response_model=DateSpotDisplay)
def update_date_spot(
    spot_id: int,
    payload: DateSpotUpdate,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Edit a spot's details. Only fields present in the body change; optional
    fields sent as "" or null are cleared.

    JSON rather than a form on purpose: FastAPI reads an empty form field as
    "not sent", which would make it impossible to clear a field. The photo is
    replaced separately via PUT /{spot_id}/image.
    """
    spot = _get_spot(db, spot_id)
    if not _can_manage(db, spot, current_user):
        raise HTTPException(status_code=403, detail="You can only edit places you added.")

    sent = payload.model_fields_set

    if "name" in sent:
        name = _tidy(payload.name, 150)
        if not name:
            raise HTTPException(status_code=400, detail="Please give the place a name.")
        spot.name = name

    if "description" in sent:
        description = (payload.description or "").strip()
        if len(description) < 10:
            raise HTTPException(
                status_code=400,
                detail="Please add a short description (at least 10 characters).",
            )
        spot.description = description

    if "city" in sent or "country" in sent:
        city = payload.city if "city" in sent else spot.city
        country = payload.country if "country" in sent else spot.country
        if not _tidy(city, 120) or not _tidy(country, 120):
            raise HTTPException(status_code=400, detail="Please say which city and country it's in.")
        spot.city, spot.country = _canonical_place(db, city, country)

    if "neighborhood" in sent:
        spot.neighborhood = _clean_neighborhood(payload.neighborhood, spot.city)
    if "map_url" in sent:
        spot.map_url = _clean_map_url(payload.map_url)
    if "category" in sent:
        spot.category = _clean_category(payload.category)
    if "price" in sent:
        spot.price = _clean_price(payload.price)
    if "best_for" in sent:
        spot.best_for = _clean_best_for(payload.best_for)

    db.commit()
    db.refresh(spot)
    return spot


@router.put("/{spot_id}/image", response_model=DateSpotDisplay)
async def replace_date_spot_image(
    spot_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Add or replace a spot's photo (e.g. an admin illustrating a starter spot)."""
    spot = _get_spot(db, spot_id)
    if not _can_manage(db, spot, current_user):
        raise HTTPException(status_code=403, detail="You can only edit places you added.")

    old_public_id = spot.public_id
    spot.image_url, spot.public_id = _upload_image(image)
    db.commit()
    db.refresh(spot)

    if old_public_id:
        try:
            cloudinary.uploader.destroy(old_public_id)
        except Exception:
            # The new photo is already saved; a leftover old file is harmless.
            pass
    return spot


@router.delete("/{spot_id}")
def delete_date_spot(
    spot_id: int,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Authors can remove their own spot; admins can remove any (moderation)."""
    spot = _get_spot(db, spot_id)
    if not _can_manage(db, spot, current_user):
        raise HTTPException(status_code=403, detail="You can only remove places you added.")

    if spot.public_id:
        try:
            cloudinary.uploader.destroy(spot.public_id)
        except Exception:
            # The row still goes away even if the CDN cleanup fails.
            pass

    db.delete(spot)
    db.commit()
    return {"detail": "Place removed"}
