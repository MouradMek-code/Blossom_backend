from sqlalchemy.orm import Session

from database.models import DbProfileLike
from database.models import DbMatch
from database.models import  DbProfile,DbConversation

def like_profile(
    db: Session,
    current_user_id: int,
    liked_profile_id: int
):
    profile_db = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()
    existing = db.query(DbProfileLike).filter(
        DbProfileLike.liker_profile_id == profile_db.id,
        DbProfileLike.liked_profile_id == liked_profile_id
    ).first()

    if existing:
        return {
            "message": "already liked"
        }

    like = DbProfileLike(
        liker_profile_id=profile_db.id,
        liked_profile_id=liked_profile_id
    )

    db.add(like)
    db.commit()
    db.refresh(like)

    reverse_like = db.query(DbProfileLike).filter(
        DbProfileLike.liker_profile_id == liked_profile_id,
        DbProfileLike.liked_profile_id == profile_db.id,
    ).first()

    if reverse_like:

        match = DbMatch(
            profile1_id=min(profile_db.id, liked_profile_id),
            profile2_id=max(profile_db.id, liked_profile_id)
        )

        db.add(match)
        db.commit()
        db.refresh(match)
        conversation = DbConversation(
            match_id=match.id
        )

        db.add(conversation)
        db.commit()
        return {
            "liked": True,
            "matched": True
        }

    return {
        "liked": True,
        "matched": False
    }