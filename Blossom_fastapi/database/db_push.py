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
from database.models import DbAdminAlertToken, DbConversation, DbProfile, DbPushToken, DbUser

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
    # A date spot invite - with the spot's promotion when it has one.
    "spot_invite": {
        "en": "💌 {name} invites you to {spot}",
        "fr": "💌 {name} vous invite à {spot}",
        "zh": "💌 {name} 邀请你去 {spot}",
        "ar": "💌 {name} يدعوك إلى {spot}",
    },
    "spot_invite_promo": {
        "en": "💌 {name} invites you to {spot} - 🎁 {title} for both of you if you say yes",
        "fr": "💌 {name} vous invite à {spot} - 🎁 {title} pour vous deux si vous dites oui",
        "zh": "💌 {name} 邀请你去 {spot} - 🎁 如果你同意，你们两人都能获得：{title}",
        "ar": "💌 {name} يدعوك إلى {spot} - 🎁 {title} لكما معًا إذا وافقت",
    },
    # A couple's code is about to expire (sent once, to both).
    "promo_reminder": {
        "en": "⏰ Your {title} at {spot} ends in {hours} h - show your code before then.",
        "fr": "⏰ Votre « {title} » chez {spot} expire dans {hours} h - montrez votre code avant.",
        "zh": "⏰ 你在 {spot} 的 {title} 将在 {hours} 小时后过期，请在此之前出示优惠码。",
        "ar": "⏰ عرضك {title} في {spot} ينتهي خلال {hours} ساعة - أظهر رمزك قبل ذلك.",
    },
    # A date spot invite accepted - with the promotion when it got them one.
    "invite_yes": {
        "en": "✅ {name} is in for {spot}!",
        "fr": "✅ {name} est partant·e pour {spot} !",
        "zh": "✅ {name} 答应一起去 {spot}！",
        "ar": "✅ {name} موافق على الذهاب إلى {spot}!",
    },
    "invite_yes_promo": {
        "en": "🎁 {name} is in for {spot} - you both got: {title}! Your code is in the chat.",
        "fr": "🎁 {name} est partant·e pour {spot} : vous avez gagné « {title} » ! Votre code est dans la discussion.",
        "zh": "🎁 {name} 答应一起去 {spot}，你们获得了：{title}！优惠码在聊天中。",
        "ar": "🎁 {name} موافق على {spot}، وحصلتما على: {title}! الرمز في المحادثة.",
    },
    # Admins only.
    "business_message": {
        "en": "📩 New message from {name}{business}",
        "fr": "📩 Nouveau message de {name}{business}",
        "zh": "📩 来自 {name}{business} 的新消息",
        "ar": "📩 رسالة جديدة من {name}{business}",
    },
    "spot_suggestion": {
        "en": "📍 New place suggested by {author}: {name} ({city})",
        "fr": "📍 Nouveau lieu suggéré par {author} : {name} ({city})",
        "zh": "📍 {author} 推荐了新地点：{name}（{city}）",
        "ar": "📍 مكان جديد اقترحه {author}: {name} ({city})",
    },
    "spot_approved": {
        "en": "🎉 Your place {name} is now on Blossom - thank you!",
        "fr": "🎉 Votre lieu {name} est maintenant sur Blossom - merci !",
        "zh": "🎉 你推荐的地点 {name} 已上线 Blossom，谢谢！",
        "ar": "🎉 مكانك {name} أصبح الآن على Blossom - شكرًا لك!",
    },
    "partner_request": {
        "en": "🏪 New partner request: {name} - {title}",
        "fr": "🏪 Nouvelle demande de partenariat : {name} - {title}",
        "zh": "🏪 新的合作申请：{name} - {title}",
        "ar": "🏪 طلب شراكة جديد: {name} - {title}",
    },
    "new_profile": {
        "en": "🌱 New profile: {name}",
        "fr": "🌱 Nouveau profil : {name}",
        "zh": "🌱 新用户资料：{name}",
        "ar": "🌱 ملف شخصي جديد: {name}",
    },
}


def is_expo_token(token: str) -> bool:
    return bool(token) and token.startswith(("ExponentPushToken[", "ExpoPushToken[")) and token.endswith("]")


def normalize_language(language) -> str:
    code = (language or "").strip().lower()[:2]
    return code if code in LANGUAGES else "en"


def register_token(db: Session, user_id: int, token: str, language=None, is_admin: bool = False):
    language = normalize_language(language)
    row = db.query(DbPushToken).filter(DbPushToken.token == token).first()
    if row:
        row.user_id = user_id  # same phone, possibly another account now
        row.language = language
    else:
        db.add(DbPushToken(user_id=user_id, token=token, language=language))
    alert = db.get(DbAdminAlertToken, token)
    if is_admin:
        # This phone now gets the "new profile" notifications for good.
        if alert:
            alert.user_id = user_id
            alert.language = language
        else:
            db.add(DbAdminAlertToken(token=token, user_id=user_id, language=language))
    elif alert:
        alert.language = language
    db.commit()


def unregister_token(db: Session, user_id: int, token: str):
    db.query(DbPushToken).filter(
        DbPushToken.user_id == user_id,
        DbPushToken.token == token,
    ).delete(synchronize_session=False)
    db.commit()


def delete_user_tokens(db: Session, user_id: int):
    db.query(DbPushToken).filter(DbPushToken.user_id == user_id).delete(synchronize_session=False)
    db.query(DbAdminAlertToken).filter(DbAdminAlertToken.user_id == user_id).delete(synchronize_session=False)


def _messages_for_profile(db: Session, profile_id: int, kind: str, name: str, data: dict, **extra):
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
            "body": TEXTS[kind][normalize_language(row.language)].format(name=name or "", **extra),
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
    cleared) are removed so we stop sending to them.
    Returns {"sent": n, "errors": [...]} for callers that want to know."""
    result = {"sent": 0, "errors": []}
    if not messages:
        return result
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
            result["errors"].append(f"Expo push service unreachable: {exc}")
            continue
        if isinstance(tickets, dict):
            tickets = [tickets]
        for message, ticket in zip(chunk, tickets):
            if ticket.get("status") != "error":
                result["sent"] += 1
                continue
            error = (ticket.get("details") or {}).get("error")
            result["errors"].append(ticket.get("message") or error or "unknown error")
            if error == "DeviceNotRegistered":
                dead_tokens.append(message["to"])
            else:
                log.warning("Expo push error for a token: %s", ticket.get("message"))

    if dead_tokens:
        db = SessionLocal()
        try:
            db.query(DbPushToken).filter(DbPushToken.token.in_(dead_tokens)).delete(synchronize_session=False)
            db.query(DbAdminAlertToken).filter(DbAdminAlertToken.token.in_(dead_tokens)).delete(synchronize_session=False)
            db.commit()
        except Exception as exc:
            log.warning("Could not remove dead push tokens: %s", exc)
        finally:
            db.close()
    return result


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



def notify_invite_accepted(db: Session, background_tasks: BackgroundTasks, conversation_id: int,
                           inviter_profile_id: int, accepter_name: str, spot_name: str, promo_title=None):
    """"✅ Leo is in for Café X!" to the one who sent the invite - with the
    promotion they both got, if any. The one who tapped "I'm in" sees it on
    screen already."""
    kind = "invite_yes_promo" if promo_title else "invite_yes"
    _queue(background_tasks, _messages_for_profile(
        db, inviter_profile_id, kind, accepter_name,
        {"type": "message", "conversationId": conversation_id},
        spot=spot_name, title=promo_title or "",
    ))


def _admin_targets(db: Session, exclude_user_id=None):
    """{token: language} for every admin's phone: the ones logged in to an
    admin account now, plus any phone an admin has used before
    (admin_alert_token)."""
    query = db.query(DbUser.id).filter(DbUser.is_admin == True)  # noqa: E712
    if exclude_user_id is not None:
        query = query.filter(DbUser.id != exclude_user_id)
    admin_ids = [uid for (uid,) in query]
    targets = {}
    if admin_ids:
        for row in db.query(DbPushToken).filter(DbPushToken.user_id.in_(admin_ids)).all():
            targets[row.token] = row.language
        for row in db.query(DbAdminAlertToken).filter(DbAdminAlertToken.user_id.in_(admin_ids)).all():
            targets.setdefault(row.token, row.language)
    return targets


def notify_partner_request(db: Session, background_tasks: BackgroundTasks, request):
    """"🏪 New partner request: Café Lune - -20% on the bill" to the admins."""
    targets = _admin_targets(db)
    _queue(background_tasks, [
        {
            "to": token,
            "title": "Blossom",
            "body": TEXTS["partner_request"][normalize_language(language)].format(
                name=request.venue_name, title=request.offer_title),
            "data": {"type": "partner_request", "requestId": request.id},
            "sound": "default",
            "channelId": "default",
            "priority": "high",
        }
        for token, language in targets.items()
    ])


def notify_spot_suggestion(db: Session, background_tasks: BackgroundTasks, spot, author_name: str):
    """"📍 New place suggested by Sara: Café Rose (Paris)" to the admins."""
    targets = _admin_targets(db)
    _queue(background_tasks, [
        {
            "to": token,
            "title": "Blossom",
            "body": TEXTS["spot_suggestion"][normalize_language(language)].format(
                author=author_name or "?", name=spot.name, city=spot.city),
            "data": {"type": "spot_suggestion", "spotId": spot.id},
            "sound": "default",
            "channelId": "default",
            "priority": "high",
        }
        for token, language in targets.items()
    ])


def notify_spot_approved(db: Session, background_tasks: BackgroundTasks, spot):
    """"🎉 Your place Café Rose is now on Blossom" to the member who suggested it."""
    if not spot.profile_id:
        return
    profile = db.get(DbProfile, spot.profile_id)
    if not profile:
        return
    rows = db.query(DbPushToken.token, DbPushToken.language).filter(DbPushToken.user_id == profile.user_id).all()
    _queue(background_tasks, [
        {
            "to": token,
            "title": "Blossom",
            "body": TEXTS["spot_approved"][normalize_language(language)].format(name=spot.name),
            "data": {"type": "spot", "spotId": spot.id},
            "sound": "default",
            "channelId": "default",
        }
        for token, language in rows
    ])


def notify_business_message(db: Session, background_tasks: BackgroundTasks, message):
    """"📩 New message from Nadia - Café Lune" to the admins."""
    business = f" - {message.business}" if message.business else ""
    _queue(background_tasks, [
        {
            "to": token,
            "title": "Blossom",
            "body": TEXTS["business_message"][normalize_language(language)].format(name=message.name, business=business),
            "data": {"type": "business_message", "messageId": message.id},
            "sound": "default",
            "channelId": "default",
            "priority": "high",
        }
        for token, language in _admin_targets(db).items()
    ])


def notify_new_profile(db: Session, background_tasks: BackgroundTasks, profile: DbProfile):
    """"🌱 New profile: sara · Paris, France" to every admin's phone once the
    profile is finished (photos in), so they don't have to keep checking the
    admin list. Nobody else is told.

    An admin's phones are the ones logged in to the admin account now, plus
    any phone an admin has used before (admin_alert_token) - so logging out
    or trying the sign-up on the same phone doesn't stop the notifications.
    An admin's own new profile only goes to the other admins."""
    targets = _admin_targets(db, exclude_user_id=profile.user_id)
    if not targets:
        log.warning("Profile %s finished, but no admin phone is registered for notifications", profile.id)
        return
    log.info("Profile %s finished: notifying %d admin phone(s)", profile.id, len(targets))

    place = ", ".join(part for part in (profile.city, profile.country) if part)
    name = f"{profile.first_name} · {place}" if place else profile.first_name
    _queue(background_tasks, [
        {
            "to": token,
            "title": "Blossom",
            "body": TEXTS["new_profile"][normalize_language(language)].format(name=name),
            "data": {"type": "new_profile", "profileId": profile.id},
            "sound": "default",
            "channelId": "default",
            "priority": "high",
        }
        for token, language in targets.items()
    ])


def notify_spot_invite(db: Session, background_tasks: BackgroundTasks, conversation_id: int,
                       sender: DbProfile, spot_name: str, promo_title=None):
    """"💌 Sara invites you to Café Lune - 🎁 -20% for both of you if you say
    yes": the gift is what makes people answer, so it's in the notification."""
    conversation = db.query(DbConversation).filter(DbConversation.id == conversation_id).first()
    if not conversation:
        return
    match = conversation.match
    recipient_id = match.profile2_id if match.profile1_id == sender.id else match.profile1_id
    _queue(background_tasks, _messages_for_profile(
        db, recipient_id, "spot_invite_promo" if promo_title else "spot_invite", sender.first_name,
        {"type": "message", "conversationId": conversation_id},
        spot=spot_name, title=promo_title or "",
    ))


def send_voucher_reminders(db: Session, now=None):
    """Runs every few minutes (see main.py): "⏰ Your -20% at Café Lune ends in
    5 h" to both, once per code. Returns how many codes were reminded."""
    from database.db_offers import claim_due_reminders

    messages = []
    reminded = claim_due_reminders(db, now)
    for voucher, hours_left in reminded:
        spot = voucher.offer.spot
        for profile_id in (voucher.profile1_id, voucher.profile2_id):
            messages += _messages_for_profile(
                db, profile_id, "promo_reminder", "",
                {"type": "voucher", "voucherId": voucher.id},
                title=voucher.offer.title, spot=spot.name if spot else "", hours=hours_left,
            )
    send_push_messages(messages)
    return len(reminded)
