from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database import db_verification
from database.database import get_db
from routers.schemas import UserAuth

router = APIRouter(
    prefix="/verification",
    tags=["Verification"],
)


class RejectIn(BaseModel):
    reason: str  # "pose" | "face" | "blurry"


def _require_admin(user):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/me")
def my_verification(db: Session = Depends(get_db), current_user: UserAuth = Depends(get_current_user)):
    """Where my ✓ badge stands, and the pose to copy for the selfie."""
    return db_verification.status(db, current_user)


@router.post("")
def send_selfie(
    background_tasks: BackgroundTasks,
    selfie: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    """The selfie copying the pose; the admins are told."""
    return db_verification.submit(db, current_user, selfie, background_tasks)


@router.get("/admin")
def pending_selfies(db: Session = Depends(get_db), current_user: UserAuth = Depends(get_current_user)):
    _require_admin(current_user)
    return db_verification.list_pending(db)


@router.post("/admin/{verification_id}/approve")
def approve(
    verification_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    _require_admin(current_user)
    return db_verification.decide(db, verification_id, True, None, background_tasks)


@router.post("/admin/{verification_id}/reject")
def reject(
    verification_id: int,
    request: RejectIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user),
):
    _require_admin(current_user)
    return db_verification.decide(db, verification_id, False, request.reason, background_tasks)
