from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.models import DbProfileLike
from database.models import DbMatch
from database.models import  DbProfile,DbConversation
from database import db_block

def like_profile(
    db: Session,
    current_user_id: int,
    liked_profile_id: int
):
    profile_db = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()

    if db_block.is_blocked_either_direction(db, profile_db.id, liked_profile_id):
        raise HTTPException(status_code=403, detail="You can't like a blocked profile")

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


def count_unseen_likes(
    db: Session,
    current_user_id: int
):
    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()

    matched_profiles = db.query(DbMatch).filter(
        (DbMatch.profile1_id == profile.id) |
        (DbMatch.profile2_id == profile.id)
    ).all()
    matched_ids = [
        m.profile2_id if m.profile1_id == profile.id else m.profile1_id
        for m in matched_profiles
    ]

    return db.query(DbProfileLike).filter(
        DbProfileLike.liked_profile_id == profile.id,
        DbProfileLike.seen == False,  # noqa: E712
        ~DbProfileLike.liker_profile_id.in_(matched_ids)
    ).count()


def mark_likes_seen(
    db: Session,
    current_user_id: int
):
    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()

    db.query(DbProfileLike).filter(
        DbProfileLike.liked_profile_id == profile.id,
        DbProfileLike.seen == False,  # noqa: E712
    ).update({DbProfileLike.seen: True})

    db.commit()


def likes_summary(db: Session, current_user_id: int, photo_count: int = 3):
    """The "Likes you" circle at the top of Chats: how many people like me
    (not matched yet, not blocked either way), how many are new, and the first
    photo of the latest few - the circle shows them blurred."""
    from database.models import DbProfilePhoto

    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()
    if not profile:
        return {"total": 0, "new": 0, "photos": []}
    matched = db.query(DbMatch).filter(
        (DbMatch.profile1_id == profile.id) | (DbMatch.profile2_id == profile.id)
    ).all()
    hidden = {m.profile2_id if m.profile1_id == profile.id else m.profile1_id for m in matched}
    hidden |= set(db_block.get_block_relation_ids(db, profile.id))

    likes = [
        (liker_id, seen)
        for liker_id, seen in db.query(DbProfileLike.liker_profile_id, DbProfileLike.seen)
        .filter(DbProfileLike.liked_profile_id == profile.id)
        .order_by(DbProfileLike.created_at.desc(), DbProfileLike.id.desc())
        .all()
        if liker_id not in hidden
    ]
    latest = [liker_id for liker_id, _ in likes[:photo_count]]
    first_photo = {}
    if latest:
        for profile_id, url in (
            db.query(DbProfilePhoto.profile_id, DbProfilePhoto.image_url)
            .filter(DbProfilePhoto.profile_id.in_(latest))
            .order_by(DbProfilePhoto.id)
            .all()
        ):
            first_photo.setdefault(profile_id, url)
    return {
        "total": len(likes),
        "new": sum(1 for _, seen in likes if not seen),
        "photos": [first_photo[i] for i in latest if i in first_photo],
    }
