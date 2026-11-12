from fastapi import HTTPException
from database.models import DbPost,DbMessage,DbConversation,DbMatch,DbProfile
from routers.schemas import UserBase, PostBase
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from datetime import datetime, timedelta
from database import db_block
import cloudinary.uploader

# What a photo message says to anything that can't show the photo (older app
# versions, the Messages list, notifications).
PHOTO_CONTENT = "📷 Photo"
# A "typing" ping this recent means they're still typing (clients ping every
# few seconds while the box changes).
TYPING_FRESH_SECONDS = 6
# last_active_at is written at most once a minute per person.
ACTIVE_EVERY_SECONDS = 60


def touch_active(db: Session, profile_id: int, now: datetime = None):
    """The member is on Blossom right now (called from what the app and the
    website poll: the unread badge, the inbox, an open chat)."""
    now = now or datetime.utcnow()
    updated = db.query(DbProfile).filter(
        DbProfile.id == profile_id,
        or_(
            DbProfile.last_active_at.is_(None),
            DbProfile.last_active_at < now - timedelta(seconds=ACTIVE_EVERY_SECONDS),
        ),
    ).update({DbProfile.last_active_at: now}, synchronize_session=False)
    if updated:
        db.commit()


def _typing_column(match, profile_id: int) -> str:
    return "profile1_typing_at" if match.profile1_id == profile_id else "profile2_typing_at"


def _other_id(match, profile_id: int) -> int:
    return match.profile2_id if match.profile1_id == profile_id else match.profile1_id


def _both_have_written(messages, profile_id: int, other_id: int) -> bool:
    """Photos wait until both have written (typed messages; invites and
    photos don't count)."""
    senders = {m.sender_profile_id for m in messages if not m.image_url and not m.date_spot_id}
    return profile_id in senders and other_id in senders


def _must_write_first(me: DbProfile, other: DbProfile) -> bool:
    """True if `me` isn't allowed to open this conversation: in a man/woman
    dating match, the woman sends the first message.

    A match with someone who's only here for language exchange is a language
    exchange (that's all Browse lets them share), so either can write first."""
    if "language" in (me.connection_type, other.connection_type):
        return False
    return {me.gender, other.gender} == {"Man", "Woman"} and me.gender == "Man"


def first_move(me: DbProfile, other: DbProfile):
    """Who opens this conversation, from `me`'s side: "you" (she), "them"
    (he waits for her) or None (anyone can)."""
    if me is None or other is None:
        return None
    if _must_write_first(me, other):
        return "them"
    if _must_write_first(other, me):
        return "you"
    return None


def _profile_card(profile: DbProfile) -> dict:
    """The bit of a profile that chat screens show: name, age and main photo."""
    return {
        "id": profile.id,
        "first_name": profile.first_name,
        "age": profile.age,
        "photo": profile.photos[0].image_url if profile.photos else None,
    }


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
    content: str,
    date_spot_id: int = None,
    image: tuple = None,
):
    # Date spot invites come through here too, so they obey exactly the same
    # rules as typed messages: access, blocks, and who may write first.
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

        if _must_write_first(sender_profile, other_profile):
            raise HTTPException(
                status_code=403,
                detail="In a match between a man and a woman, the woman has to send the first message"
            )

    message = DbMessage(
        conversation_id=conversation_id,
        sender_profile_id=profile_id,
        content=content,
        date_spot_id=date_spot_id,
        image_url=image[0] if image else None,
        image_public_id=image[1] if image else None,
    )

    db.add(message)
    # Sent: no longer typing, and on Blossom right now.
    setattr(conversation, _typing_column(match, profile_id), None)
    db.query(DbProfile).filter(DbProfile.id == profile_id).update(
        {DbProfile.last_active_at: datetime.utcnow()}, synchronize_session=False
    )
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
        .options(
            selectinload(DbConversation.messages).selectinload(DbMessage.date_spot)
        )
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

    # Opening a conversation reads it. The chat polls this every few seconds,
    # so messages that arrive while it's open are marked read almost at once.
    unread = db.query(DbMessage).filter(
        DbMessage.conversation_id == conversation_id,
        DbMessage.sender_profile_id != profile_id,
        DbMessage.is_read == False,  # noqa: E712
    )
    if unread.update({DbMessage.is_read: True}, synchronize_session=False):
        db.commit()

    messages = (
        db.query(DbMessage)
        # Chat polls this every few seconds; load invite cards' spots in one
        # extra query instead of one per invite.
        .options(selectinload(DbMessage.date_spot))
        .filter(
            DbMessage.conversation_id == conversation_id
        )
        .order_by(DbMessage.created_at)
        .all()
    )
    # Invite cards: the spot's promotion, and the couple's code.
    from database.db_offers import decorate_messages
    return decorate_messages(db, messages)


def get_live(
    db: Session,
    conversation_id: int,
    profile_id: int,
    now: datetime = None
):
    """An open chat's poll: the messages (reading them, as get_messages
    does), whether the other person is typing, when they were last on
    Blossom (not while their profile is on a break), and whether photos can
    be sent yet. Nothing about someone blocked either way."""
    now = now or datetime.utcnow()
    conversation = get_conversation_for_profile(db, conversation_id, profile_id)
    if not conversation:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this conversation"
        )
    match = conversation.match
    other_id = _other_id(match, profile_id)
    typing_at = getattr(conversation, _typing_column(match, other_id))
    blocked = db_block.is_blocked_either_direction(db, profile_id, other_id)
    other = db.query(DbProfile.last_active_at, DbProfile.paused_at).filter(DbProfile.id == other_id).first()
    # Before loading the messages: it commits, which would expire them.
    touch_active(db, profile_id, now)
    messages = get_messages(db, conversation_id, profile_id)
    if blocked:
        return {"messages": messages, "typing": False, "last_active_at": None, "photos_allowed": False}
    return {
        "messages": messages,
        "typing": typing_at is not None and 0 <= (now - typing_at).total_seconds() <= TYPING_FRESH_SECONDS,
        "last_active_at": other.last_active_at if other and other.paused_at is None else None,
        "photos_allowed": _both_have_written(messages, profile_id, other_id),
    }


def set_typing(db: Session, conversation_id: int, profile_id: int, now: datetime = None):
    """The box is changing: "typing..." on the other side for a few seconds."""
    now = now or datetime.utcnow()
    conversation = get_conversation_for_profile(db, conversation_id, profile_id)
    if not conversation:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this conversation"
        )
    match = conversation.match
    if db_block.is_blocked_either_direction(db, profile_id, _other_id(match, profile_id)):
        return
    setattr(conversation, _typing_column(match, profile_id), now)
    db.commit()
    touch_active(db, profile_id, now)


def check_can_send_photo(db: Session, conversation_id: int, profile_id: int):
    """Before uploading a chat photo: access, blocks, and both have written."""
    conversation = get_conversation_for_profile(db, conversation_id, profile_id)
    if not conversation:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this conversation"
        )
    other_id = _other_id(conversation.match, profile_id)
    if db_block.is_blocked_either_direction(db, profile_id, other_id):
        raise HTTPException(status_code=403, detail="You can't message a blocked profile")
    messages = db.query(DbMessage.sender_profile_id, DbMessage.image_url, DbMessage.date_spot_id).filter(
        DbMessage.conversation_id == conversation_id
    ).all()
    if not _both_have_written(messages, profile_id, other_id):
        raise HTTPException(
            status_code=403,
            detail="You can send photos once you've both written to each other."
        )


def delete_conversation_messages(db: Session, conversation_id: int):
    """A conversation's messages, and its photos on Cloudinary (unmatch,
    account deleted). The caller commits."""
    public_ids = [
        public_id for (public_id,) in db.query(DbMessage.image_public_id).filter(
            DbMessage.conversation_id == conversation_id,
            DbMessage.image_public_id.isnot(None),
        ).all()
    ]
    for public_id in public_ids:
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception:
            # An orphaned Cloudinary asset isn't worth blocking this over.
            pass
    db.query(DbMessage).filter(DbMessage.conversation_id == conversation_id).delete()


def get_conversation_details(
    db: Session,
    conversation_id: int,
    profile_id: int
):
    """Who the viewer is talking to, for the chat header."""
    conversation = get_conversation_for_profile(db, conversation_id, profile_id)
    if not conversation:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this conversation"
        )

    match = conversation.match
    other_id = match.profile2_id if match.profile1_id == profile_id else match.profile1_id
    other = (
        db.query(DbProfile)
        .options(selectinload(DbProfile.photos))
        .filter(DbProfile.id == other_id)
        .first()
    )
    if not other:
        raise HTTPException(status_code=404, detail="This person is no longer on Blossom")

    # Still empty: whose move it is (women write first) - said to both.
    empty = db.query(DbMessage.id).filter(DbMessage.conversation_id == conversation.id).first() is None
    me = db.query(DbProfile).filter(DbProfile.id == profile_id).first() if empty else None
    return {
        "conversation_id": conversation.id,
        # Lets the client tell its own bubbles apart without relying on a
        # locally stored profile id that may be missing.
        "me_profile_id": profile_id,
        "profile": _profile_card(other),
        "first_move": first_move(me, other) if empty else None,
        # "Matched through the event: ..." when an event's organiser made the match.
        "event": _match_event(db, match),
    }


def _match_event(db: Session, match):
    from database.db_events import match_event
    return match_event(db, match)


def get_inbox(
    db: Session,
    profile_id: int
):
    """Every match, newest activity first, with the last message and how many
    messages are unread - including new matches nobody has written to yet, so
    the conversation can be started from Messages."""
    me = db.query(DbProfile).filter(DbProfile.id == profile_id).first()
    blocked = db_block.get_block_relation_ids(db, profile_id)

    matches = [
        m for m in db.query(DbMatch).filter(
            (DbMatch.profile1_id == profile_id) | (DbMatch.profile2_id == profile_id)
        ).all()
        if (m.profile2_id if m.profile1_id == profile_id else m.profile1_id) not in blocked
    ]
    if not matches:
        return []

    other_ids = {
        m.profile2_id if m.profile1_id == profile_id else m.profile1_id for m in matches
    }
    profiles = {
        p.id: p
        for p in db.query(DbProfile)
        .options(selectinload(DbProfile.photos))
        .filter(DbProfile.id.in_(other_ids))
        .all()
    }

    conversations = {
        c.match_id: c
        for c in db.query(DbConversation)
        .filter(DbConversation.match_id.in_([m.id for m in matches]))
        .all()
    }
    conversation_ids = [c.id for c in conversations.values()]

    last_messages = {}
    unread_counts = {}
    if conversation_ids:
        # Message ids only ever grow, so the highest id is the latest message.
        latest_ids = (
            select(func.max(DbMessage.id))
            .where(DbMessage.conversation_id.in_(conversation_ids))
            .group_by(DbMessage.conversation_id)
        )
        last_messages = {
            msg.conversation_id: msg
            for msg in db.query(DbMessage).filter(DbMessage.id.in_(latest_ids)).all()
        }
        unread_counts = dict(
            db.query(DbMessage.conversation_id, func.count(DbMessage.id))
            .filter(
                DbMessage.conversation_id.in_(conversation_ids),
                DbMessage.sender_profile_id != profile_id,
                DbMessage.is_read == False,  # noqa: E712
            )
            .group_by(DbMessage.conversation_id)
            .all()
        )

    items = []
    for match in matches:
        other = profiles.get(
            match.profile2_id if match.profile1_id == profile_id else match.profile1_id
        )
        if other is None:
            continue
        conversation = conversations.get(match.id)
        last = last_messages.get(conversation.id) if conversation else None
        items.append({
            "profile": _profile_card(other),
            "conversation_id": conversation.id if conversation else None,
            "last_message": {
                "content": last.content,
                "created_at": last.created_at,
                "mine": last.sender_profile_id == profile_id,
                "is_invite": last.date_spot_id is not None,
                "is_photo": last.image_url is not None,
            } if last else None,
            "unread_count": unread_counts.get(conversation.id, 0) if conversation else 0,
            "matched_at": match.matched_at,
            # No messages yet and the rules say the other person opens.
            "waiting_for_them": last is None and me is not None and _must_write_first(me, other),
            # ...and the other side of it: she opens this one.
            "your_move": last is None and me is not None and _must_write_first(other, me),
        })

    def activity(item):
        when = item["last_message"]["created_at"] if item["last_message"] else item["matched_at"]
        return when or datetime.min

    items.sort(key=activity, reverse=True)
    return items


def count_unread_conversations(
    db: Session,
    profile_id: int
):
    """How many conversations have messages the viewer hasn't read yet - the
    number on the Messages badge. Blocked people don't count."""
    blocked = db_block.get_block_relation_ids(db, profile_id)
    query = (
        db.query(func.count(func.distinct(DbMessage.conversation_id)))
        .join(DbConversation, DbConversation.id == DbMessage.conversation_id)
        .join(DbMatch, DbMatch.id == DbConversation.match_id)
        .filter(
            (DbMatch.profile1_id == profile_id) | (DbMatch.profile2_id == profile_id),
            DbMessage.sender_profile_id != profile_id,
            DbMessage.is_read == False,  # noqa: E712
        )
    )
    if blocked:
        query = query.filter(DbMessage.sender_profile_id.notin_(blocked))
    return query.scalar() or 0