from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.params import Depends
from sqlalchemy.orm import Session
from database import db_profile,db_message
from database.models import DbProfile,DbProfilePhoto
from auth.oauth2 import get_current_user
from database.database import get_db
from routers.schemas import ProfileBase, ProfileDisplay, UserAuth,ProfileDisplayforPhoto,BioUpdate
from routers.schemas import UserAuth,ProfilePhotoDisplay
import cloudinary.uploader
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
async def create_profile(request:ProfileBase,db:Session=Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    return db_profile.create_profile(db,request,current_use)

@router.get("/", response_model=ProfileDisplay)
async def read_profile(current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_profile(db,current_user)

    if result is None:
        raise HTTPException(status_code=404,detail="Profile still doesn't exist")
    return result
@router.get("/profiles/matched", response_model=List[ProfileDisplay])
async def read_profile_matched(current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_profiles_matched(db,current_user)
    return result
@router.get("/all_profile", response_model=List[ProfileDisplay])
async def get_all_profiles(current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_all_profiles(db,current_user)
    if result is None:
        raise HTTPException(status_code=404,detail="Profiles still doesn't exist")
    return result
@router.get("/{id}", response_model=ProfileDisplay)
async def read_profile(id:int,current_user:UserAuth=Depends(get_current_user),db:Session=Depends(get_db)):
    result=db_profile.get_profile_by_id(db,id)

    if result is None:
        raise HTTPException(status_code=404,detail="Profile still doesn't exist")
    return result



@router.post("/image",response_model=ProfilePhotoDisplay)
async def upload_image(image:UploadFile=File(...),db:Session = Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    result = cloudinary.uploader.upload(image.file)
    db_profile_instance = db.query(DbProfile).filter(DbProfile.user_id == current_use.id).first()
    db_profile_photo = DbProfilePhoto(
        image_url=result["secure_url"],
        public_id=result["public_id"],
        profile_id=db_profile_instance.id
    )
    db.add(db_profile_photo)
    db.commit()
    db.refresh(db_profile_photo)
    return db_profile_photo

@router.put("/update_city_country", response_model=ProfileDisplay)
def update_location(city:str,country:str,db:Session = Depends(get_db),current_user: UserAuth=Depends(get_current_user)):
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