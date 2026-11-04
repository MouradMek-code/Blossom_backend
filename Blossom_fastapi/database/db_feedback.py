""""Report a problem", inside the app and on the website - members and
visitors alike, without leaving Blossom (Google Play's Child Safety
Standards ask for it). A child safety concern, a scam, harassment, a bug...
The admins are told at once; they see the reports in Admin → Reports.
"""
import re
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from database import db_push
from database.models import DbFeedback, DbProfile

KINDS = ("child_safety", "scam", "harassment", "bug", "other")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PER_HOUR = 5  # from one member or one email
ANONYMOUS_PER_10_MIN = 20  # from visitors who leave no email, all together


def create(db: Session, user, data: dict, background_tasks: BackgroundTasks, now: datetime = None) -> dict:
    now = now or datetime.utcnow()
    kind = data.get("kind")
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="Please choose what it's about.")
    message = " ".join((data.get("message") or "").split()) if kind != "bug" else (data.get("message") or "").strip()
    if len(message) < 5:
        raise HTTPException(status_code=400, detail="Please tell us a little more.")
    message = message[:2000]

    profile = db.query(DbProfile).filter(DbProfile.user_id == user.id).first() if user else None
    email = (data.get("email") or "").strip()[:200] or None
    if email and not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please check the email address, or leave it empty.")

    recent = db.query(DbFeedback).filter(DbFeedback.created_at > now - timedelta(hours=1))
    if profile:
        too_many = recent.filter(DbFeedback.profile_id == profile.id).count() >= PER_HOUR
    elif email:
        too_many = recent.filter(DbFeedback.email == email).count() >= PER_HOUR
    else:
        too_many = db.query(DbFeedback).filter(
            DbFeedback.created_at > now - timedelta(minutes=10),
            DbFeedback.profile_id.is_(None), DbFeedback.email.is_(None),
        ).count() >= ANONYMOUS_PER_10_MIN
    if too_many:
        raise HTTPException(status_code=429, detail="We already have your reports - we'll look at them first.")

    about = data.get("about_profile_id")
    report = DbFeedback(
        created_at=now,
        kind=kind,
        message=message,
        profile_id=profile.id if profile else None,
        reporter_name=(profile.first_name if profile else None) or (user.username if user else None),
        email=email or (user.email if user else None),
        about_profile_id=about if isinstance(about, int) else None,
        language=(data.get("language") or "")[:2] or None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    db_push.notify_feedback(db, background_tasks, report)
    return {"id": report.id}


def _iso(value):
    return value.isoformat() + "Z" if value else None


def list_reports(db: Session, include_handled: bool = False) -> list:
    """Admins: newest first; child safety on top of what's still open."""
    query = db.query(DbFeedback)
    if not include_handled:
        query = query.filter(DbFeedback.handled.is_(False))
    rows = query.order_by(DbFeedback.id.desc()).all()
    about_ids = {r.about_profile_id for r in rows if r.about_profile_id}
    names = {
        p.id: p.first_name
        for p in db.query(DbProfile).filter(DbProfile.id.in_(about_ids or [0]))
    }
    rows.sort(key=lambda r: (r.handled, r.kind != "child_safety"))
    return [
        {
            "id": r.id,
            "created_at": _iso(r.created_at),
            "kind": r.kind,
            "message": r.message,
            "reporter": {"profile_id": r.profile_id, "name": r.reporter_name, "email": r.email},
            "about": {"profile_id": r.about_profile_id, "name": names.get(r.about_profile_id)}
            if r.about_profile_id else None,
            "handled": bool(r.handled),
        }
        for r in rows
    ]


def set_handled(db: Session, report_id: int, handled: bool) -> dict:
    report = db.get(DbFeedback, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    report.handled = handled
    db.commit()
    return {"id": report.id, "handled": report.handled}


def delete(db: Session, report_id: int) -> dict:
    report = db.get(DbFeedback, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    db.delete(report)
    db.commit()
    return {"deleted": report_id}
