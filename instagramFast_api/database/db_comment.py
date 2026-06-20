from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database.models import  DbComment;
from routers.schemas import CommentBase


def create(db: Session,comment: CommentBase,username:str):
  db_comment=DbComment(
      username=username,
      content=comment.content,
      post_id=comment.post_id,
      timestamp=datetime.now(),
  )
  db.add(db_comment)
  db.commit()
  db.refresh(db_comment)

  return db_comment

def get_all_comments(db: Session,post_id: int):
    return db.query(DbComment).filter(DbComment.post_id == post_id).all()

def delete_comment(comment_id: int,user_id:int,db: Session):

    db_comment=db.query(DbComment).filter(DbComment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    post=db_comment.post
    if post.user_id != user_id:
        raise HTTPException(status_code=404, detail="can not delete comment of other users only the comment belongs to you ")
    db.delete(db_comment)
    db.commit()

    return {"message":f"Comment {db_comment.content} deleted successfully "}
