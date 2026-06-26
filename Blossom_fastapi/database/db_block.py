from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.models import DbBlock, DbProfile


def _current_profile(db: Session, user_id: int) -> DbProfile:
    profile = db.query(DbProfile).filter(DbProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def block_profile(db: Session, user_id: int, blocked_profile_id: int):
    profile = _current_profile(db, user_id)

    if profile.id == blocked_profile_id:
        raise HTTPException(status_code=400, detail="You can't block yourself")

    existing = db.query(DbBlock).filter(
        DbBlock.blocker_profile_id == profile.id,
        DbBlock.blocked_profile_id == blocked_profile_id
    ).first()

    if existing:
        return {"message": "already blocked"}

    db.add(DbBlock(blocker_profile_id=profile.id, blocked_profile_id=blocked_profile_id))
    db.commit()
    return {"message": "blocked"}


def unblock_profile(db: Session, user_id: int, blocked_profile_id: int):
    profile = _current_profile(db, user_id)

    db.query(DbBlock).filter(
        DbBlock.blocker_profile_id == profile.id,
        DbBlock.blocked_profile_id == blocked_profile_id
    ).delete()
    db.commit()
    return {"message": "unblocked"}


def get_blocked_profile_ids(db: Session, user_id: int):
    profile = _current_profile(db, user_id)

    blocks = db.query(DbBlock).filter(DbBlock.blocker_profile_id == profile.id).all()
    return [b.blocked_profile_id for b in blocks]


def get_block_relation_ids(db: Session, profile_id: int):
    """Profile ids that are blocked in either direction relative to
    profile_id - used to hide blocked users from browse/likes in both
    directions, not just the one who initiated the block."""
    blocks = db.query(DbBlock).filter(
        (DbBlock.blocker_profile_id == profile_id) | (DbBlock.blocked_profile_id == profile_id)
    ).all()

    ids = set()
    for b in blocks:
        ids.add(b.blocked_profile_id if b.blocker_profile_id == profile_id else b.blocker_profile_id)
    return ids


def is_blocked_either_direction(db: Session, profile_id_a: int, profile_id_b: int) -> bool:
    return db.query(DbBlock).filter(
        (
            (DbBlock.blocker_profile_id == profile_id_a) & (DbBlock.blocked_profile_id == profile_id_b)
        )
        |
        (
            (DbBlock.blocker_profile_id == profile_id_b) & (DbBlock.blocked_profile_id == profile_id_a)
        )
    ).first() is not None
