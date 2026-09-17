from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import HTTPException, Depends, status
from sqlalchemy.orm import Session
from database.database import get_db
from database import db_user
from dotenv import load_dotenv
import os

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = 'HS256'

# People stay logged in until they log out: a session lasts a year, and the
# app swaps it for a fresh one (POST /refresh_token) whenever it's opened. It
# used to be 15 minutes, which logged everyone out constantly.
ACCESS_TOKEN_EXPIRE_DAYS = 365


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    # "iat" (issued at) lets a password reset cut off sessions issued before it.
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db_user.get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception

    # Long sessions must still end when the password is reset (e.g. someone
    # else got into the account): reject tokens issued before that moment.
    valid_after = getattr(user, "sessions_valid_after", None)
    if valid_after is not None:
        issued_at = payload.get("iat")
        if issued_at is None or datetime.utcfromtimestamp(issued_at) < valid_after:
            raise credentials_exception
    return user