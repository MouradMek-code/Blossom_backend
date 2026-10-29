"""Accounts left without a photo are deleted (main.py runs this every 10
minutes).

Sign-up saves the profile before the photo step, so anyone who stopped there
kept an account nobody could see. One hour is left to add a photo (the photo
step itself takes a minute or two); after that the account goes, as do
accounts that never got as far as a profile. Admins and the profiles an admin
made for a friend are never touched.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import db_profile
from database.models import DbProfile, DbUser

GRACE = timedelta(hours=1)


def _deletable_users(db: Session):
    return db.query(DbUser).filter(DbUser.is_admin.isnot(True), DbUser.created_by.is_(None))


def delete_photoless_accounts(db: Session, now: datetime = None) -> int:
    """Returns how many accounts were deleted."""
    # Profiles are dated with local time and users with UTC (as they're
    # saved); on the server both are UTC.
    profile_cutoff = (now or datetime.now()) - GRACE
    user_cutoff = (now or datetime.utcnow()) - GRACE

    no_photo = (
        _deletable_users(db)
        .join(DbProfile, DbProfile.user_id == DbUser.id)
        .filter(
            ~DbProfile.photos.any(),
            or_(DbProfile.created_at.is_(None), DbProfile.created_at < profile_cutoff),
        )
    )
    no_profile = _deletable_users(db).filter(
        ~db.query(DbProfile.id).filter(DbProfile.user_id == DbUser.id).exists(),
        or_(DbUser.created_at.is_(None), DbUser.created_at < user_cutoff),
    )

    deleted = 0
    for user in no_photo.all() + no_profile.all():
        try:
            db_profile.delete_account(db, user)
            deleted += 1
        except Exception as exc:  # one stuck account mustn't stop the others
            db.rollback()
            logging.getLogger(__name__).warning("Couldn't delete photo-less account %s: %s", user.id, exc)
    return deleted
