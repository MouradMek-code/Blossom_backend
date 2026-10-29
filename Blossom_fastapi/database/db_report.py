"""Members reporting members. Admins get a notification for each report and
read them in Admin (list_reports); a report keeps the names, so it still
says who and why after an account is deleted (see clear_profile)."""
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from database import db_push
from database.models import DbProfile, DbReport

REASON_MAX = 1000


def create_report(db: Session, user_id: int, reported_profile_id: int, reason: str,
                  background_tasks: BackgroundTasks = None):
    profile = db.query(DbProfile).filter(DbProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.id == reported_profile_id:
        raise HTTPException(status_code=400, detail="You can't report yourself")

    reported = db.get(DbProfile, reported_profile_id)
    if not reported:
        raise HTTPException(status_code=404, detail="This profile no longer exists.")

    reason = (reason or "").strip()[:REASON_MAX]
    if not reason:
        raise HTTPException(status_code=400, detail="Say what happened.")

    # The same person reporting the same person again within a day: once is
    # enough (and no second notification).
    recent = db.query(DbReport.id).filter(
        DbReport.reporter_profile_id == profile.id,
        DbReport.reported_profile_id == reported.id,
        DbReport.created_at >= datetime.utcnow() - timedelta(days=1),
    ).first()
    if recent:
        return {"message": "Report submitted"}

    report = DbReport(
        reporter_profile_id=profile.id,
        reported_profile_id=reported.id,
        reporter_name=profile.first_name,
        reported_name=reported.first_name,
        reason=reason,
        created_at=datetime.utcnow(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    if background_tasks is not None:
        db_push.notify_profile_report(db, background_tasks, report)
    return {"message": "Report submitted"}


def _person(profile: DbProfile, name: str):
    """Who, for the admin - or just the name when the account was deleted."""
    if profile is None:
        return {"id": None, "user_id": None, "name": name, "deleted": True}
    photos = sorted(profile.photos, key=lambda p: p.id) if profile.photos else []
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "name": profile.first_name or name,
        "age": profile.age,
        "city": profile.city,
        "photo": photos[0].image_url if photos else None,
        "deleted": False,
        "verified": profile.verified_at is not None,
        "verify_by": profile.verify_deadline.isoformat() + "Z"
        if profile.verify_deadline and not profile.verified_at else None,
    }


def list_reports(db: Session, include_handled: bool = False):
    """Admin: the reports, newest first (only the ones not handled yet,
    unless include_handled). Each says how many times that person was
    reported in all."""
    query = db.query(DbReport)
    if not include_handled:
        query = query.filter(DbReport.handled == False)  # noqa: E712
    reports = query.order_by(DbReport.created_at.desc(), DbReport.id.desc()).limit(200).all()
    ids = {r.reporter_profile_id for r in reports} | {r.reported_profile_id for r in reports}
    ids.discard(None)
    profiles = {
        p.id: p for p in db.query(DbProfile).options(selectinload(DbProfile.photos)).filter(DbProfile.id.in_(ids)).all()
    } if ids else {}
    reported_ids = [r.reported_profile_id for r in reports if r.reported_profile_id]
    totals = dict(
        db.query(DbReport.reported_profile_id, func.count(DbReport.id))
        .filter(DbReport.reported_profile_id.in_(reported_ids))
        .group_by(DbReport.reported_profile_id).all()
    ) if reported_ids else {}
    return [
        {
            "id": r.id,
            "reason": r.reason,
            "created_at": r.created_at.isoformat(timespec="seconds") + "Z" if r.created_at else None,
            "handled": r.handled,
            "reporter": _person(profiles.get(r.reporter_profile_id), r.reporter_name),
            "reported": _person(profiles.get(r.reported_profile_id), r.reported_name),
            "times_reported": totals.get(r.reported_profile_id, 1),
        }
        for r in reports
    ]


def set_handled(db: Session, report_id: int, handled: bool = True):
    report = db.get(DbReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    report.handled = handled
    db.commit()
    return {"handled": report.handled}


def clear_profile(db: Session, profile: DbProfile):
    """Before a profile is deleted: its reports keep the names (so an admin
    can still read who and why) and lose the link to the profile, which the
    database would otherwise refuse to delete."""
    for report in db.query(DbReport).filter(DbReport.reported_profile_id == profile.id):
        report.reported_name = report.reported_name or profile.first_name
        report.reported_profile_id = None
    for report in db.query(DbReport).filter(DbReport.reporter_profile_id == profile.id):
        report.reporter_name = report.reporter_name or profile.first_name
        report.reporter_profile_id = None
