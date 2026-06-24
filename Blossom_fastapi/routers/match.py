from fastapi import APIRouter
from fastapi import Depends, HTTPException

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

@router.delete("/unmatch/{profile_id}")
def unmatch(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = db_match.unmatch(db, current_user.id, profile_id)
    if not result:
        raise HTTPException(status_code=404, detail="Match not found")
    return {"message": "Unmatched"}