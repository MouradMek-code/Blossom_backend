from typing import List

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.params import Depends
from sqlalchemy.orm import Session
from database import db_profile,db_message,db_push
from database.models import DbProfile,DbProfilePhoto
from auth.oauth2 import get_current_user
from database.database import get_db
from routers.schemas import ProfileBase, ProfileDisplay, UserAuth,ProfileDisplayforPhoto,BioUpdate,ConnectionUpdate,DetectedLocation,PauseUpdate
from routers.schemas import UserAuth,ProfilePhotoDisplay
import cloudinary.uploader
from datetime import datetime
from sqlalchemy import func
import cloudinary
import os
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)
router = APIRouter(
    tags=["post"],
    prefix="/post",
)
router = APIRouter(
    prefix="/profile",
    tags=["profile"],
)

@router.post("/", response_model=ProfileDisplay)
def create_profile(request:ProfileBase,db:Session=Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    # From a country Blossom isn't open to (India) - the country chosen, or the
    # phone's time zone - the account is removed straight away. The apps then
    # check the GPS position too, with permission (POST /profile/location).
    from database.closed_countries import is_closed, is_closed_timezone
    if is_closed(request.country) or is_closed_timezone(request.timezone):
        db_profile.delete_account(db, current_use)
        raise HTTPException(status_code=403, detail="Sorry, Blossom isn't available in your country yet.")
    # Admins are notified later, once the photos are in (see upload_image).
    return db_profile.create_profile(db,request,current_use)

@router.get("/", response_model=ProfileDisplay)
def read_profile(current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_profile(db,current_user)

    if result is None:
        raise HTTPException(status_code=404,detail="Profile still doesn't exist")
    result.paused = result.paused_at is not None
    return result
@router.get("/profiles/matched", response_model=List[ProfileDisplay])
def read_profile_matched(current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_profiles_matched(db,current_user)
    return result
@router.get("/all_profile", response_model=List[ProfileDisplay])
def get_all_profiles(current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_all_profiles(db,current_user)
    if result is None:
        raise HTTPException(status_code=404,detail="Profiles still doesn't exist")
    return result
@router.get("/{id}", response_model=ProfileDisplay)
def read_profile(id:int,current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_profile_by_id(db,id)

    if result is None:
        raise HTTPException(status_code=404,detail="Profile still doesn't exist")
    return result



@router.post("/image",response_model=ProfilePhotoDisplay)
def upload_image(background_tasks:BackgroundTasks,image:UploadFile=File(...),db:Session = Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    # Check before the (slow) Cloudinary upload, not after it.
    db_profile_instance = db.query(DbProfile).filter(DbProfile.user_id == current_use.id).first()
    if db_profile_instance is None:
        raise HTTPException(status_code=404, detail="Please finish your profile before adding photos.")
    content_type = (image.content_type or "").lower()
    if content_type and content_type != "application/octet-stream" and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please choose a photo (JPG, PNG, HEIC...).")
    result = cloudinary.uploader.upload(image.file)
    db_profile_photo = DbProfilePhoto(
        image_url=result["secure_url"],
        public_id=result["public_id"],
        profile_id=db_profile_instance.id
    )
    db.add(db_profile_photo)
    db.commit()
    db.refresh(db_profile_photo)
    _notify_if_just_finished(db, background_tasks, db_profile_instance)
    return db_profile_photo


# Sign-up asks for at least 2 photos: with the 2nd one the profile is done.
PHOTOS_TO_FINISH = 2


def _notify_if_just_finished(db: Session, background_tasks: BackgroundTasks, profile: DbProfile):
    """Tell the admins about a new member once their profile is finished -
    once per person: completed_at is claimed by a single UPDATE, so two
    uploads at the same moment can't both notify, and deleting and re-adding
    photos later doesn't notify again."""
    if profile.completed_at is not None:
        return
    photos = db.query(func.count(DbProfilePhoto.id)).filter(DbProfilePhoto.profile_id == profile.id).scalar()
    if photos < PHOTOS_TO_FINISH:
        return
    claimed = db.query(DbProfile).filter(
        DbProfile.id == profile.id, DbProfile.completed_at.is_(None)
    ).update({DbProfile.completed_at: datetime.now()}, synchronize_session=False)
    db.commit()
    if claimed:
        db.refresh(profile)
        db_push.notify_new_profile(db, background_tasks, profile)

@router.post("/location")
def detected_location(payload: DetectedLocation, db: Session = Depends(get_db),
                      current_user: UserAuth = Depends(get_current_user)):
    """The app, after the profile exists: where the phone is now (approximate,
    with the member's permission). The profile's city and country follow it.
    In a country Blossom isn't open to (India), the account is removed."""
    from database.closed_countries import CLOSED_COUNTRY_CODES
    from routers.geo import country_name

    code = payload.country_code.strip().upper()
    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user.id).first()
    if profile is None:
        return {"removed": False, "updated": False}
    if code in CLOSED_COUNTRY_CODES:
        db_profile.delete_account(db, current_user)
        return {"removed": True, "updated": False}
    country = country_name(code)
    city = " ".join((payload.city or "").split())[:50]
    if not country or not city:
        return {"removed": False, "updated": False}
    if profile.city == city and profile.country == country:
        return {"removed": False, "updated": False, "city": city, "country": country}
    db_profile.update_profile(db, current_user, city, country)
    return {"removed": False, "updated": True, "city": city, "country": country}


@router.put("/update_city_country", response_model=ProfileDisplay)
def update_location(city:str,country:str,db:Session = Depends(get_db),current_user: UserAuth=Depends(get_current_user)):
    city = " ".join(city.split())
    country = " ".join(country.split())
    # Both columns are VARCHAR(50); reject cleanly instead of a database error.
    if not city or not country or len(city) > 50 or len(country) > 50:
        raise HTTPException(status_code=400, detail="Please choose a country and a city.")
    from database.closed_countries import check_country
    check_country(country)
    result=db_profile.update_profile(db,current_user,city,country)
    if result is None:
        raise HTTPException(status_code=404,detail="Profiles still doesn't exist")
    return result

@router.put("/bio", response_model=ProfileDisplay)
def update_bio(request:BioUpdate,db:Session = Depends(get_db),current_user: UserAuth=Depends(get_current_user)):
    result=db_profile.update_bio(db,current_user,request.bio)
    if result is None:
        raise HTTPException(status_code=404,detail="Profile still doesn't exist")
    return result

@router.put("/connection", response_model=ProfileDisplay)
def update_connection(request: ConnectionUpdate, db: Session = Depends(get_db), current_user: UserAuth = Depends(get_current_user)):
    """Dating, language exchange or both."""
    result = db_profile.update_connection_type(db, current_user, request.connection_type)
    if result is None:
        raise HTTPException(status_code=404, detail="Profile still doesn't exist")
    return result

@router.put("/pause")
def update_pause(request: PauseUpdate, db: Session = Depends(get_db), current_user: UserAuth = Depends(get_current_user)):
    """"Take a break": hidden from Browse (matches, chats and photos stay)."""
    paused = db_profile.set_paused(db, current_user, request.paused)
    if paused is None:
        raise HTTPException(status_code=404, detail="Profile still doesn't exist")
    return {"paused": paused}

@router.delete("/image/{photo_id}")
def delete_image(photo_id:int,db:Session = Depends(get_db),current_user: UserAuth=Depends(get_current_user)):
    result=db_profile.delete_profile_photo(db,current_user,photo_id)
    if result is None:
        raise HTTPException(status_code=404,detail="Photo not found")
    return {"message":"Photo deleted"}

@router.get(
    "/profile/{profile_id}"
)
def get_conversation(
    profile_id: int,
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):

    return db_profile.get_or_create_conversation(
        db,
        user,
        profile_id
    )