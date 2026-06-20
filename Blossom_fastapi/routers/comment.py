from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from database import db_comment
from auth.oauth2 import get_current_user
from database.database import get_db
from database.models import DbComment
from routers.schemas import CommentDisplay, UserAuth,CommentBase

router = APIRouter(
    prefix="/comment",tags=["comment"]
)

@router.get("/all/{post_id}",response_model=list[CommentDisplay])
async def get_comments(post_id: int,db:Session=Depends(get_db)):
    return db_comment.get_all_comments(db,post_id)

@router.post("/comment",response_model=CommentDisplay)
async def create_comment(comment:CommentBase,db:Session=Depends(get_db),current_use: UserAuth=Depends(get_current_user)):

    return db_comment.create(db,comment,current_use.username)

@router.delete("/comment/{comment_id}")
async def delete_comment(comment_id:int,db:Session=Depends(get_db),current_use: UserAuth=Depends(get_current_user)):
    return db_comment.delete_comment(comment_id,current_use.id,db)