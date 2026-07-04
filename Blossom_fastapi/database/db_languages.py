from database.models import DbLanguage, DbLearningLanguage, DbProfile
from routers.schemas import ProfileBaseLanguage, UserAuth
from sqlalchemy.orm import Session


def create_languages(db: Session, request: ProfileBaseLanguage, user: UserAuth):
    db_profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    entry = DbLanguage(language_name=request.language_name, profile_id=db_profile.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_languages(db: Session, user: UserAuth):
    return db.query(DbProfile).filter(DbProfile.user_id == user.id).first().languages


def create_learning_languages(db: Session, request: ProfileBaseLanguage, user: UserAuth):
    db_profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    entry = DbLearningLanguage(language_name=request.language_name, profile_id=db_profile.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_learning_languages(db: Session, user: UserAuth):
    return db.query(DbProfile).filter(DbProfile.user_id == user.id).first().learning_languages
