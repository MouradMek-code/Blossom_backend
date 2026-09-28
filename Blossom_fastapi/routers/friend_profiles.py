"""Admins create a profile for a friend; the friend confirms it from an email
link (see database/db_friend_profiles.py)."""
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from auth import oauth2
from database import db_friend_profiles
from database.database import get_db
from routers.schemas import FriendProfileClaim, FriendProfileCreate, FriendProfileSend, UserAuth
from routers.user import require_admin

router = APIRouter(prefix="/friend_profiles", tags=["friend profiles"])


# ---- admin -------------------------------------------------------------------
@router.get("")
def list_friend_profiles(db: Session = Depends(get_db), _: UserAuth = Depends(require_admin)):
    return db_friend_profiles.list_all(db)


@router.post("")
def create_friend_profile(
    request: FriendProfileCreate,
    db: Session = Depends(get_db),
    admin: UserAuth = Depends(require_admin),
):
    return db_friend_profiles.create(db, admin, request)


@router.post("/{user_id}/photos")
def add_friend_photo(
    user_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: UserAuth = Depends(require_admin),
):
    return db_friend_profiles.add_photo(db, user_id, image)


@router.delete("/{user_id}/photos/{photo_id}")
def remove_friend_photo(
    user_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
    _: UserAuth = Depends(require_admin),
):
    return db_friend_profiles.remove_photo(db, user_id, photo_id)


@router.post("/{user_id}/send")
def send_friend_link(
    user_id: int,
    background_tasks: BackgroundTasks,
    request: FriendProfileSend = FriendProfileSend(),
    db: Session = Depends(get_db),
    _: UserAuth = Depends(require_admin),
):
    return db_friend_profiles.send_link(db, user_id, background_tasks, request.language)


@router.delete("/{user_id}")
def delete_friend_profile(user_id: int, db: Session = Depends(get_db), _: UserAuth = Depends(require_admin)):
    return db_friend_profiles.delete_pending(db, user_id)


# ---- the friend, from the email link (no account needed) ---------------------
@router.get("/claim/{token}")
def claim_preview(token: str, db: Session = Depends(get_db)):
    return db_friend_profiles.preview(db, token)


@router.post("/claim/{token}")
def claim_profile(token: str, request: FriendProfileClaim, db: Session = Depends(get_db)):
    if not request.accept_terms:
        raise HTTPException(status_code=400, detail="Please accept the terms to activate your profile.")
    user = db_friend_profiles.claim(db, token, request.password)
    return {
        "access_token": oauth2.create_access_token(data={"username": user.username}),
        "token_type": "bearer",
        "username": user.username,
        "profile_id": user.profile.id if user.profile else None,
    }


@router.post("/claim/{token}/decline")
def decline_profile(token: str, db: Session = Depends(get_db)):
    return db_friend_profiles.decline(db, token)
