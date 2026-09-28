"""Profiles an admin creates for a friend, from the answers and photos the
friend gave them.

  * The admin fills in every sign-up answer and adds the photos. The account
    has no usable password yet, and the profile stays out of Browse.
  * The friend gets an email with a private link: they check their profile,
    accept the terms and choose their password - from then on it's a normal
    account that only they can log in to, and it shows in Browse. Or they
    press "This isn't me" and everything is deleted.

So a profile made this way is always a real person who said yes: until the
friend confirms, nobody sees it, and the admin never knows their password.
"""
import html
import os
import re
import secrets
from datetime import datetime, timedelta

import cloudinary.uploader
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from database import db_profile, mailer
from database.models import DbLanguage, DbLearningLanguage, DbProfile, DbProfilePhoto, DbUser
from methods import HashedPassword

SITE_URL = os.getenv("SITE_URL", "https://blossom-date.com").rstrip("/")
LANGUAGES = ("en", "fr", "zh", "ar")
MAX_PHOTOS = 6
PHOTOS_NEEDED = 2  # as at sign-up: a profile is finished with its 2nd photo
LINK_DAYS = 30  # how long the email link works

# The sign-up answers an admin can fill in (same names as ProfileBase).
ANSWER_FIELDS = (
    "bio", "age", "gender", "sexual_orientation", "height_cm", "occupation", "education",
    "smoking", "drinking", "exercise_frequency", "has_pets", "relationship_goal",
    "first_date_preference", "past_relationships_count", "last_breakup_reason",
    "has_children", "wants_children", "personality_type",
)
LONG_FIELDS = {"bio": 2000, "occupation": 255, "education": 255}
# Skipped for language exchange only (like the sign-up questions' "for").
DATING_ONLY = {
    "relationship_goal", "first_date_preference", "past_relationships_count",
    "last_breakup_reason", "has_children", "wants_children",
}


def _lang(value):
    code = (value or "").strip().lower()[:2]
    return code if code in LANGUAGES else "en"


def _clean(value, limit):
    value = " ".join(str(value or "").split())
    return value[:limit] or None


def is_pending(user: DbUser) -> bool:
    """Made by an admin, not confirmed by the friend yet."""
    return user.created_by is not None and user.claimed_at is None


def pending_filter():
    """SQL condition for accounts still waiting for the friend (for Browse)."""
    return (DbUser.created_by.isnot(None)) & (DbUser.claimed_at.is_(None))


def claim_url(user: DbUser) -> str:
    return f"{SITE_URL}/claim/{user.claim_token}"


def _username_for(db: Session, first_name: str) -> str:
    """"sara4821": the friend logs in with their email anyway."""
    base = re.sub(r"[^a-z0-9]", "", first_name.lower())[:20] or "member"
    for _ in range(20):
        candidate = f"{base}{secrets.randbelow(9000) + 1000}"
        if not db.query(DbUser.id).filter(DbUser.username == candidate).first():
            return candidate
    return f"{base}{secrets.token_hex(4)}"


def _status(user: DbUser) -> str:
    if user.claimed_at is not None:
        return "active"
    return "sent" if user.claim_sent_at else "draft"


def row(user: DbUser) -> dict:
    profile = user.profile
    photos = sorted(profile.photos, key=lambda p: p.id) if profile else []
    return {
        "user_id": user.id,
        "profile_id": profile.id if profile else None,
        "first_name": profile.first_name if profile else user.username,
        "email": user.email,
        "language": user.claim_language or "en",
        "status": _status(user),
        "photos": [{"id": p.id, "image_url": p.image_url} for p in photos],
        "created_at": user.created_at,
        "sent_at": user.claim_sent_at,
        "claimed_at": user.claimed_at,
    }


def _load(db: Session, user_id: int) -> DbUser:
    user = (
        db.query(DbUser)
        .options(selectinload(DbUser.profile).selectinload(DbProfile.photos))
        .filter(DbUser.id == user_id, DbUser.created_by.isnot(None))
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="This friend's profile doesn't exist anymore.")
    return user


def _load_pending(db: Session, user_id: int) -> DbUser:
    user = _load(db, user_id)
    if not is_pending(user):
        raise HTTPException(
            status_code=409,
            detail="Your friend already activated this profile: it's theirs now, only they can change it.",
        )
    return user


# ---- admin -----------------------------------------------------------------
def create(db: Session, admin: DbUser, data) -> dict:
    first_name = _clean(data.first_name, 60)
    if not first_name:
        raise HTTPException(status_code=400, detail="Please enter your friend's first name.")
    email = (data.email or "").strip().lower()
    if db.query(DbUser.id).filter(func.lower(DbUser.email) == email).first():
        raise HTTPException(
            status_code=409,
            detail="There's already a Blossom account with this email. Your friend can simply log in.",
        )
    city, country = _clean(data.city, 50), _clean(data.country, 50)
    if not city or not country:
        raise HTTPException(status_code=400, detail="Please say which city and country your friend lives in.")

    # Every question, as at sign-up (where none can be skipped). Browse even
    # breaks on some empty answers (has_pets), so this isn't just tidiness.
    answers = {field: _clean(getattr(data, field, None), LONG_FIELDS.get(field, 100)) for field in ANSWER_FIELDS}
    if data.bio:  # keep the friend's line breaks
        answers["bio"] = str(data.bio).strip()[:2000] or None
    connection_type = db_profile.clean_connection_type(data.connection_type)
    if connection_type == "language" and not answers["relationship_goal"]:
        answers["relationship_goal"] = "Friendship"
    missing = [
        field for field in ANSWER_FIELDS
        if not answers[field] and not (connection_type == "language" and field in DATING_ONLY)
    ]
    if not [n for n in (data.languages or []) if _clean(n, 60)]:
        missing.append("languages")
    if not [n for n in (data.learning_languages or []) if _clean(n, 60)]:
        missing.append("learning_languages")
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"reason": "missing", "fields": missing, "message": "Please answer every question."},
        )

    now = datetime.utcnow()
    user = DbUser(
        username=_username_for(db, first_name),
        email=email,
        # Nobody can log in until the friend chooses their password.
        password=HashedPassword.HashedPassword.hash_password(secrets.token_urlsafe(32)),
        date_of_birth=data.date_of_birth,
        created_at=now,
        created_by=admin.id,
        claim_token=secrets.token_urlsafe(32),
        claim_language=_lang(data.language),
    )
    db.add(user)
    db.flush()

    profile = DbProfile(
        first_name=first_name,
        city=city,
        country=country,
        connection_type=connection_type,
        created_at=datetime.now(),
        user_id=user.id,
        **answers,
    )
    db.add(profile)
    db.flush()

    for names, model in ((data.languages, DbLanguage), (data.learning_languages, DbLearningLanguage)):
        seen = set()
        for name in (names or [])[:20]:
            name = _clean(name, 60)
            if name and name.lower() not in seen:
                seen.add(name.lower())
                db.add(model(language_name=name, profile_id=profile.id))

    db.commit()
    return row(_load(db, user.id))


def list_all(db: Session) -> list:
    users = (
        db.query(DbUser)
        .options(selectinload(DbUser.profile).selectinload(DbProfile.photos))
        .filter(DbUser.created_by.isnot(None))
        .order_by(DbUser.id.desc())
        .all()
    )
    return [row(u) for u in users]


def add_photo(db: Session, user_id: int, image) -> dict:
    user = _load_pending(db, user_id)
    if not user.profile:
        raise HTTPException(status_code=404, detail="This friend's profile doesn't exist anymore.")
    if len(user.profile.photos) >= MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"{MAX_PHOTOS} photos at most.")
    content_type = (image.content_type or "").lower()
    if content_type and content_type != "application/octet-stream" and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please choose a photo (JPG, PNG, HEIC...).")
    try:
        result = cloudinary.uploader.upload(image.file)
    except Exception:
        raise HTTPException(status_code=400, detail="We couldn't upload that photo. Please try another one.")
    photo = DbProfilePhoto(image_url=result["secure_url"], public_id=result["public_id"], profile_id=user.profile.id)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return {"id": photo.id, "image_url": photo.image_url}


def remove_photo(db: Session, user_id: int, photo_id: int) -> dict:
    user = _load_pending(db, user_id)
    photo = next((p for p in (user.profile.photos if user.profile else []) if p.id == photo_id), None)
    if not photo:
        raise HTTPException(status_code=404, detail="This photo isn't there anymore.")
    if photo.public_id:
        try:
            cloudinary.uploader.destroy(photo.public_id)
        except Exception:
            pass  # the row goes anyway
    db.delete(photo)
    db.commit()
    return row(_load(db, user_id))


def send_link(db: Session, user_id: int, background_tasks: BackgroundTasks, language=None) -> dict:
    """Email the friend their link (again, if they lost it). A link past its
    30 days is replaced by a new one."""
    user = _load_pending(db, user_id)
    if not user.profile or len(user.profile.photos) < PHOTOS_NEEDED:
        raise HTTPException(status_code=400, detail=f"Add at least {PHOTOS_NEEDED} photos of your friend first.")
    now = datetime.utcnow()
    if user.claim_sent_at and now - user.claim_sent_at > timedelta(days=LINK_DAYS):
        user.claim_token = secrets.token_urlsafe(32)
    if language:
        user.claim_language = _lang(language)
    user.claim_sent_at = now
    db.commit()
    subject, html_body = claim_email(user)
    background_tasks.add_task(mailer.send_email, user.email, subject, html_body)
    return row(_load(db, user_id))


def delete_pending(db: Session, user_id: int) -> dict:
    """Admins remove a profile the friend hasn't activated (a mistake, a friend
    who changed their mind). Once activated, it's the friend's account."""
    user = _load_pending(db, user_id)
    db_profile.delete_account(db, user)
    return {"deleted": True}


# ---- the friend ------------------------------------------------------------
def _by_token(db: Session, token: str) -> DbUser:
    user = None
    if token and len(token) <= 64:
        user = (
            db.query(DbUser)
            .options(selectinload(DbUser.profile).selectinload(DbProfile.photos))
            .filter(DbUser.claim_token == token)
            .first()
        )
    if not user or not is_pending(user) or not user.claim_sent_at:
        raise HTTPException(
            status_code=404,
            detail={"reason": "not_found", "message": "This link doesn't work anymore. It may have been used already."},
        )
    if datetime.utcnow() - user.claim_sent_at > timedelta(days=LINK_DAYS):
        raise HTTPException(
            status_code=410,
            detail={"reason": "expired", "message": "This link has expired. Ask your friend to send you a new one."},
        )
    return user


def preview(db: Session, token: str) -> dict:
    user = _by_token(db, token)
    profile = user.profile
    photos = sorted(profile.photos, key=lambda p: p.id) if profile else []
    return {
        "first_name": profile.first_name if profile else user.username,
        "email": user.email,
        "username": user.username,
        "language": user.claim_language or "en",
        "age": profile.age if profile else None,
        "city": profile.city if profile else None,
        "country": profile.country if profile else None,
        "bio": profile.bio if profile else None,
        "photos": [p.image_url for p in photos],
    }


def mark_claimed(db: Session, user: DbUser):
    """The friend is in: the profile is theirs and shows in Browse. Counted as
    a finished sign-up from now (no admin notification: an admin made it)."""
    now = datetime.utcnow()
    user.claimed_at = now
    user.claim_token = None
    if user.profile and user.profile.completed_at is None and len(user.profile.photos) >= PHOTOS_NEEDED:
        user.profile.completed_at = datetime.now()


def claim(db: Session, token: str, password: str) -> DbUser:
    user = _by_token(db, token)
    user.password = HashedPassword.HashedPassword.hash_password(password)
    mark_claimed(db, user)
    db.commit()
    db.refresh(user)
    return user


def decline(db: Session, token: str) -> dict:
    user = _by_token(db, token)
    db_profile.delete_account(db, user)
    return {"deleted": True}


# ---- the email -------------------------------------------------------------
EMAILS = {
    "en": (
        "🌸 {name}, your Blossom profile is ready",
        "Your Blossom profile is ready",
        [
            "Hi {name},",
            "The Blossom team created your dating profile with the answers and photos you gave us.",
            "<b>Nobody can see it yet.</b> Check it, choose your password, and it goes live.",
            "Didn't ask for this? Open the link and choose <b>This isn't me</b>: we'll delete everything.",
            "The link works for {days} days.",
        ],
        "Check and activate my profile",
    ),
    "fr": (
        "🌸 {name}, ton profil Blossom est prêt",
        "Ton profil Blossom est prêt",
        [
            "Bonjour {name},",
            "L'équipe Blossom a créé ton profil de rencontre avec les réponses et les photos que tu nous as données.",
            "<b>Personne ne peut encore le voir.</b> Vérifie-le, choisis ton mot de passe, et il sera en ligne.",
            "Tu n'as rien demandé ? Ouvre le lien et choisis <b>Ce n'est pas moi</b> : on supprime tout.",
            "Le lien fonctionne pendant {days} jours.",
        ],
        "Vérifier et activer mon profil",
    ),
    "zh": (
        "🌸 {name}，你的 Blossom 资料已准备好",
        "你的 Blossom 资料已准备好",
        [
            "{name}，你好：",
            "Blossom 团队已根据你提供的回答和照片为你创建了交友资料。",
            "<b>目前还没有人能看到它。</b>检查资料、设置密码后即可上线。",
            "不是你申请的？打开链接并选择<b>这不是我</b>，我们会删除所有内容。",
            "链接在 {days} 天内有效。",
        ],
        "检查并激活我的资料",
    ),
    "ar": (
        "🌸 {name}، ملفك على Blossom جاهز",
        "ملفك على Blossom جاهز",
        [
            "مرحبًا {name}،",
            "أنشأ فريق Blossom ملفك للتعارف بالإجابات والصور التي أعطيتنا إياها.",
            "<b>لا أحد يستطيع رؤيته بعد.</b> راجعه واختر كلمة المرور، وسيصبح ظاهرًا.",
            "لم تطلب ذلك؟ افتح الرابط واختر <b>هذا ليس أنا</b> وسنحذف كل شيء.",
            "الرابط صالح لمدة {days} يومًا.",
        ],
        "مراجعة ملفي وتفعيله",
    ),
}


def claim_email(user: DbUser):
    subject, title, paragraphs, button = EMAILS[_lang(user.claim_language)]
    name = html.escape(user.profile.first_name if user.profile else user.username)
    fill = {"name": name, "days": LINK_DAYS}
    body = mailer.card(
        title,
        [p.format(**fill) for p in paragraphs],
        (button, claim_url(user)),
    )
    plain_name = user.profile.first_name if user.profile else user.username
    return subject.format(name=plain_name), body
