from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from methods import HashedPassword
from database.models import DbUser, OTP
from routers.schemas import UserBase
from sqlalchemy import func
from sqlalchemy.orm import Session
from auth import oauth2
from datetime import datetime, timedelta

# How long after confirming the email code the account can be created.
VERIFIED_EMAIL_VALID_FOR = timedelta(minutes=30)


def _verified_email(db: Session, email) -> bool:
    email = (email or "").strip().lower()
    return bool(email) and db.query(OTP.id).filter(
        func.lower(OTP.email) == email,
        OTP.verified_at.isnot(None),
        OTP.verified_at >= datetime.now() - VERIFIED_EMAIL_VALID_FOR,
    ).first() is not None

def create_user(db : Session,request:UserBase):

    # Explicit duplicate checks so the client gets a clear 409 with a
    # specific message instead of a raw 500 from the DB unique constraint.
    # These mirror the /user/send_email gate (username + email + phone) so a
    # duplicate is caught up-front before the OTP is sent, and again here as a
    # race-safety net - never only here (that would pass the gate, send a code,
    # then reject at the very end).
    if db.query(DbUser).filter(DbUser.username == request.username).first():
        raise HTTPException(status_code=409, detail="This username is already taken. Please choose another.")
    if db.query(DbUser).filter(DbUser.email == request.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists. Try logging in instead.")
    if request.phone_number and db.query(DbUser).filter(DbUser.phone_number == request.phone_number).first():
        raise HTTPException(status_code=409, detail="An account with this phone number already exists.")
    # Only for an email whose code was just confirmed (/user/verify-email).
    # This used to be open: calling it straight away skipped the code, which
    # is how accounts got made without any verification.
    if not _verified_email(db, request.email):
        raise HTTPException(status_code=403, detail="Please confirm your email with the code we sent you first.")

    new_user = DbUser(

    username=request.username,
    email=request.email,
    phone_number=request.phone_number,
    date_of_birth=request.date_of_birth,
    password=HashedPassword.HashedPassword.hash_password(request.password),
    created_at=datetime.utcnow(),
    )
    access_token = oauth2.create_access_token(data={"username": request.username})
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        # Fallback in case of a race between the check above and commit.
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with these details already exists.")
    # The confirmed code is used up.
    db.query(OTP).filter(func.lower(OTP.email) == request.email.strip().lower()).delete(synchronize_session=False)
    db.commit()


    return {"username":new_user.username,"email":new_user.email,"phone_number":new_user.phone_number,"access_token":access_token}

def get_user_by_username(db:Session,username:str):
    user=db.query(DbUser).filter(DbUser.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    return user