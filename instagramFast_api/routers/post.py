from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.models import  DbProfile,DbProfilePhoto
from auth.oauth2 import get_current_user
from database import db_post
from database.database import get_db
from routers.schemas import PostDisplay, PostBase, ProfilePhotoBase, UserAuth,ProfilePhotoDisplay
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
image_type=["absolute","relative"]

@router.post('', response_model=PostDisplay)
async def create_post(request:PostBase,db:Session = Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    if request.image_type  not in image_type:
           raise HTTPException(status_code=400,detail="Image type not supported")

    return  db_post.create_post(db,request,current_use.id)

@router.get('/all', response_model=list[PostDisplay])
async def get_posts_all(db:Session = Depends(get_db)):
    return db_post.get_all_posts(db)


@router.get('/{user_id}', response_model=PostDisplay)
async def get_post_by_user_id(user_id :int,db:Session = Depends(get_db)):
    return db_post.get_post_by_user_id(db,user_id)

@router.delete('delete/{post_id}')
async def delete_post(post_id:int,db:Session = Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    return db_post.delete_post_by_id(db,post_id,current_use.id)

