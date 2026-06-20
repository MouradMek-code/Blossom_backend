from fastapi import HTTPException
from database.models import DbPost
from routers.schemas import UserBase, PostBase
from sqlalchemy.orm import Session
from datetime import datetime

def create_post(db:Session,request:PostBase,user_id:int):
    db_post=DbPost(
        image_url=request.image_url,
        image_type=request.image_type,
        caption=request.caption,
        user_id=user_id,
    timestamp=datetime.now())
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

def  get_post_by_user_id(db:Session,user_id:int):
    return db.query(DbPost).filter(DbPost.user_id == user_id).first()

def get_all_posts(db:Session):
    return db.query(DbPost).all()

def delete_post_by_id(db:Session,id:int,user_id:int):
    db_post = db.query(DbPost).filter(DbPost.id == id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post id not found")
    if db_post.user_id != user_id:
        raise HTTPException(status_code=404, detail="only post creator can delete the post")
    db.delete(db_post)
    db.commit()
    return {"message": f"Post with id {id} has been deleted"}


