from fastapi import FastAPI
from pip._internal.network import auth

from database import models
from database.database import engine
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routers import user, post,comment,profile,profile_language,likes,match,message
from auth import authentication

app = FastAPI()
app.include_router(user.router)
app.include_router(post.router)
app.include_router(authentication.router)
app.include_router(comment.router)
app.include_router(profile.router)
app.include_router(profile_language.router)
app.include_router(likes.router)
app.include_router(match.router)
app.include_router(message.router)
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}



models.Base.metadata.create_all(bind=engine)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)