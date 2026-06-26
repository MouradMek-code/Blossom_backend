from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database.database import get_db
from database import db_block
from routers.schemas import UserAuth

router = APIRouter(
    prefix="/blocks",
    tags=["Blocks"]
)


@router.post("/{blocked_profile_id}")
def block_profile(
    blocked_profile_id: int,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    return db_block.block_profile(db, current_user.id, blocked_profile_id)


@router.delete("/{blocked_profile_id}")
def unblock_profile(
    blocked_profile_id: int,
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    return db_block.unblock_profile(db, current_user.id, blocked_profile_id)


@router.get("")
def list_blocked_profiles(
    db: Session = Depends(get_db),
    current_user: UserAuth = Depends(get_current_user)
):
    return db_block.get_blocked_profile_ids(db, current_user.id)
