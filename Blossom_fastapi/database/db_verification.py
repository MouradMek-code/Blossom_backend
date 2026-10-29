"""The ✓ verified badge.

The member takes a selfie copying a pose the server picked (so an old or
stolen photo can't be used), an admin compares it with the profile photos and
approves or rejects it. The selfie is deleted from Cloudinary as soon as the
admin has decided - only the result is kept.
"""
import secrets
from datetime import datetime, timedelta

import cloudinary.uploader
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session, selectinload

from database import db_push, mailer
from database.models import DbProfile, DbPushToken, DbUser, DbVerification

# The poses the apps can show (emoji and text are on their side).
POSES = ("peace", "thumb", "wave", "point", "ok", "chin")
# Why a selfie was turned down, shown to the member with the new pose.
REASONS = ("pose", "face", "blurry")

# An admin's "Ask to verify": the time the member is given to send the selfie,
# and the extra time after a rejected one. Nothing is deleted automatically:
# past the deadline, Admin shows it and the admin decides.
REQUEST_HOURS = 48
RETRY_HOURS = 24


def _iso(value):
    return value.isoformat() + "Z" if value else None


def _own_profile(db: Session, user) -> DbProfile:
    profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Please finish your profile first.")
    return profile


def _latest(db: Session, profile_id: int):
    return (
        db.query(DbVerification)
        .filter(DbVerification.profile_id == profile_id)
        .order_by(DbVerification.id.desc())
        .first()
    )


def _forget_selfie(verification: DbVerification):
    if verification.public_id:
        try:
            cloudinary.uploader.destroy(verification.public_id)
        except Exception:
            pass  # the link isn't shown anywhere any more either way
    verification.image_url = None
    verification.public_id = None


def status(db: Session, user) -> dict:
    """{"status": "none" | "pending" | "approved" | "rejected", "pose", "reason"}.
    The pose to copy is picked here, once, and kept until a selfie is sent."""
    profile = _own_profile(db, user)
    if profile.verified_at:
        return {"status": "approved", "pose": None, "reason": None, "deadline": None}
    deadline = _iso(profile.verify_deadline)  # asked by an admin: verify by then
    latest = _latest(db, profile.id)
    if latest and latest.status == "pending":
        return {"status": "pending", "pose": latest.pose, "reason": None, "deadline": deadline}
    if profile.verification_pose not in POSES:
        profile.verification_pose = secrets.choice(POSES)
        db.commit()
    rejected = latest is not None and latest.status == "rejected"
    return {
        "status": "rejected" if rejected else "none",
        "pose": profile.verification_pose,
        "reason": latest.reason if rejected else None,
        "deadline": deadline,
    }


def submit(db: Session, user, image, background_tasks: BackgroundTasks) -> dict:
    profile = _own_profile(db, user)
    if profile.verified_at:
        raise HTTPException(status_code=409, detail="You're already verified.")
    latest = _latest(db, profile.id)
    if latest and latest.status == "pending":
        raise HTTPException(status_code=409, detail="Your selfie is already being checked.")
    if not profile.photos:
        raise HTTPException(status_code=400, detail="Add your photos first: we compare the selfie with them.")
    content_type = (image.content_type or "").lower()
    if content_type and content_type != "application/octet-stream" and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please send a photo.")

    pose = profile.verification_pose if profile.verification_pose in POSES else secrets.choice(POSES)
    result = cloudinary.uploader.upload(image.file, folder="blossom_verifications")
    verification = DbVerification(
        profile_id=profile.id,
        pose=pose,
        image_url=result["secure_url"],
        public_id=result["public_id"],
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(verification)
    # A new attempt after this one gets a new pose.
    profile.verification_pose = None
    db.commit()
    db.refresh(verification)
    db_push.notify_verification_request(db, background_tasks, profile)
    return {"status": "pending", "pose": pose, "reason": None, "deadline": _iso(profile.verify_deadline)}


def list_pending(db: Session) -> list:
    """Admins: the selfies waiting, oldest first, with what to compare them to."""
    rows = (
        db.query(DbVerification)
        .filter(DbVerification.status == "pending")
        .order_by(DbVerification.id)
        .all()
    )
    profiles = {
        p.id: p
        for p in db.query(DbProfile).options(selectinload(DbProfile.photos))
        .filter(DbProfile.id.in_([r.profile_id for r in rows] or [0]))
    }
    result = []
    for row in rows:
        profile = profiles.get(row.profile_id)
        if not profile:
            continue
        result.append({
            "id": row.id,
            "pose": row.pose,
            "selfie": row.image_url,
            "sent_at": row.created_at.isoformat() + "Z" if row.created_at else None,
            "profile": {
                "id": profile.id,
                "first_name": profile.first_name,
                "age": profile.age,
                "city": profile.city,
                "country": profile.country,
                "photos": [p.image_url for p in profile.photos],
            },
        })
    return result


def decide(db: Session, verification_id: int, approve: bool, reason, background_tasks: BackgroundTasks) -> dict:
    verification = db.get(DbVerification, verification_id)
    if not verification:
        raise HTTPException(status_code=404, detail="Not found.")
    if verification.status != "pending":
        raise HTTPException(status_code=409, detail="Already decided.")
    if not approve and reason not in REASONS:
        raise HTTPException(status_code=400, detail="Please choose a reason.")
    now = datetime.utcnow()
    verification.status = "approved" if approve else "rejected"
    verification.reason = None if approve else reason
    verification.reviewed_at = now
    profile = db.get(DbProfile, verification.profile_id)
    if profile:
        if approve:
            profile.verified_at = now
            profile.verify_deadline = None
        else:
            profile.verification_pose = secrets.choice(POSES)  # a fresh pose for the retry
            if profile.verify_deadline:
                # Asked to verify: a day to try again, whatever the deadline was.
                profile.verify_deadline = max(profile.verify_deadline, now + timedelta(hours=RETRY_HOURS))
    _forget_selfie(verification)
    db.commit()
    if profile:
        db_push.notify_verification_result(db, background_tasks, profile, approve)
    return {"id": verification.id, "status": verification.status}


REQUEST_EMAIL = {
    "en": ("Please verify your Blossom profile",
           "Please verify your profile",
           ["Our team has noticed something unusual about your Blossom profile.",
            "To keep it, please verify that it's really you within <b>48 hours</b>: copy a pose and take a quick "
            "selfie. If it isn't verified in time, the profile will be deleted for suspicious activity."],
           "Verify my profile"),
    "fr": ("Merci de vérifier votre profil Blossom",
           "Merci de vérifier votre profil",
           ["Notre équipe a remarqué quelque chose d'inhabituel sur votre profil Blossom.",
            "Pour le garder, merci de confirmer que c'est bien vous sous <b>48 heures</b> : reproduisez une pose "
            "et prenez un selfie rapide. Sans vérification à temps, le profil sera supprimé pour activité suspecte."],
           "Vérifier mon profil"),
    "zh": ("请认证你的 Blossom 资料",
           "请认证你的资料",
           ["我们的团队注意到你的 Blossom 资料有异常。",
            "如需保留资料，请在 <b>48 小时</b>内证明真的是你：模仿一个姿势并拍一张自拍。逾期未认证，资料将因可疑活动被删除。"],
           "认证我的资料"),
    "ar": ("يرجى توثيق ملفك على Blossom",
           "يرجى توثيق ملفك الشخصي",
           ["لاحظ فريقنا شيئًا غير معتاد في ملفك الشخصي على Blossom.",
            "للاحتفاظ به، يرجى إثبات أنه أنت حقًا خلال <b>48 ساعة</b>: قلّد وضعية والتقط صورة سيلفي سريعة. "
            "إذا لم يتم التوثيق في الوقت المحدد، سيُحذف الملف بسبب نشاط مشبوه."],
           "توثيق ملفي"),
}


def request(db: Session, profile_id: int, background_tasks: BackgroundTasks) -> dict:
    """Admin: "Ask to verify". The member is told by notification and email
    to verify within 48 hours or the profile will be deleted - by the admin,
    by hand (Admin shows when the deadline has passed)."""
    profile = db.get(DbProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    if profile.verified_at:
        raise HTTPException(status_code=409, detail="Already verified.")
    profile.verify_deadline = datetime.utcnow() + timedelta(hours=REQUEST_HOURS)
    if profile.verification_pose not in POSES:
        profile.verification_pose = secrets.choice(POSES)
    db.commit()

    db_push.notify_verification_asked(db, background_tasks, profile)
    user = db.get(DbUser, profile.user_id)
    language = db.query(DbPushToken.language).filter(DbPushToken.user_id == profile.user_id).scalar()
    subject, title, paragraphs, button = REQUEST_EMAIL[db_push.normalize_language(language)]
    if user and user.email:
        background_tasks.add_task(
            mailer.send_email, user.email, subject,
            mailer.card(title, paragraphs, (button, "https://blossom-date.com/verify")),
        )
    return {"profile_id": profile.id, "deadline": _iso(profile.verify_deadline)}


def clear_profile(db: Session, profile):
    """Account deletion: the selfies go too."""
    for verification in db.query(DbVerification).filter(DbVerification.profile_id == profile.id):
        _forget_selfie(verification)
        db.delete(verification)
