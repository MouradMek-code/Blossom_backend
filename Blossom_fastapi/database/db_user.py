from fastapi import HTTPException
from sqlalchemy.testing.pickleable import User
from methods import HashedPassword
from database.models import DbUser
from routers.schemas import UserBase
from sqlalchemy.orm import Session
from auth import oauth2
def create_user(db : Session,request:UserBase):

    new_user = DbUser(

    username=request.username,
    email=request.email,
    phone_number=request.phone_number,
    password=HashedPassword.HashedPassword.hash_password(request.password)
    )
    access_token = oauth2.create_access_token(data={"username": request.username})
    db.add(new_user)
    db.commit()
    db.refresh(new_user)


    return {"username":new_user.username,"email":new_user.email,"phone_number":new_user.phone_number,"access_token":access_token}

def get_all_users(db:Session):

    return db.query(DbUser).all()

def get_user_by_id(db:Session,id:int):

    db_user = db.query(DbUser).filter(DbUser.id == id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db.query(DbUser).filter(DbUser.id == id).first()

def delete_user_by_id(db:Session,id:int):

    db_user = db.query(DbUser).filter(DbUser.id == id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(db_user)
    db.commit()
    return {"message":f"User with id {id} has been deleted"}

def delete_all_users(db:Session):
    try:
        db.query(DbUser).delete()
        db.commit()
    except:
        raise HTTPException(status_code=404, detail="error on deleting all users")
    return {"message":f"Users had been deleted"}

def get_user_by_username(db:Session,username:str):
    user=db.query(DbUser).filter(DbUser.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    return user