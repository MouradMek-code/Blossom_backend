import os
from typing import List, Optional

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from auth.oauth2 import get_current_user
from database.database import get_db
from database.models import DbDateSpot, DbProfile, DbUser
from routers.schemas import DateSpotDisplay, UserAuth

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

router = APIRouter(
    prefix="/date_spots",
    tags=["date spots"],
)


@router.get("", response_model=List[DateSpotDisplay])
def list_date_spots(
    country: Optional[str] = None,
    city: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Public listing so the city pages are browsable (and indexable)."""
    query = db.query(DbDateSpot).options(selectinload(DbDateSpot.profile))
    if country:
        query = query.filter(DbDateSpot.country == country)
    if city:
        query = query.filter(DbDateSpot.city == city)
    return query.order_by(DbDateSpot.created_at.desc()).all()


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


@router.post("", response_model=DateSpotDisplay)
async def create_date_spot(
    name: str = Form(...),
    city: str = Form(...),
    country: str = Form(...),
    description: str = Form(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    name = (name or "").strip()
    city = (city or "").strip()
    country = (country or "").strip()
    description = (description or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Please give the place a name.")
    if not city or not country:
        raise HTTPException(status_code=400, detail="Please say which city and country it's in.")
    if len(description) < 10:
        raise HTTPException(
            status_code=400,
            detail="Please add a short description (at least 10 characters).",
        )

    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="Finish creating your profile before sharing a place.",
        )

    image_url = None
    public_id = None
    if image is not None:
        try:
            result = cloudinary.uploader.upload(image.file)
            image_url = result["secure_url"]
            public_id = result["public_id"]
        except Exception:
            raise HTTPException(status_code=400, detail="We couldn't upload that photo. Please try another one.")

    spot = DbDateSpot(
        name=name,
        city=city,
        country=country,
        description=description,
        image_url=image_url,
        public_id=public_id,
        profile_id=profile.id,
    )
    db.add(spot)
    db.commit()
    db.refresh(spot)
    return spot


@router.delete("/{spot_id}")
def delete_date_spot(
    spot_id: int,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Authors can remove their own spot; admins can remove any (moderation)."""
    spot = db.query(DbDateSpot).filter(DbDateSpot.id == spot_id).first()
    if not spot:
        raise HTTPException(status_code=404, detail="That place no longer exists.")

    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user.id).first()
    is_owner = profile is not None and spot.profile_id == profile.id
    is_admin = bool(getattr(current_user, "is_admin", False))
    if not is_owner and not is_admin:
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
