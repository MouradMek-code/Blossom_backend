from fastapi import HTTPException
from database.models import DbPost,DbMessage,DbConversation,DbMatch
from routers.schemas import UserBase, PostBase
from sqlalchemy.orm import Session
from datetime import datetime


def send_message(
    db: Session,
    conversation_id: int,
    profile_id: int,
    content: str
):

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
    conversation_id: int
):

    return (
        db.query(DbMessage)
        .filter(
            DbMessage.conversation_id == conversation_id
        )
        .order_by(DbMessage.created_at)
        .all()
    )