from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database.database import get_db
from database import db_match
router = APIRouter(
    prefix="/matches",
    tags=["matches"]
)
@router.get("")
def matches(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return db_match.get_matches(
        db,
        current_user.id
    )