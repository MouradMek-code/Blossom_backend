from fastapi import HTTPException
from database.models import DbLanguage, DbLearningLanguage, DbProfile
from routers.schemas import ProfileBaseLanguage, UserAuth
from sqlalchemy.orm import Session


def _add_once(db: Session, model, request: ProfileBaseLanguage, user: UserAuth):
    """Adds a language to the member's profile. Sending it again (the app
    retrying after a lost answer) gives back the one already there instead
    of a second copy."""
    db_profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Create your profile first.")
    entry = db.query(model).filter(
        model.profile_id == db_profile.id, model.language_name == request.language_name
    ).first()
    if entry:
        return entry
    entry = model(language_name=request.language_name, profile_id=db_profile.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def create_languages(db: Session, request: ProfileBaseLanguage, user: UserAuth):
    return _add_once(db, DbLanguage, request, user)


def get_languages(db: Session, user: UserAuth):
    return db.query(DbProfile).filter(DbProfile.user_id == user.id).first().languages


def create_learning_languages(db: Session, request: ProfileBaseLanguage, user: UserAuth):
    return _add_once(db, DbLearningLanguage, request, user)


def get_learning_languages(db: Session, user: UserAuth):
    return db.query(DbProfile).filter(DbProfile.user_id == user.id).first().learning_languages
