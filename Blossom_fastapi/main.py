from fastapi import FastAPI
from pip._internal.network import auth
from sqlalchemy import text

from database import models
from database.database import engine
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routers import user, post,comment,profile,profile_language,profile_learning_language,likes,match,message,block,report,date_spot,geo,push
from auth import authentication

app = FastAPI()
app.include_router(user.router)
app.include_router(post.router)
app.include_router(authentication.router)
app.include_router(comment.router)
app.include_router(profile.router)
app.include_router(profile_language.router)
app.include_router(profile_learning_language.router)
app.include_router(likes.router)
app.include_router(match.router)
app.include_router(message.router)
app.include_router(block.router)
app.include_router(report.router)
app.include_router(date_spot.router)
app.include_router(geo.router)
app.include_router(push.router)
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
    connection.execute(text(
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS date_of_birth DATE"
    ))
    connection.execute(text(
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS first_date_preference VARCHAR(100)"
    ))
    connection.execute(text(
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS past_relationships_count VARCHAR(50)"
    ))
    connection.execute(text(
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS last_breakup_reason VARCHAR(100)"
    ))
    connection.execute(text(
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false"
    ))
    connection.execute(text(
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS sessions_valid_after TIMESTAMP"
    ))
    connection.execute(text(
        "ALTER TABLE date_spots ADD COLUMN IF NOT EXISTS map_url VARCHAR(500)"
    ))
    connection.execute(text(
        "ALTER TABLE date_spots ADD COLUMN IF NOT EXISTS category VARCHAR(60)"
    ))
    connection.execute(text(
        "ALTER TABLE date_spots ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0"
    ))
    connection.execute(text(
        "ALTER TABLE date_spots ADD COLUMN IF NOT EXISTS map_click_count INTEGER NOT NULL DEFAULT 0"
    ))
    connection.execute(text(
        "ALTER TABLE date_spots ADD COLUMN IF NOT EXISTS neighborhood VARCHAR(120)"
    ))
    connection.execute(text(
        "ALTER TABLE date_spots ADD COLUMN IF NOT EXISTS price VARCHAR(8)"
    ))
    connection.execute(text(
        "ALTER TABLE date_spots ADD COLUMN IF NOT EXISTS best_for VARCHAR(120)"
    ))
    connection.execute(text(
        "ALTER TABLE message ADD COLUMN IF NOT EXISTS date_spot_id INTEGER "
        "REFERENCES date_spots(id) ON DELETE SET NULL"
    ))
    # Existing messages are backfilled as already read (DEFAULT true), so the
    # new unread badges don't light up for old history; new messages then
    # default to unread.
    connection.execute(text(
        "ALTER TABLE message ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT true"
    ))
    connection.execute(text(
        "ALTER TABLE message ALTER COLUMN is_read SET DEFAULT false"
    ))
    # One-off data fix: before the neighborhood field existed, these Paris
    # neighborhoods were entered as cities, splitting Paris into three "cities"
    # in the filters. Idempotent - once moved, the WHERE matches nothing.
    connection.execute(text(
        "UPDATE date_spots SET city = 'Paris', neighborhood = 'Châtelet' "
        "WHERE city = 'Chatelet' AND country = 'France'"
    ))
    connection.execute(text(
        "UPDATE date_spots SET city = 'Paris', neighborhood = 'Cité Universitaire' "
        "WHERE city = 'Cite universitaire' AND country = 'France'"
    ))

# Indexes for the lookups every screen makes (user by username, a profile's
# photos, likes/matches/blocks of a profile, a conversation's messages).
# Without them each of those scans the whole table, which gets slower with
# every new member. Same names create_all gives the index=True columns in
# models.py, so a fresh database doesn't end up with duplicates.
# One query finds the ones already there, so normal restarts cost a single
# round trip. Missing ones get a transaction each: if two workers start at
# once and race on the same index, only that statement fails and startup
# carries on.
HOT_PATH_INDEXES = [
    ("user", "username"),
    ("user", "email"),
    ("profile_photos", "profile_id"),
    ("language", "profile_id"),
    ("learning_language", "profile_id"),
    ("profile_like", "liked_profile_id"),
    ("match", "profile1_id"),
    ("match", "profile2_id"),
    ("message", "conversation_id"),
    ("profile_block", "blocked_profile_id"),
]
with engine.connect() as connection:
    existing_indexes = set(connection.execute(text(
        "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
    )).scalars())
for table, column in HOT_PATH_INDEXES:
    index_name = f"ix_{table}_{column}"
    if index_name in existing_indexes:
        continue
    try:
        with engine.begin() as connection:
            connection.execute(text(
                f'CREATE INDEX IF NOT EXISTS {index_name} ON "{table}" ({column})'
            ))
    except Exception as exc:
        print(f"Index {index_name} not created this time: {exc}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)