from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.models import DbReport, DbProfile


def create_report(db: Session, user_id: int, reported_profile_id: int, reason: str):
    profile = db.query(DbProfile).filter(DbProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.id == reported_profile_id:
        raise HTTPException(status_code=400, detail="You can't report yourself")

    report = DbReport(
        reporter_profile_id=profile.id,
        reported_profile_id=reported_profile_id,
        reason=reason
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"message": "Report submitted"}
