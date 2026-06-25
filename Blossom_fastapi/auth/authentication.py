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
    identifier = request.username
    user = db.query(DbUser).filter(
        (DbUser.username == identifier) | (DbUser.email == identifier)
    ).first()
    if not user:
       raise HTTPException(status_code=404, detail="Incorrect username or email")

    request_password=request.password
    if not request_password:
        raise HTTPException(status_code=404, detail="please specify password")
    if not HashedPassword.verify_password(request_password, user.password):
        raise HTTPException(status_code=404, detail="Incorrect  password")

    access_token = oauth2.create_access_token(data={"username":user.username})

    return {"access_token":access_token,"token_type":"bearer","user_id":user.id,"username":user.username}

