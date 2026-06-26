from database.models import  DbProfile,DbProfileLike,DbConversation,DbProfilePhoto,DbLanguage,DbMessage,DbUser
from routers.schemas import ProfileBase, UserAuth
from sqlalchemy.orm import Session
from datetime import datetime
from database.models import DbMatch
from database import db_block
import cloudinary.uploader
def create_profile(db:Session,request:ProfileBase,user:UserAuth):
    print(request)
    db_profile=DbProfile(
        first_name=user.username,
        bio=request.bio,
        age=request.age,
        gender=request.gender,
        sexual_orientation=request.sexual_orientation,
        height_cm=request.height_cm,
        occupation=request.occupation,
        education=request.education,
        smoking=request.smoking,
        drinking=request.drinking,
        exercise_frequency=request.exercise_frequency,
        has_pets=request.has_pets,
        relationship_goal=request.relationship_goal,
        has_children=request.has_children,
        wants_children=request.wants_children,
        personality_type=request.personality_type,
        city=request.city,
        country=request.country,
        created_at=datetime.now(),
        user_id=user.id
    )
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile

def get_profile(db:Session,user:UserAuth):
     return db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
def get_all_profileslollollol(db:Session,user:UserAuth):
    return db.query(DbProfile).filter(DbProfile.user_id != user.id).all()

def get_all_profiles(db: Session, user: UserAuth):

    current_profile = (
        db.query(DbProfile)
        .filter(DbProfile.user_id == user.id)
        .first()
    )

    if not current_profile:
        return []

    excluded_profile_ids = {current_profile.id}

    # Profiles already liked
    likes = (
        db.query(DbProfileLike)
        .filter(
            DbProfileLike.liker_profile_id == current_profile.id
        )
        .all()
    )

    excluded_profile_ids.update(
        like.liked_profile_id
        for like in likes
    )

    # Profiles already matched
    matches = (
        db.query(DbMatch)
        .filter(
            (DbMatch.profile1_id == current_profile.id)
            |
            (DbMatch.profile2_id == current_profile.id)
        )
        .all()
    )

    for match in matches:

        if match.profile1_id == current_profile.id:
            excluded_profile_ids.add(match.profile2_id)
        else:
            excluded_profile_ids.add(match.profile1_id)

    excluded_profile_ids.update(db_block.get_block_relation_ids(db, current_profile.id))

    profiles = (
        db.query(DbProfile)
        .filter(
            DbProfile.id.notin_(excluded_profile_ids)
        )
        .all()
    )

    return profiles

def get_profile_by_id(db:Session,id:int):
    return db.query(DbProfile).filter(DbProfile.id == id).first()
def update_profile(db:Session,user:UserAuth,city:str,country:str):

    profile_db=db.query(DbProfile).filter(DbProfile.user_id == user.id)
    profile_db.update({
        DbProfile.city:city,
        DbProfile.country:country
    })
    db.commit()
    return profile_db.first()

def update_bio(db:Session,user:UserAuth,bio:str):

    profile_db=db.query(DbProfile).filter(DbProfile.user_id == user.id)
    profile_db.update({
        DbProfile.bio:bio
    })
    db.commit()
    return profile_db.first()

def delete_profile_photo(db:Session,user:UserAuth,photo_id:int):

    profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    if not profile:
        return None

    photo = db.query(DbProfilePhoto).filter(
        DbProfilePhoto.id == photo_id,
        DbProfilePhoto.profile_id == profile.id
    ).first()

    if not photo:
        return None

    if photo.public_id:
        try:
            cloudinary.uploader.destroy(photo.public_id)
        except Exception:
            # Don't block deleting the DB row over a Cloudinary hiccup -
            # worst case is an orphaned asset, not a broken request.
            pass

    db.delete(photo)
    db.commit()
    return photo

def get_profiles_matched(db:Session,user:UserAuth):
    profile_db = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    db_matched=db.query(DbMatch).filter(
        (DbMatch.profile1_id == profile_db.id) |
        (DbMatch.profile2_id == profile_db.id)
    ).all()
    profiles_id=[]
    for match in db_matched:
        if match.profile1_id != profile_db.id :
            profiles_id.append(match.profile1_id)
        elif match.profile2_id != profile_db.id:
            profiles_id.append(match.profile2_id)
    profiles=[]
    for profile_id in profiles_id:
        profiles.append(db.query(DbProfile).filter(DbProfile.id == profile_id).first())
    return profiles

def get_or_create_conversation(
    db: Session,
    user,
    other_profile_id: int
):
    current_profile = (
        db.query(DbProfile)
        .filter(DbProfile.user_id == user.id)
        .first()
    )

    if not current_profile:
        raise Exception("Profile not found")

    match = (
        db.query(DbMatch)
        .filter(
            (
                (DbMatch.profile1_id == current_profile.id) &
                (DbMatch.profile2_id == other_profile_id)
            )
            |
            (
                (DbMatch.profile1_id == other_profile_id) &
                (DbMatch.profile2_id == current_profile.id)
            )
        )
        .first()
    )

    if not match:
        raise Exception("Profiles are not matched")

    conversation = (
        db.query(DbConversation)
        .filter(
            DbConversation.match_id == match.id
        )
        .first()
    )

    if conversation:
        return {
            "conversation_id": conversation.id
        }

    conversation = DbConversation(
        match_id=match.id
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {
        "conversation_id": conversation.id
    }

def delete_account(db: Session, user: UserAuth):
    profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()

    if profile:
        photos = db.query(DbProfilePhoto).filter(DbProfilePhoto.profile_id == profile.id).all()
        for photo in photos:
            if photo.public_id:
                try:
                    cloudinary.uploader.destroy(photo.public_id)
                except Exception:
                    # An orphaned Cloudinary asset isn't worth blocking account deletion over.
                    pass
            db.delete(photo)

        db.query(DbLanguage).filter(DbLanguage.profile_id == profile.id).delete()

        matches = db.query(DbMatch).filter(
            (DbMatch.profile1_id == profile.id) | (DbMatch.profile2_id == profile.id)
        ).all()
        for match in matches:
            conversation = db.query(DbConversation).filter(DbConversation.match_id == match.id).first()
            if conversation:
                db.query(DbMessage).filter(DbMessage.conversation_id == conversation.id).delete()
                db.delete(conversation)
            db.delete(match)

        db.query(DbProfileLike).filter(
            (DbProfileLike.liker_profile_id == profile.id) | (DbProfileLike.liked_profile_id == profile.id)
        ).delete()

        db.delete(profile)

    db_user = db.query(DbUser).filter(DbUser.id == user.id).first()
    db.delete(db_user)
    db.commit()
    return {"message": "Account deleted"}