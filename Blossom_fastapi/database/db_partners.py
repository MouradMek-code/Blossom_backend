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
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import db_offers, db_push, mailer
from database.models import DbBusinessMessage, DbDateSpot, DbPartnerRequest, DbSpotOffer, DbVenue

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


# ---- places already on Blossom ------------------------------------------------------

def _fold(value) -> str:
    """"Café Rosé" -> "cafe rose": search ignores accents and case."""
    value = unicodedata.normalize("NFKD", str(value or "")).lower()
    return "".join(c for c in value if not unicodedata.combining(c))


def _spot_brief(spot: DbDateSpot, partner: bool) -> dict:
    return {
        "id": spot.id,
        "name": spot.name,
        "neighborhood": spot.neighborhood,
        "city": spot.city,
        "country": spot.country,
        "image_url": spot.image_url,
        "category": spot.category,
        # Already a Blossom partner: new gifts are asked for from its manager page.
        "partner": partner,
    }


def search_spots(db: Session, query: str, limit: int = 8) -> list:
    """Spots whose name (or name + city) contains every word typed."""
    words = _fold(query).split()
    if not words or len("".join(words)) < 2:
        return []
    found = []
    for spot in db.query(DbDateSpot).filter(DbDateSpot.status == "published").order_by(DbDateSpot.name).all():
        name = _fold(spot.name)
        haystack = f"{name} {_fold(spot.neighborhood)} {_fold(spot.city)}"
        if all(w in haystack for w in words):
            # Names starting with what was typed first.
            found.append((0 if name.startswith(words[0]) else 1, spot))
    found.sort(key=lambda item: item[0])
    spots = [spot for _, spot in found[:limit]]
    partners = {sid for (sid,) in db.query(DbVenue.spot_id).filter(DbVenue.spot_id.in_([s.id for s in spots]))} if spots else set()
    return [_spot_brief(s, s.id in partners) for s in spots]


def spot_for_form(db: Session, spot_id: int) -> dict:
    spot = db.get(DbDateSpot, spot_id)
    if not spot or spot.status != "published":
        raise HTTPException(status_code=404, detail="This place isn't on Blossom anymore.")
    partner = db.query(DbVenue.id).filter(DbVenue.spot_id == spot.id).first() is not None
    return _spot_brief(spot, partner)


# ---- requests --------------------------------------------------------------------

def create_request(db: Session, background_tasks: BackgroundTasks, data: dict, venue: DbVenue = None,
                   now: datetime = None):
    now = now or datetime.utcnow()
    title = _text(data.get("offer_title"), 120)
    _check_offer_fields(title, data.get("max_couples"), data.get("ends_at"), data.get("valid_hours"), now)

    spot = None
    if venue is None and data.get("spot_id"):
        spot = db.get(DbDateSpot, data["spot_id"])
        if not spot:
            raise HTTPException(status_code=404, detail={
                "reason": "spot_gone",
                "message": "This place isn't on Blossom anymore. Please fill in your place instead.",
            })
        # A partner already has a manager page, where new gifts are asked for.
        # Not accepted from the public form: approving it would send the
        # venue's manager link and staff code to whoever filled it in.
        if db.query(DbVenue.id).filter(DbVenue.spot_id == spot.id).first():
            raise HTTPException(status_code=409, detail={
                "reason": "already_partner",
                "message": "This place is already a Blossom partner: new gifts are asked for from its "
                           "manager page. Ask the person who manages it, or have the link sent to the "
                           "venue's email.",
            })

    if venue is None:
        email = _text(data.get("contact_email"), 200)
        if spot is not None:
            name, city, country, map_url = spot.name, spot.city, spot.country, spot.map_url
        else:
            name = _text(data.get("venue_name"), 150)
            city = _text(data.get("city"), 120)
            country = _text(data.get("country"), 120)
            if not name or len(name) < 2:
                raise HTTPException(status_code=400, detail="Enter the name of your place.")
            if not city or not country:
                raise HTTPException(status_code=400, detail="Enter the city and the country.")
            map_url = _text(data.get("map_url"), 500)
            if map_url and not map_url.lower().startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="The Google Maps link should start with https://")
        if not email or not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email address, so we can answer you.")
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
        spot_id=spot.id if spot else None,
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
    # The venue picked its place on the form.
    if request.spot_id and request.spot:
        return request.spot
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
        # True when the venue itself said "this is my place" on the form.
        "spot_chosen": bool(request.spot_id),
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

    # A place a member suggested and nobody approved yet: the gift makes it public.
    spot.status = "published"
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


# ---- "Lost my manager link" -------------------------------------------------------

LINK_EMAILS_PER_HOUR = 3
_link_requests = defaultdict(list)  # email -> times (per server process)

LINK_EMAIL = {
    "en": ("Your Blossom manager link", "Your manager page",
           ["Here is the private link to manage <b>{venue}</b> on Blossom: pause or renew your offer, add places and see how many couples came.",
            "Keep it private. If someone else got it, ask Blossom for a new one."], "Open my manager page"),
    "fr": ("Votre lien de gestion Blossom", "Votre page de gestion",
           ["Voici le lien privé pour gérer <b>{venue}</b> sur Blossom : mettez votre offre en pause ou renouvelez-la, ajoutez des places et voyez combien de couples sont venus.",
            "Gardez-le privé. Si quelqu'un d'autre l'a eu, demandez-en un nouveau à Blossom."], "Ouvrir ma page de gestion"),
    "zh": ("你的 Blossom 管理链接", "你的管理页面",
           ["这是在 Blossom 上管理 <b>{venue}</b> 的私人链接：暂停或续期优惠、增加名额、查看有多少对情侣到店。",
            "请勿外传。如果被别人拿到，请联系 Blossom 更换新链接。"], "打开我的管理页面"),
    "ar": ("رابط الإدارة الخاص بك على Blossom", "صفحة الإدارة الخاصة بك",
           ["هذا هو الرابط الخاص لإدارة <b>{venue}</b> على Blossom: أوقف عرضك أو جدّده، أضف أماكن، وشاهد عدد الأزواج الذين جاؤوا.",
            "احتفظ به سرًا. إن حصل عليه شخص آخر، اطلب رابطًا جديدًا من Blossom."], "فتح صفحة الإدارة"),
}


def send_manager_links(db: Session, background_tasks: BackgroundTasks, email: str, now: datetime = None):
    """Email the manager link(s) of the venues registered with this address.
    Always the same answer, so nobody can find out which emails are partners."""
    now = now or datetime.utcnow()
    email = _text(email, 200) or ""
    key = email.lower()
    recent = [t for t in _link_requests.get(key, []) if t > now - timedelta(hours=1)]
    _link_requests[key] = recent
    if EMAIL_RE.match(email) and len(recent) < LINK_EMAILS_PER_HOUR:
        recent.append(now)
        venues = db.query(DbVenue).filter(func.lower(DbVenue.contact_email) == key).all()
        for venue in venues:
            subject, title, paragraphs, button = LINK_EMAIL[_lang(venue.language)]
            body = [p.format(venue=_e(venue.name)) for p in paragraphs]
            background_tasks.add_task(mailer.send_email, venue.contact_email, subject,
                                      mailer.card(title, body, (button, manage_url(venue))))
    return {"ok": True}


# ---- "Contact us" for businesses ------------------------------------------------

TOPICS = ("partnership", "question", "problem", "other")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", mailer.SENDER["email"])
MESSAGES_PER_DAY = 5


def create_business_message(db: Session, background_tasks: BackgroundTasks, data: dict, now: datetime = None):
    now = now or datetime.utcnow()
    name = _text(data.get("name"), 120)
    email = _text(data.get("email"), 200)
    message = _long_text(data.get("message"), 3000)
    topic = data.get("topic") if data.get("topic") in TOPICS else "other"
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Enter your name.")
    if not email or not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address, so we can answer you.")
    if not message or len(message) < 5:
        raise HTTPException(status_code=400, detail="Write your message.")
    sent_today = db.query(func.count(DbBusinessMessage.id)).filter(
        func.lower(DbBusinessMessage.email) == email.lower(),
        DbBusinessMessage.created_at > now - timedelta(days=1),
    ).scalar()
    if sent_today >= MESSAGES_PER_DAY:
        raise HTTPException(status_code=429, detail="We already have your messages - we'll answer soon.")

    row = DbBusinessMessage(
        created_at=now, name=name, business=_text(data.get("business"), 150), email=email,
        phone=_text(data.get("phone"), 40), topic=topic, message=message,
        language=_lang(data.get("language")), handled=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    db_push.notify_business_message(db, background_tasks, row)
    details = "".join(
        f"<b>{label}:</b> {_e(value)}<br>" for label, value in (
            ("Name", row.name), ("Business", row.business), ("Email", row.email),
            ("Phone", row.phone), ("Topic", row.topic),
        ) if value
    )
    body = [details, _e(row.message).replace(chr(10), "<br>"), "Reply to this email to answer them."]
    background_tasks.add_task(
        mailer.send_email, ADMIN_EMAIL, f"📩 Blossom business message from {row.name}",
        mailer.card("New business message", body), {"email": row.email, "name": row.name},
    )
    return {"id": row.id, "ok": True}


def business_message_view(row: DbBusinessMessage):
    return {
        "id": row.id, "created_at": row.created_at, "name": row.name, "business": row.business,
        "email": row.email, "phone": row.phone, "topic": row.topic, "message": row.message,
        "language": row.language, "handled": row.handled,
    }


def list_business_messages(db: Session):
    rows = (
        db.query(DbBusinessMessage)
        .order_by(DbBusinessMessage.handled, DbBusinessMessage.created_at.desc())
        .limit(60).all()
    )
    return [business_message_view(r) for r in rows]


def set_handled(db: Session, message_id: int, handled: bool):
    row = db.get(DbBusinessMessage, message_id)
    if not row:
        raise HTTPException(status_code=404, detail="Message not found.")
    row.handled = bool(handled)
    db.commit()
    return business_message_view(row)
