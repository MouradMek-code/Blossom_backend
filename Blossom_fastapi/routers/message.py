from fastapi import APIRouter, Depends
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from database.models import  DbProfile,DbProfilePhoto
from auth.oauth2 import get_current_user
from database import db_post,db_message,db_push
from database.database import get_db
from routers.schemas import PostDisplay, PostBase, MessageCreate,ProfilePhotoBase, UserAuth,ProfilePhotoDisplay,ConversationDisplay,MessageDisplay
import cloudinary.uploader

router = APIRouter(
    prefix="/messages",
    tags=["Messages"]
)


def _my_profile_id(db: Session, user: UserAuth) -> int:
    profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Finish creating your profile first.")
    return profile.id


@router.get("/inbox")
def inbox(
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    """The Messages page: every match with its last message and unread count."""
    return db_message.get_inbox(db, _my_profile_id(db, user))


@router.get("/unread_count")
def unread_count(
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    """Conversations with unread messages - the badge on the Messages link."""
    return {"count": db_message.count_unread_conversations(db, _my_profile_id(db, user))}


@router.get("/conversation/{conversation_id}/details")
def conversation_details(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    """Name and photo of the person on the other side, for the chat header."""
    return db_message.get_conversation_details(db, conversation_id, _my_profile_id(db, user))

@router.get(
    "/conversations",
    response_model=list[ConversationDisplay]
)
def conversations(
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    db_profile_instance = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    return db_message.get_my_conversations(
        db,
        db_profile_instance.id
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
    db_profile_instance = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    return db_message.get_messages(
        db,
        conversation_id,
        db_profile_instance.id
    )


@router.post(
    "/conversation/{conversation_id}"
)
def send(
    conversation_id: int,
    request: MessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    db_profile_instance = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    message = db_message.send_message(
        db,
        conversation_id,
        db_profile_instance.id,
        request.content
    )
    # Only reached if the message was accepted (access, blocks, who writes first).
    db_push.notify_new_message(db, background_tasks, conversation_id, db_profile_instance.id)
    return message