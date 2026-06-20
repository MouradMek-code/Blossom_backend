
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

