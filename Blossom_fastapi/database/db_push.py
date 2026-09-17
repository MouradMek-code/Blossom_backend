"""Phone notifications (new message, match, like) through Expo's push service,
which delivers to Android phones via Firebase Cloud Messaging.

Sending happens in a FastAPI background task after the response, so a slow or
failing push never delays or breaks the action that triggered it.
"""
import logging
import os

import requests
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import DbConversation, DbProfile, DbPushToken

log = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
LANGUAGES = ("en", "fr", "zh", "ar")

# Deliberately content-free: a lock screen shows who wrote, never what they
# wrote, and a like never says who it's from (that's what Likes You is for).
TEXTS = {
    "message": {
        "en": "💬 New message from {name}",
        "fr": "💬 Nouveau message de {name}",
        "zh": "💬 {name} 给你发来一条新消息",
        "ar": "💬 رسالة جديدة من {name}",
    },
    "match": {
        "en": "💕 It's a match with {name}!",
        "fr": "💕 C'est un match avec {name} !",
        "zh": "💕 你和 {name} 配对成功！",
        "ar": "💕 تطابق جديد مع {name}!",
    },
    "like": {
        "en": "🌸 Someone likes you",
        "fr": "🌸 Quelqu'un vous aime",
        "zh": "🌸 有人喜欢你",
        "ar": "🌸 شخص ما معجب بك",
    },
}


def is_expo_token(token: str) -> bool:
    return bool(token) and token.startswith(("ExponentPushToken[", "ExpoPushToken[")) and token.endswith("]")


def normalize_language(language) -> str:
    code = (language or "").strip().lower()[:2]
    return code if code in LANGUAGES else "en"


def register_token(db: Session, user_id: int, token: str, language=None):
    row = db.query(DbPushToken).filter(DbPushToken.token == token).first()
    if row:
        row.user_id = user_id  # same phone, possibly another account now
        row.language = normalize_language(language)
    else:
        db.add(DbPushToken(user_id=user_id, token=token, language=normalize_language(language)))
    db.commit()


def unregister_token(db: Session, user_id: int, token: str):
    db.query(DbPushToken).filter(
        DbPushToken.user_id == user_id,
        DbPushToken.token == token,
    ).delete(synchronize_session=False)
    db.commit()


def delete_user_tokens(db: Session, user_id: int):
    db.query(DbPushToken).filter(DbPushToken.user_id == user_id).delete(synchronize_session=False)


def _messages_for_profile(db: Session, profile_id: int, kind: str, name: str, data: dict):
    """One push per phone of the person behind profile_id, each in that
    phone's language."""
    profile = db.query(DbProfile).filter(DbProfile.id == profile_id).first()
    if not profile or not profile.user_id:
        return []
    tokens = db.query(DbPushToken).filter(DbPushToken.user_id == profile.user_id).all()
    return [
        {
            "to": row.token,
            "title": "Blossom",
            "body": TEXTS[kind][normalize_language(row.language)].format(name=name or ""),
            "data": data,
            "sound": "default",
            "channelId": "default",
            "priority": "high",
        }
        for row in tokens
    ]


def send_push_messages(messages):
    """POST to Expo in chunks. Runs after the response - must never raise.
    Tokens Expo reports as no longer registered (app uninstalled, data
    cleared) are removed so we stop sending to them."""
    if not messages:
        return
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    access_token = os.getenv("EXPO_ACCESS_TOKEN")  # only if "enhanced push security" is on
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    dead_tokens = []
    for start in range(0, len(messages), 100):
        chunk = messages[start:start + 100]
        try:
            resp = requests.post(EXPO_PUSH_URL, json=chunk, headers=headers, timeout=10)
            tickets = resp.json().get("data") or []
        except Exception as exc:  # network error, bad JSON, ...
            log.warning("Expo push request failed: %s", exc)
            continue
        if isinstance(tickets, dict):
            tickets = [tickets]
        for message, ticket in zip(chunk, tickets):
            if ticket.get("status") != "error":
                continue
            error = (ticket.get("details") or {}).get("error")
            if error == "DeviceNotRegistered":
                dead_tokens.append(message["to"])
            else:
                log.warning("Expo push error for a token: %s", ticket.get("message"))

    if dead_tokens:
        db = SessionLocal()
        try:
            db.query(DbPushToken).filter(DbPushToken.token.in_(dead_tokens)).delete(synchronize_session=False)
            db.commit()
        except Exception as exc:
            log.warning("Could not remove dead push tokens: %s", exc)
        finally:
            db.close()


def _queue(background_tasks: BackgroundTasks, messages):
    if messages:
        background_tasks.add_task(send_push_messages, messages)


def notify_new_message(db: Session, background_tasks: BackgroundTasks, conversation_id: int, sender_profile_id: int):
    """"💬 New message from Wendy" to the other person in the conversation.
    Called after send_message succeeded, so access, blocks and the
    women-write-first rule have already been checked."""
    conversation = db.query(DbConversation).filter(DbConversation.id == conversation_id).first()
    sender = db.query(DbProfile).filter(DbProfile.id == sender_profile_id).first()
    if not conversation or not sender:
        return
    match = conversation.match
    recipient_id = match.profile2_id if match.profile1_id == sender_profile_id else match.profile1_id
    _queue(background_tasks, _messages_for_profile(
        db, recipient_id, "message", sender.first_name,
        {"type": "message", "conversationId": conversation_id},
    ))


def notify_like(db: Session, background_tasks: BackgroundTasks, liker_profile_id: int, liked_profile_id: int, matched: bool):
    """A new like: "It's a match with ..." if it completed a match, otherwise
    an anonymous "Someone likes you". Only the other person is notified - the
    one who tapped like is looking at the app already."""
    liker = db.query(DbProfile).filter(DbProfile.id == liker_profile_id).first()
    if not liker:
        return
    if matched:
        messages = _messages_for_profile(db, liked_profile_id, "match", liker.first_name, {"type": "match"})
    else:
        messages = _messages_for_profile(db, liked_profile_id, "like", "", {"type": "like"})
    _queue(background_tasks, messages)
