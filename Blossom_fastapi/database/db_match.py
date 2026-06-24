
from sqlalchemy.orm import Session

from database.models import DbProfile, DbProfileLike, DbConversation, DbMessage
from database.models import DbMatch
def get_matches(
    db: Session,
    current_user_id: int
):
    profile_db = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()
    return db.query(DbMatch).filter(
        (DbMatch.profile1_id == profile_db.id) |
        (DbMatch.profile2_id == profile_db.id)
    ).all()


def count_unseen_matches(
    db: Session,
    current_user_id: int
):
    profile_db = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()
    return db.query(DbMatch).filter(
        ((DbMatch.profile1_id == profile_db.id) & (DbMatch.seen_by_profile1 == False)) |  # noqa: E712
        ((DbMatch.profile2_id == profile_db.id) & (DbMatch.seen_by_profile2 == False))  # noqa: E712
    ).count()


def mark_matches_seen(
    db: Session,
    current_user_id: int
):
    profile_db = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()

    db.query(DbMatch).filter(
        DbMatch.profile1_id == profile_db.id,
        DbMatch.seen_by_profile1 == False,  # noqa: E712
    ).update({DbMatch.seen_by_profile1: True})

    db.query(DbMatch).filter(
        DbMatch.profile2_id == profile_db.id,
        DbMatch.seen_by_profile2 == False,  # noqa: E712
    ).update({DbMatch.seen_by_profile2: True})

    db.commit()


def unmatch(
    db: Session,
    current_user_id: int,
    other_profile_id: int
):
    """Removes the match (+ its conversation/messages) between the current
    user and other_profile_id, and removes the current user's like on
    that profile so it can show up in Browse again. The other profile's
    like of the current user is left alone - they may still see this
    profile under Likes You afterward, which is fine since they never
    took back their own like."""
    profile = db.query(DbProfile).filter(DbProfile.user_id == current_user_id).first()
    if not profile:
        return None

    match = db.query(DbMatch).filter(
        ((DbMatch.profile1_id == profile.id) & (DbMatch.profile2_id == other_profile_id)) |
        ((DbMatch.profile1_id == other_profile_id) & (DbMatch.profile2_id == profile.id))
    ).first()

    if not match:
        return None

    conversation = db.query(DbConversation).filter(DbConversation.match_id == match.id).first()
    if conversation:
        db.query(DbMessage).filter(DbMessage.conversation_id == conversation.id).delete()
        db.delete(conversation)

    db.query(DbProfileLike).filter(
        DbProfileLike.liker_profile_id == profile.id,
        DbProfileLike.liked_profile_id == other_profile_id
    ).delete()

    db.delete(match)
    db.commit()
    return True

