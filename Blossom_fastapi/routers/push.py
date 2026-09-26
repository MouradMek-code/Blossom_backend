from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database import db_push
from database.database import get_db
from routers.schemas import PushTokenRegister, PushTokenUnregister, UserAuth

router = APIRouter(
    prefix="/push",
    tags=["push notifications"],
)


@router.post("/register")
def register_push_token(
    payload: PushTokenRegister,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Called by the app after login: this phone should get this account's
    notifications. Safe to call on every app start."""
    if not db_push.is_expo_token(payload.token):
        raise HTTPException(status_code=400, detail="Invalid push token.")
    db_push.register_token(db, current_user.id, payload.token, payload.language)
    return {"ok": True}


@router.post("/unregister")
def unregister_push_token(
    payload: PushTokenUnregister,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Called on logout, so a shared phone stops getting the old account's
    notifications."""
    db_push.unregister_token(db, current_user.id, payload.token)
    return {"ok": True}


@router.post("/test")
def send_test_push(
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """Admins: send a test notification to this account's phones and say how
    many there are - 0 means no phone is logged in to this account with
    notifications allowed, so new-profile notifications can't arrive."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return db_push.send_test(db, current_user.id)
