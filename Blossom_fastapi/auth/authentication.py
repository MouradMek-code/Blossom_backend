from fastapi import APIRouter, HTTPException, Depends
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from auth import oauth2
from database.database import get_db
from database.models import DbUser
from methods.HashedPassword import HashedPassword
router=APIRouter(tags=["authentication"])

@router.post('/login')
async def login(request : OAuth2PasswordRequestForm = Depends(),db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm always names this field "username" per spec,
    # but the value itself can be either a username or an email - look up
    # by whichever one matches.
    identifier = (request.username or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Please enter your username or email.")

    request_password = request.password
    if not request_password:
        raise HTTPException(status_code=400, detail="Please enter your password.")

    user = db.query(DbUser).filter(
        (DbUser.username == identifier) | (DbUser.email == identifier)
    ).first()
    if not user:
       raise HTTPException(status_code=401, detail="No account found with that username or email.")

    if not HashedPassword.verify_password(request_password, user.password):
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again.")

    access_token = oauth2.create_access_token(data={"username":user.username})

    return {"access_token":access_token,"token_type":"bearer","user_id":user.id,"username":user.username}


@router.post('/refresh_token')
def refresh_token(current_user: DbUser = Depends(oauth2.get_current_user)):
    """Swap a still-valid session for a fresh one-year session. The app calls
    this when it's opened, so anyone who uses it stays logged in until they
    log out. An invalid session (expired, or cut off by a password reset)
    gets 401 like any other request."""
    access_token = oauth2.create_access_token(data={"username": current_user.username})
    return {"access_token": access_token, "token_type": "bearer", "user_id": current_user.id, "username": current_user.username}

