
from sqlalchemy.orm import Session

from database.models import DbProfile
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

