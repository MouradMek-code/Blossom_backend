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

@router.get("/unseen_count")
def unseen_matches_count(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return {"count": db_match.count_unseen_matches(db, current_user.id)}

@router.post("/mark_seen")
def mark_matches_seen(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    db_match.mark_matches_seen(db, current_user.id)
    return {"status": "ok"}