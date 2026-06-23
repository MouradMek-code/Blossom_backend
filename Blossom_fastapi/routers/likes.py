from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database.database import get_db
from database import db_like
from routers.schemas import UserAuth
from database.models import DbProfileLike,DbProfile,DbMatch

router = APIRouter(
    prefix="/likes",
    tags=["Likes"]
)

@router.post("/{liked_profile_id}")
def like_profile(
    liked_profile_id: int,
    db: Session = Depends(get_db),
    current_user: UserAuth=Depends(get_current_user)
):
    return db_like.like_profile(
        db,
        current_user.id,
        liked_profile_id
    )

@router.get("/profile_likes/unseen_count")
def unseen_likes_count(
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    return {"count": db_like.count_unseen_likes(db, current_user.id)}

@router.post("/profile_likes/mark_seen")
def mark_likes_seen(
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    db_like.mark_likes_seen(db, current_user.id)
    return {"status": "ok"}

@router.get("/profile_likes")
def profile_liker(db: Session = Depends(get_db),
    current_user: UserAuth=Depends(get_current_user)
):
    profile=db.query(DbProfile).filter(DbProfile.user_id == current_user.id).first()
    matched_profiles=db.query(DbMatch).filter(
        (DbMatch.profile1_id == profile.id) |
        (DbMatch.profile2_id == profile.id)
    ).all()
    matched_ids = []

    for match in matched_profiles:
        if match.profile1_id == profile.id:
            matched_ids.append(match.profile2_id)
        else:
            matched_ids.append(match.profile1_id)
    profileslikers = db.query(DbProfileLike).filter(
        DbProfileLike.liked_profile_id == profile.id,
        ~DbProfileLike.liker_profile_id.in_(matched_ids)
    ).all()

    if profileslikers:
      profileslikersid=[]
      for profilesliker in profileslikers:
         profileslikersid.append(profilesliker.liker_profile_id)
         return profileslikersid
    return []

@router.get("/profiles_i_liked")
def profiles_i_liked(
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    profile = db.query(DbProfile).filter(
        DbProfile.user_id == current_user.id
    ).first()

    profile_likes = db.query(DbProfileLike).filter(
        DbProfileLike.liker_profile_id == profile.id
    ).all()

    liked_profile_ids = []

    for like in profile_likes:
        liked_profile_ids.append(like.liked_profile_id)

    return liked_profile_ids