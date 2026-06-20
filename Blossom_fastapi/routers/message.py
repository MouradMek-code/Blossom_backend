from fastapi import APIRouter, Depends
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.models import  DbProfile,DbProfilePhoto
from auth.oauth2 import get_current_user
from database import db_post,db_message
from database.database import get_db
from routers.schemas import PostDisplay, PostBase, MessageCreate,ProfilePhotoBase, UserAuth,ProfilePhotoDisplay,ConversationDisplay,MessageDisplay
import cloudinary.uploader

router = APIRouter(
    prefix="/messages",
    tags=["Messages"]
)

@router.get(
    "/conversations",
    response_model=list[ConversationDisplay]
)
def conversations(
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    return db_message.get_my_conversations(
        db,
        user
    )

@router.get(
    "/conversation/{conversation_id}",
    response_model=list[MessageDisplay]
)
def messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    return db_message.get_messages(
        db,
        conversation_id
    )


@router.post(
    "/conversation/{conversation_id}"
)
def send(
    conversation_id: int,
    request: MessageCreate,
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    db_profile_instance = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    return db_message.send_message(
        db,
        conversation_id,
        db_profile_instance.id,
        request.content
    )