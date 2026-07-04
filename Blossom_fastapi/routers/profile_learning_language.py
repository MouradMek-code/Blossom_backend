from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session
from database import db_languages
from auth.oauth2 import get_current_user
from database.database import get_db
from routers.schemas import ProfileBaseLanguage, ProfileLearningLanguageDisplay, UserAuth

router = APIRouter(
    prefix="/profile_learning_language",
    tags=["profile_learning_language"],
)

@router.post("/", response_model=ProfileLearningLanguageDisplay)
async def create_learning_language(request: ProfileBaseLanguage, db: Session = Depends(get_db), current_use: UserAuth = Depends(get_current_user)):
    return db_languages.create_learning_languages(db, request, current_use)
