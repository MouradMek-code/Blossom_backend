"""Events organised by members - see database/db_events.py."""
from typing import List, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.oauth2 import get_current_user
from database import db_events
from database.database import get_db
from routers.analytics import optional_user
from routers.schemas import UserAuth

router = APIRouter(prefix="/events", tags=["events"])


class EventUpdate(BaseModel):
    """Only the fields sent change."""
    kind: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1500)
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    place_name: Optional[str] = Field(default=None, max_length=150)
    map_url: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    max_people: Optional[int] = None
    languages: Optional[Union[List[str], str]] = None
    women_only: Optional[bool] = None
    comments_open: Optional[bool] = None


class CommentIn(BaseModel):
    text: str = Field(max_length=2000)
    parent_id: Optional[int] = None


class ReportIn(BaseModel):
    comment_id: Optional[int] = None
    reason: Optional[str] = Field(default=None, max_length=1000)


def _require_admin(user):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")


# ---- everyone ------------------------------------------------------------------

@router.get("")
def list_events(
    city: Optional[str] = None,
    country: Optional[str] = None,
    kind: Optional[str] = None,
    spot_id: Optional[int] = None,
    mine: bool = False,
    db: Session = Depends(get_db),
    user=Depends(optional_user),
):
    """Upcoming events (visitors too); mine=1: the ones I organise or I'm interested in."""
    return db_events.list_events(db, user, city, country, kind, spot_id, mine)


@router.get("/locations")
def event_locations(db: Session = Depends(get_db)):
    return db_events.locations(db)


@router.get("/admin/reports")
def list_reports(db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_events.list_reports(db)


@router.post("/admin/reports/{report_id}/handled")
def report_handled(report_id: int, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    return db_events.mark_report_handled(db, report_id)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    return db_events.delete_comment(db, user, comment_id)


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db), user=Depends(optional_user)):
    return db_events.get_event(db, event_id, user)


# ---- members -------------------------------------------------------------------

@router.post("")
def create_event(
    title: str = Form(...),
    description: str = Form(...),
    starts_at: str = Form(...),
    place_name: Optional[str] = Form(None),
    kind: str = Form("group"),
    ends_at: Optional[str] = Form(None),
    map_url: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    spot_id: Optional[int] = Form(None),
    max_people: Optional[int] = Form(None),
    languages: Optional[str] = Form(None),
    women_only: Optional[bool] = Form(False),
    comments_open: Optional[bool] = Form(True),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: UserAuth = Depends(get_current_user),
):
    data = {
        "title": title, "description": description, "starts_at": starts_at, "ends_at": ends_at,
        "place_name": place_name, "kind": kind, "map_url": map_url, "city": city, "country": country,
        "spot_id": spot_id, "max_people": max_people, "languages": languages,
        "women_only": women_only, "comments_open": comments_open,
    }
    return db_events.create_event(db, user, data, image)


@router.patch("/{event_id}")
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db),
                 user: UserAuth = Depends(get_current_user)):
    return db_events.update_event(db, user, event_id, payload.model_dump(exclude_unset=True))


@router.put("/{event_id}/image")
def replace_image(event_id: int, image: UploadFile = File(...), db: Session = Depends(get_db),
                  user: UserAuth = Depends(get_current_user)):
    return db_events.replace_image(db, user, event_id, image)


@router.delete("/{event_id}")
def cancel_event(event_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                 user: UserAuth = Depends(get_current_user)):
    """The organiser cancels; an admin removes."""
    return db_events.cancel_event(db, user, event_id, background_tasks)


@router.post("/{event_id}/interest")
def interested(event_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
               user: UserAuth = Depends(get_current_user)):
    return db_events.set_interest(db, user, event_id, background_tasks, True)


@router.delete("/{event_id}/interest")
def not_interested(event_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                   user: UserAuth = Depends(get_current_user)):
    return db_events.set_interest(db, user, event_id, background_tasks, False)


@router.get("/{event_id}/interested")
def interested_people(event_id: int, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    """The organiser (and admins) only."""
    return db_events.interested_people(db, user, event_id)


@router.post("/{event_id}/interested/{profile_id}/match")
def match_person(event_id: int, profile_id: int, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    return db_events.answer_interest(db, user, event_id, profile_id, "match", background_tasks)


@router.post("/{event_id}/interested/{profile_id}/decline")
def decline_person(event_id: int, profile_id: int, background_tasks: BackgroundTasks,
                   db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    return db_events.answer_interest(db, user, event_id, profile_id, "decline", background_tasks)


@router.get("/{event_id}/comments")
def list_comments(event_id: int, db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    """Members only."""
    return db_events.list_comments(db, user, event_id)


@router.post("/{event_id}/comments")
def add_comment(event_id: int, payload: CommentIn, background_tasks: BackgroundTasks,
                db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    return db_events.add_comment(db, user, event_id, payload.text, payload.parent_id, background_tasks)


@router.post("/{event_id}/report")
def report(event_id: int, payload: ReportIn, background_tasks: BackgroundTasks,
           db: Session = Depends(get_db), user: UserAuth = Depends(get_current_user)):
    return db_events.report(db, user, event_id, payload.comment_id, payload.reason, background_tasks)
