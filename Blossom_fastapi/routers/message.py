from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from database.models import  DbProfile,DbProfilePhoto
from auth.oauth2 import get_current_user
from database import db_post,db_message,db_push
from database.database import get_db
from routers.schemas import PostDisplay, PostBase, MessageCreate,ProfilePhotoBase, UserAuth,ProfilePhotoDisplay,ConversationDisplay,MessageDisplay,ChatLive
import cloudinary
import cloudinary.uploader
import os

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# Chat photos: phones resize before sending; this is only the safety net.
MAX_CHAT_PHOTO_BYTES = 10 * 1024 * 1024

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
    profile_id = _my_profile_id(db, user)
    db_message.touch_active(db, profile_id)
    return db_message.get_inbox(db, profile_id)


@router.get("/unread_count")
def unread_count(
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    """Conversations with unread messages - the badge on the Messages link.
    Polled by the app and the website while they're open, so it also keeps
    "active 5 min ago" up to date."""
    profile_id = _my_profile_id(db, user)
    db_message.touch_active(db, profile_id)
    return {"count": db_message.count_unread_conversations(db, profile_id)}


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


@router.get(
    "/conversation/{conversation_id}/live",
    response_model=ChatLive
)
def live(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    """An open chat's poll: messages, "typing...", "active 5 min ago", and
    whether photos can be sent yet."""
    return db_message.get_live(db, conversation_id, _my_profile_id(db, user))


@router.post("/conversation/{conversation_id}/typing")
def typing(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    """The message box is changing (sent every few seconds while typing)."""
    db_message.set_typing(db, conversation_id, _my_profile_id(db, user))
    return {"ok": True}


@router.post(
    "/conversation/{conversation_id}/photo",
    response_model=MessageDisplay
)
def send_photo(
    conversation_id: int,
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user)
):
    """A photo in the chat - once both have written to each other. The other
    person sees it blurred until they tap it."""
    profile_id = _my_profile_id(db, user)
    # Every check before the (slow) upload.
    db_message.check_can_send_photo(db, conversation_id, profile_id)
    content_type = (image.content_type or "").lower()
    if content_type and content_type != "application/octet-stream" and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please choose a photo (JPG, PNG, HEIC...).")
    image.file.seek(0, 2)
    size = image.file.tell()
    image.file.seek(0)
    if size > MAX_CHAT_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="This photo is too big (10 MB max).")
    result = cloudinary.uploader.upload(image.file, folder="blossom_chat")
    try:
        message = db_message.send_message(
            db, conversation_id, profile_id, db_message.PHOTO_CONTENT,
            image=(result["secure_url"], result["public_id"]),
        )
    except HTTPException:
        # Refused after all (blocked in the meantime...): don't keep the file.
        try:
            cloudinary.uploader.destroy(result["public_id"])
        except Exception:
            pass
        raise
    db_push.notify_new_message(db, background_tasks, conversation_id, profile_id, photo=True)
    return message


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