from fastapi import HTTPException
from database.models import DbPost,DbMessage,DbConversation,DbMatch,DbProfile
from routers.schemas import UserBase, PostBase
from sqlalchemy.orm import Session
from datetime import datetime
from database import db_block


def get_conversation_for_profile(
    db: Session,
    conversation_id: int,
    profile_id: int
):
    """Returns the conversation only if profile_id is one of the two
    matched profiles on it - None otherwise, so callers can reject
    access to conversations the caller isn't part of."""
    return (
        db.query(DbConversation)
        .join(DbMatch)
        .filter(
            DbConversation.id == conversation_id,
            (DbMatch.profile1_id == profile_id) | (DbMatch.profile2_id == profile_id)
        )
        .first()
    )


def send_message(
    db: Session,
    conversation_id: int,
    profile_id: int,
    content: str
):
    conversation = get_conversation_for_profile(db, conversation_id, profile_id)
    if not conversation:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this conversation"
        )

    match = conversation.match
    other_profile_id = (
        match.profile2_id if match.profile1_id == profile_id else match.profile1_id
    )
    if db_block.is_blocked_either_direction(db, profile_id, other_profile_id):
        raise HTTPException(status_code=403, detail="You can't message a blocked profile")

    first_message = db.query(DbMessage).filter(
        DbMessage.conversation_id == conversation_id
    ).first() is None

    if first_message:
        sender_profile = db.query(DbProfile).filter(DbProfile.id == profile_id).first()
        other_profile = db.query(DbProfile).filter(DbProfile.id == other_profile_id).first()
        genders = {sender_profile.gender, other_profile.gender}

        if genders == {"Man", "Woman"} and sender_profile.gender == "Man":
            raise HTTPException(
                status_code=403,
                detail="In a match between a man and a woman, the woman has to send the first message"
            )

    message = DbMessage(
        conversation_id=conversation_id,
        sender_profile_id=profile_id,
        content=content
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message

def get_my_conversations(
    db: Session,
    profile_id: int
):

    return (
        db.query(DbConversation)
        .join(DbMatch)
        .filter(
            (DbMatch.profile1_id == profile_id)
            |
            (DbMatch.profile2_id == profile_id)
        )
        .all()
    )

def get_messages(
    db: Session,
    conversation_id: int,
    profile_id: int
):
    conversation = get_conversation_for_profile(db, conversation_id, profile_id)
    if not conversation:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this conversation"
        )

    return (
        db.query(DbMessage)
        .filter(
            DbMessage.conversation_id == conversation_id
        )
        .order_by(DbMessage.created_at)
        .all()
    )