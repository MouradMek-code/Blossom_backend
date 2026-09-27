""""Partner with Blossom": venues offering a promotion to Blossom couples.

  * A café fills in the public form -> a pending request; admins get a
    notification. An admin approves (the spot, the venue and the promotion are
    created, the café gets an email with its manager link and staff code) or
    refuses (a polite email).
  * No account for venues: the owner's private manager link lets them pause,
    resume, add places, extend the end date - at once - and ask for a new
    offer, which comes back to the admins as a request (anything couples will
    newly see is approved first). Waiters only have the staff code.
"""
import html
import os
import re
import secrets
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import db_offers, db_push, mailer
from database.models import DbDateSpot, DbPartnerRequest, DbSpotOffer, DbVenue

SITE_URL = os.getenv("SITE_URL", "https://blossom-date.com").rstrip("/")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LANGUAGES = ("en", "fr", "zh", "ar")
DEFAULT_OPEN_DAYS = 30
DEFAULT_VALID_HOURS = 7 * 24
MAX_PENDING_PER_SENDER = 3  # per email (form) or per venue (manager page), per day


def _lang(value):
    code = (value or "").strip().lower()[:2]
    return code if code in LANGUAGES else "en"


def _text(value, limit):
    value = " ".join(str(value or "").split())
    return value[:limit] or None


def _long_text(value, limit):
    value = str(value or "").strip()
    return value[:limit] or None


def manage_url(venue: DbVenue) -> str:
    return f"{SITE_URL}/venue/manage/{venue.manage_token}"


def _check_offer_fields(title, max_couples, ends_at, valid_hours, now):
    if not title or len(title) < 3:
        raise HTTPException(status_code=400, detail="Describe the offer, e.g. \"-20% on the bill\".")
    if max_couples is not None and not 1 <= max_couples <= 100000:
        raise HTTPException(status_code=400, detail="Number of couples: leave empty for no limit, or 1 or more.")
    if valid_hours is not None and not 1 <= valid_hours <= 24 * 365:
        raise HTTPException(status_code=400, detail="Couples need between 1 hour and a year to use it.")
    if ends_at is not None and ends_at <= now:
        raise HTTPException(status_code=400, detail="The end date must be in the future.")


# ---- requests --------------------------------------------------------------------

def create_request(db: Session, background_tasks: BackgroundTasks, data: dict, venue: DbVenue = None,
                   now: datetime = None):
    now = now or datetime.utcnow()
    title = _text(data.get("offer_title"), 120)
    _check_offer_fields(title, data.get("max_couples"), data.get("ends_at"), data.get("valid_hours"), now)

    if venue is None:
        name = _text(data.get("venue_name"), 150)
        email = _text(data.get("contact_email"), 200)
        city = _text(data.get("city"), 120)
        country = _text(data.get("country"), 120)
        if not name or len(name) < 2:
            raise HTTPException(status_code=400, detail="Enter the name of your place.")
        if not city or not country:
            raise HTTPException(status_code=400, detail="Enter the city and the country.")
        if not email or not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email address, so we can answer you.")
        map_url = _text(data.get("map_url"), 500)
        if map_url and not map_url.lower().startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="The Google Maps link should start with https://")
        recent = db.query(func.count(DbPartnerRequest.id)).filter(
            func.lower(DbPartnerRequest.contact_email) == email.lower(),
            DbPartnerRequest.status == "pending",
            DbPartnerRequest.created_at > now - timedelta(days=1),
        ).scalar()
    else:
        name, email, city, country, map_url = venue.name, venue.contact_email, None, None, None
        recent = db.query(func.count(DbPartnerRequest.id)).filter(
            DbPartnerRequest.venue_id == venue.id, DbPartnerRequest.status == "pending",
        ).scalar()
    if recent >= MAX_PENDING_PER_SENDER:
        raise HTTPException(status_code=429, detail="We already have your requests - we'll answer them first.")

    request = DbPartnerRequest(
        created_at=now, status="pending", venue_id=venue.id if venue else None,
        venue_name=name, map_url=map_url, city=city, country=country,
        about=_long_text(data.get("about"), 1000),
        offer_title=title, offer_details=_long_text(data.get("offer_details"), 500),
        max_couples=data.get("max_couples"), ends_at=data.get("ends_at"), valid_hours=data.get("valid_hours"),
        contact_name=_text(data.get("contact_name"), 120) if venue is None else venue.contact_name,
        contact_email=email,
        contact_phone=_text(data.get("contact_phone"), 40) if venue is None else venue.contact_phone,
        message=_long_text(data.get("message"), 1000),
        language=_lang(data.get("language") or (venue.language if venue else None)),
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    db_push.notify_partner_request(db, background_tasks, request)
    if venue is None and email:
        background_tasks.add_task(mailer.send_email, email, *_received_email(request))
    return {"id": request.id, "status": request.status}


def _suggested_spot(db: Session, request: DbPartnerRequest):
    """An existing spot for this place, so approving links it instead of
    creating a double."""
    if request.venue_id:
        return None
    if request.map_url:
        spot = db.query(DbDateSpot).filter(DbDateSpot.map_url == request.map_url).first()
        if spot:
            return spot
    if request.venue_name and request.city:
        return db.query(DbDateSpot).filter(
            func.lower(DbDateSpot.name) == request.venue_name.lower(),
            func.lower(DbDateSpot.city) == request.city.lower(),
        ).first()
    return None


def request_view(db: Session, request: DbPartnerRequest):
    suggested = _suggested_spot(db, request) if request.status == "pending" else None
    venue = request.venue
    return {
        "id": request.id,
        "created_at": request.created_at,
        "status": request.status,
        "kind": "new_offer" if request.venue_id else "new_venue",
        "venue_name": request.venue_name,
        "map_url": request.map_url,
        "city": request.city or (venue.spot.city if venue and venue.spot else None),
        "country": request.country or (venue.spot.country if venue and venue.spot else None),
        "about": request.about,
        "offer_title": request.offer_title,
        "offer_details": request.offer_details,
        "max_couples": request.max_couples,
        "ends_at": request.ends_at,
        "valid_hours": request.valid_hours,
        "contact_name": request.contact_name,
        "contact_email": request.contact_email,
        "contact_phone": request.contact_phone,
        "message": request.message,
        "language": request.language,
        "reviewed_at": request.reviewed_at,
        "refuse_reason": request.refuse_reason,
        "offer_id": request.offer_id,
        "suggested_spot": {"id": suggested.id, "name": suggested.name, "city": suggested.city} if suggested else None,
        "venue": venue_view(venue) if venue else None,
    }


def list_requests(db: Session):
    pending = (
        db.query(DbPartnerRequest).filter(DbPartnerRequest.status == "pending")
        .order_by(DbPartnerRequest.created_at).all()
    )
    done = (
        db.query(DbPartnerRequest).filter(DbPartnerRequest.status != "pending")
        .order_by(DbPartnerRequest.reviewed_at.desc()).limit(30).all()
    )
    return [request_view(db, r) for r in pending + done]


def _pending(db: Session, request_id: int) -> DbPartnerRequest:
    request = db.get(DbPartnerRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found.")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="This request was already answered.")
    return request


def _new_venue(db: Session, spot: DbDateSpot, request: DbPartnerRequest, now: datetime) -> DbVenue:
    venue = DbVenue(
        spot_id=spot.id, name=spot.name, contact_name=request.contact_name,
        contact_email=request.contact_email, contact_phone=request.contact_phone,
        language=request.language, manage_token=secrets.token_urlsafe(24),
        staff_code="".join(secrets.choice("0123456789") for _ in range(4)), created_at=now,
    )
    db.add(venue)
    db.flush()
    return venue


def approve(db: Session, background_tasks: BackgroundTasks, request_id: int, changes: dict, now: datetime = None):
    """Publish it. The admin may correct anything first (changes); spot_id
    links an existing spot instead of creating one."""
    now = now or datetime.utcnow()
    request = _pending(db, request_id)
    for key in ("venue_name", "city", "country", "about", "offer_title", "offer_details",
                "max_couples", "ends_at", "valid_hours"):
        if key in changes:
            setattr(request, key, changes[key])
    title = _text(request.offer_title, 120)
    ends_at = request.ends_at or now + timedelta(days=DEFAULT_OPEN_DAYS)
    valid_hours = request.valid_hours or DEFAULT_VALID_HOURS
    _check_offer_fields(title, request.max_couples, ends_at, valid_hours, now)

    if request.venue_id:
        venue = request.venue
        spot = venue.spot
    else:
        spot = None
        if changes.get("spot_id"):
            spot = db.get(DbDateSpot, changes["spot_id"])
            if not spot:
                raise HTTPException(status_code=404, detail="Date spot not found.")
        else:
            spot = _suggested_spot(db, request)
        if spot is None:
            name = _text(request.venue_name, 150)
            if not name or not request.city or not request.country:
                raise HTTPException(status_code=400, detail="Name, city and country are needed to create the spot.")
            spot = DbDateSpot(
                name=name, city=_text(request.city, 120), country=_text(request.country, 120),
                description=request.about or f"{name} - a Blossom partner 🌸",
                map_url=request.map_url, created_at=now,
            )
            db.add(spot)
            db.flush()
        venue = db.query(DbVenue).filter(DbVenue.spot_id == spot.id).first() or _new_venue(db, spot, request, now)

    offer = db_offers.create_offer(
        db, spot.id, title, request.offer_details, request.max_couples, ends_at, valid_hours,
        staff_code=venue.staff_code, now=now,
    )
    request.status = "approved"
    request.reviewed_at = now
    request.offer_id = offer["id"]
    request.venue_id = venue.id
    db.commit()
    if venue.contact_email:
        background_tasks.add_task(mailer.send_email, venue.contact_email, *_approved_email(venue, title, offer["id"]))
    return request_view(db, request)


def refuse(db: Session, background_tasks: BackgroundTasks, request_id: int, reason=None, now: datetime = None):
    now = now or datetime.utcnow()
    request = _pending(db, request_id)
    request.status = "refused"
    request.reviewed_at = now
    request.refuse_reason = _long_text(reason, 500)
    db.commit()
    if request.contact_email:
        background_tasks.add_task(mailer.send_email, request.contact_email, *_refused_email(request))
    return request_view(db, request)


# ---- venues -----------------------------------------------------------------------

def venue_view(venue: DbVenue):
    spot = venue.spot
    return {
        "id": venue.id,
        "name": venue.name,
        "staff_code": venue.staff_code,
        "manage_url": manage_url(venue),
        "contact_name": venue.contact_name,
        "contact_email": venue.contact_email,
        "contact_phone": venue.contact_phone,
        "spot": {"id": spot.id, "name": spot.name, "city": spot.city} if spot else None,
    }


def list_venues(db: Session):
    return [venue_view(v) for v in db.query(DbVenue).order_by(DbVenue.created_at.desc()).all()]


def new_link(db: Session, venue_id: int):
    """The old manager link stops working at once (e.g. it was shared)."""
    venue = db.get(DbVenue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")
    venue.manage_token = secrets.token_urlsafe(24)
    db.commit()
    return venue_view(venue)


def venue_by_token(db: Session, token: str) -> DbVenue:
    venue = db.query(DbVenue).filter(DbVenue.manage_token == (token or "")).first() if token else None
    if not venue:
        raise HTTPException(status_code=404, detail="This link is no longer valid. Please ask Blossom for a new one.")
    return venue


def manager_view(db: Session, venue: DbVenue, now: datetime = None):
    """What the owner sees: their spot, offers with numbers (no couples'
    names), staff code, and their requests waiting for an answer."""
    now = now or datetime.utcnow()
    offers = (
        db.query(DbSpotOffer).filter(DbSpotOffer.spot_id == venue.spot_id)
        .order_by(DbSpotOffer.created_at.desc()).all()
    )
    views = []
    for offer in offers:
        view = db_offers.admin_view(db, offer, now)
        view.pop("couples", None)
        view.pop("staff_code", None)
        views.append(view)
    requests = (
        db.query(DbPartnerRequest).filter(DbPartnerRequest.venue_id == venue.id, DbPartnerRequest.status != "approved")
        .order_by(DbPartnerRequest.created_at.desc()).limit(10).all()
    )
    spot = venue.spot
    return {
        "venue": {
            "name": venue.name,
            "staff_code": venue.staff_code,
            "check_url": f"{SITE_URL}/venue",
            "spot": {"id": spot.id, "name": spot.name, "city": spot.city} if spot else None,
        },
        "offers": views,
        "requests": [
            {"id": r.id, "offer_title": r.offer_title, "status": r.status, "created_at": r.created_at,
             "refuse_reason": r.refuse_reason}
            for r in requests
        ],
    }


def manager_update_offer(db: Session, venue: DbVenue, offer_id: int, changes: dict, now: datetime = None):
    """Pause, resume, places, end date - at once. Wording changes go through a request."""
    offer = db.get(DbSpotOffer, offer_id)
    if not offer or offer.spot_id != venue.spot_id:
        raise HTTPException(status_code=404, detail="Offer not found.")
    allowed = {k: v for k, v in changes.items() if k in ("active", "max_couples", "ends_at")}
    view = db_offers.update_offer(db, offer_id, allowed, now)
    view.pop("couples", None)
    view.pop("staff_code", None)
    return view


# ---- emails ------------------------------------------------------------------------

def _e(value):
    return html.escape(str(value or ""))


EMAILS = {
    "received": {
        "en": ("We received your request 🌸", "Thank you!",
               ["We received your request for <b>{venue}</b> ({offer}).",
                "We'll look at it and answer you by email within 48 hours."]),
        "fr": ("Nous avons bien reçu votre demande 🌸", "Merci !",
               ["Nous avons bien reçu votre demande pour <b>{venue}</b> ({offer}).",
                "Nous l'examinons et vous répondons par e-mail sous 48 heures."]),
        "zh": ("我们已收到你的申请 🌸", "谢谢！",
               ["我们已收到 <b>{venue}</b> 的申请（{offer}）。", "我们会在 48 小时内通过邮件回复你。"]),
        "ar": ("استلمنا طلبك 🌸", "شكرًا!",
               ["استلمنا طلبك الخاص بـ <b>{venue}</b> ({offer}).", "سنراجعه ونرد عليك بالبريد خلال 48 ساعة."]),
    },
    "approved": {
        "en": ("🌸 Your Blossom offer is live!", "Your offer is live!",
               ["<b>{venue}</b> is now a Blossom partner: couples who match on Blossom and invite each other to your place get <b>{offer}</b>.",
                "<b>At the counter:</b> the couple shows a code like BLSM-7K3F. Your staff open <a href=\"{check}\">{check_short}</a>, type the couple's code and your staff code <b>{staff}</b>, then tap “Mark as used”. Each code works once, before its deadline.",
                "<b>Your manager page</b> (keep this link private): pause or renew your offer, add places, and see how many couples came.",
                "Your counter poster, to print: <a href=\"{poster}\">{poster_short}</a>"],
               "Open my manager page"),
        "fr": ("🌸 Votre offre Blossom est en ligne !", "Votre offre est en ligne !",
               ["<b>{venue}</b> est maintenant partenaire de Blossom : les couples qui matchent sur Blossom et s'invitent chez vous obtiennent <b>{offer}</b>.",
                "<b>Au comptoir :</b> le couple montre un code du type BLSM-7K3F. Votre équipe ouvre <a href=\"{check}\">{check_short}</a>, tape le code du couple et votre code du personnel <b>{staff}</b>, puis « Marquer comme utilisé ». Chaque code ne sert qu'une fois, avant sa date limite.",
                "<b>Votre page de gestion</b> (gardez ce lien privé) : mettez votre offre en pause ou renouvelez-la, ajoutez des places et voyez combien de couples sont venus.",
                "Votre affiche de comptoir, à imprimer : <a href=\"{poster}\">{poster_short}</a>"],
               "Ouvrir ma page de gestion"),
        "zh": ("🌸 你的 Blossom 优惠已上线！", "你的优惠已上线！",
               ["<b>{venue}</b> 现在是 Blossom 的合作伙伴：在 Blossom 配对并互相邀请来你店的情侣可享受 <b>{offer}</b>。",
                "<b>在柜台：</b>情侣会出示类似 BLSM-7K3F 的优惠码。店员打开 <a href=\"{check}\">{check_short}</a>，输入情侣的优惠码和店员代码 <b>{staff}</b>，然后点“标记为已使用”。每个优惠码只能在截止前使用一次。",
                "<b>你的管理页面</b>（请勿外传此链接）：暂停或续期优惠、增加名额、查看有多少对情侣到店。",
                "你的柜台海报（可打印）：<a href=\"{poster}\">{poster_short}</a>"],
               "打开我的管理页面"),
        "ar": ("🌸 عرضك على Blossom أصبح متاحًا!", "عرضك أصبح متاحًا!",
               ["أصبح <b>{venue}</b> شريكًا لـ Blossom: الأزواج الذين يتطابقون على Blossom ويدعون بعضهم إلى مكانك يحصلون على <b>{offer}</b>.",
                "<b>عند الكاونتر:</b> يُظهر الزوجان رمزًا مثل BLSM-7K3F. يفتح موظفوك <a href=\"{check}\">{check_short}</a>، ويكتبون رمز الزوجين ورمز الموظفين <b>{staff}</b>، ثم \"تحديد كمستخدم\". يعمل كل رمز مرة واحدة قبل موعده النهائي.",
                "<b>صفحة الإدارة الخاصة بك</b> (احتفظ بالرابط سرًا): أوقف عرضك أو جدّده، أضف أماكن، وشاهد عدد الأزواج الذين جاؤوا.",
                "ملصق الكاونتر للطباعة: <a href=\"{poster}\">{poster_short}</a>"],
               "فتح صفحة الإدارة"),
    },
    "refused": {
        "en": ("Your Blossom partner request", "Thank you for your request",
               ["Thank you for wanting to welcome Blossom couples at <b>{venue}</b>.",
                "We can't publish this offer for now.{reason}",
                "You're welcome to send a new request any time: <a href=\"{form}\">{form_short}</a>"]),
        "fr": ("Votre demande de partenariat Blossom", "Merci pour votre demande",
               ["Merci de vouloir accueillir des couples Blossom chez <b>{venue}</b>.",
                "Nous ne pouvons pas publier cette offre pour le moment.{reason}",
                "Vous pouvez envoyer une nouvelle demande quand vous voulez : <a href=\"{form}\">{form_short}</a>"]),
        "zh": ("你的 Blossom 合作申请", "感谢你的申请",
               ["感谢你愿意在 <b>{venue}</b> 接待 Blossom 情侣。", "我们暂时无法发布这个优惠。{reason}",
                "欢迎随时重新申请：<a href=\"{form}\">{form_short}</a>"]),
        "ar": ("طلب شراكتك مع Blossom", "شكرًا على طلبك",
               ["شكرًا لرغبتك في استقبال أزواج Blossom في <b>{venue}</b>.", "لا يمكننا نشر هذا العرض حاليًا.{reason}",
                "يمكنك إرسال طلب جديد في أي وقت: <a href=\"{form}\">{form_short}</a>"]),
    },
}


def _short(url):
    return url.replace("https://", "").replace("http://", "")


def _received_email(request: DbPartnerRequest):
    subject, title, paragraphs = EMAILS["received"][_lang(request.language)]
    body = [p.format(venue=_e(request.venue_name), offer=_e(request.offer_title)) for p in paragraphs]
    return subject, mailer.card(title, body)


def _approved_email(venue: DbVenue, offer_title: str, offer_id: int):
    subject, title, paragraphs, button = EMAILS["approved"][_lang(venue.language)]
    check = f"{SITE_URL}/venue"
    poster = f"{SITE_URL}/poster/{offer_id}"
    values = dict(venue=_e(venue.name), offer=_e(offer_title), staff=_e(venue.staff_code),
                  check=check, check_short=_short(check), poster=poster, poster_short=_short(poster))
    body = [p.format(**values) for p in paragraphs]
    return subject, mailer.card(title, body, (button, manage_url(venue)))


def _refused_email(request: DbPartnerRequest):
    subject, title, paragraphs = EMAILS["refused"][_lang(request.language)]
    form = f"{SITE_URL}/partner"
    reason = f" {_e(request.refuse_reason)}" if request.refuse_reason else ""
    values = dict(venue=_e(request.venue_name), reason=reason, form=form, form_short=_short(form))
    return subject, mailer.card(title, [p.format(**values) for p in paragraphs])
