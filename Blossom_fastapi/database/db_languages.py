from fastapi import HTTPException
from fastapi.openapi.utils import status_code_ranges

from database.models import  DbLanguage,DbProfile
from routers.schemas import ProfileBaseLanguage, UserAuth
from sqlalchemy.orm import Session
from datetime import datetime

def create_languages(db:Session,request:ProfileBaseLanguage,user:UserAuth):
    db_profile=db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    db_profile_language=DbLanguage(
        language_name=request.language_name,
        profile_id=db_profile.id
    )
    db.add(db_profile_language)
    db.commit()
    db.refresh(db_profile_language)

    return db_profile_language

def get_languages(db:Session,request:ProfileBaseLanguage,user:UserAuth):
    return db.query(DbProfile).filter(DbProfile.user_id == user.id).first().languages