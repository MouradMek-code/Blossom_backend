from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session
from database import db_languages
from auth.oauth2 import get_current_user
from database.database import get_db
from routers.schemas import ProfileBaseLanguage, ProfileLanguageDisplay, UserAuth

router = APIRouter(
    prefix="/profile_language",
    tags=["profile_language"],
)

@router.post("/", response_model=ProfileLanguageDisplay)
async def create_profile(request:ProfileBaseLanguage,db:Session=Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    return db_languages.create_languages(db,request,current_use)