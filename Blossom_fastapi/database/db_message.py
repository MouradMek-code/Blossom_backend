from fastapi import HTTPException
from database.models import DbPost,DbMessage,DbConversation,DbMatch
from routers.schemas import UserBase, PostBase
from sqlalchemy.orm import Session
from datetime import datetime


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