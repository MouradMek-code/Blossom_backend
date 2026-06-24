from fastapi import FastAPI
from pip._internal.network import auth
from sqlalchemy import text

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

# Base.metadata.create_all only creates tables that don't exist yet - it
# won't add new columns to tables that were already created by a previous
# deploy. These ALTER TABLE statements are idempotent (IF NOT EXISTS) so
# they're safe to run on every startup without an Alembic migration setup.
with engine.begin() as connection:
    connection.execute(text(
        "ALTER TABLE profile_like ADD COLUMN IF NOT EXISTS seen BOOLEAN NOT NULL DEFAULT false"
    ))
    connection.execute(text(
        "ALTER TABLE match ADD COLUMN IF NOT EXISTS seen_by_profile1 BOOLEAN NOT NULL DEFAULT false"
    ))
    connection.execute(text(
        "ALTER TABLE match ADD COLUMN IF NOT EXISTS seen_by_profile2 BOOLEAN NOT NULL DEFAULT false"
    ))
    connection.execute(text(
        "ALTER TABLE profile_photos ADD COLUMN IF NOT EXISTS public_id VARCHAR(255)"
    ))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)