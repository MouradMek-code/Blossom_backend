from sqlalchemy import  ForeignKey, DateTime,Column, Integer, String, Text, Boolean,Date,UniqueConstraint
from .database import Base
from sqlalchemy.orm import relationship
from datetime import datetime


class DbUser(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True,index=True)
    username = Column(String)
    email = Column(String)
    password = Column(String)
    phone_number = Column(String)
    date_of_birth = Column(Date)
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    posts = relationship("DbPost",back_populates="user")
    profile=relationship("DbProfile",back_populates="user",
    uselist=False)

class DbPost(Base):
    __tablename__ = "post"
    id = Column(Integer, primary_key=True,index=True)
    caption = Column(String)
    image_type = Column(String)
    timestamp = Column(DateTime)
    user_id=Column(Integer,ForeignKey("user.id"))
    user=relationship("DbUser",back_populates="posts")
    comments = relationship("DbComment",back_populates="post")



class DbComment(Base):
    __tablename__ = "comment"
    id = Column(Integer, primary_key=True,index=True)
    content = Column(String)
    username=Column(String)
    timestamp = Column(DateTime)
    post_id = Column(Integer,ForeignKey("post.id"))
    post = relationship("DbPost",back_populates="comments")


class DbLanguage(Base):
    __tablename__ = "language"
    id = Column(Integer, primary_key=True,index=True)
    language_name = Column(String)
    profile_id = Column(Integer, ForeignKey("profiles.id"))
    profile = relationship("DbProfile",back_populates="languages")


class DbProfile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Basic Information

    first_name = Column(String(100), nullable=False)
    bio = Column(Text)

    age = Column(String(50))
    gender = Column(String(50))
    sexual_orientation = Column(String(50))




    # Main Profile Picture


    # Physical Attributes
    height_cm = Column(String(50))

    # Professional
    occupation = Column(String(255))
    education = Column(String(255))

    # Lifestyle
    smoking = Column(String(50))
    drinking = Column(String(50))
    exercise_frequency = Column(String(100))

    has_pets = Column(String(50))

    # Relationship
    relationship_goal = Column(String(100))
    has_children = Column(String(50))
    wants_children = Column(String(50))
    first_date_preference = Column(String(100))
    past_relationships_count = Column(String(50))
    last_breakup_reason = Column(String(100))

    # Personality
    personality_type = Column(String(50))
    city = Column(String(50))
    country = Column(String(50))



    created_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("user.id"), unique=True)
    # Relationships
    user = relationship("DbUser", back_populates="profile")
    languages=relationship("DbLanguage",back_populates="profile")
    photos = relationship(
        "DbProfilePhoto",
        back_populates="profile",
        cascade="all, delete-orphan"
    )
    messages = relationship(
        "DbMessage",
        back_populates="sender")

class DbProfilePhoto(Base):
        __tablename__ = "profile_photos"

        id = Column(Integer, primary_key=True, index=True)



        image_url = Column(String(500), nullable=False)
        public_id = Column(String(255), nullable=True)
        profile_id = Column(
            Integer,
            ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False
        )
        profile = relationship(
            "DbProfile",
            back_populates="photos"
        )




class DbProfileLike(Base):
    __tablename__ = "profile_like"

    id = Column(Integer, primary_key=True, index=True)

    liker_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False
    )

    liked_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    seen = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false"
    )

    __table_args__ = (
        UniqueConstraint(
            "liker_profile_id",
            "liked_profile_id",
            name="uq_profile_like"
        ),
    )

    liker = relationship(
        "DbProfile",
        foreign_keys=[liker_profile_id]
    )

    liked = relationship(
        "DbProfile",
        foreign_keys=[liked_profile_id]
    )

class DbMatch(Base):
        __tablename__ = "match"

        id = Column(Integer, primary_key=True, index=True)

        profile1_id = Column(
            Integer,
            ForeignKey("profiles.id"),
            nullable=False
        )

        profile2_id = Column(
            Integer,
            ForeignKey("profiles.id"),
            nullable=False
        )

        matched_at = Column(
            DateTime,
            default=datetime.utcnow
        )

        seen_by_profile1 = Column(
            Boolean,
            nullable=False,
            default=False,
            server_default="false"
        )

        seen_by_profile2 = Column(
            Boolean,
            nullable=False,
            default=False,
            server_default="false"
        )

        conversation = relationship(
            "DbConversation",
            back_populates="match",
            uselist=False
        )

class DbConversation(Base):
    __tablename__ = "conversation"

    id = Column(Integer, primary_key=True, index=True)

    match_id = Column(
        Integer,
        ForeignKey("match.id"),
        unique=True,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    match = relationship(
        "DbMatch",
        back_populates="conversation"
    )

    messages = relationship(
        "DbMessage",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )

class DbMessage(Base):
    __tablename__ = "message"

    id = Column(Integer, primary_key=True)

    conversation_id = Column(
        Integer,
        ForeignKey("conversation.id"),
        nullable=False
    )

    sender_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False
    )

    content = Column(
        String,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    conversation = relationship(
        "DbConversation",
        back_populates="messages"
    )
    sender = relationship(
        "DbProfile",
        back_populates="messages"
    )



class OTP(Base):
        __tablename__ = "otps"

        id = Column(Integer, primary_key=True)
        phone_number = Column(String, index=True)
        email = Column(String)
        code = Column(String)
        expires_at = Column(DateTime)


class DbBlock(Base):
    __tablename__ = "profile_block"

    id = Column(Integer, primary_key=True, index=True)

    blocker_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False
    )

    blocked_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "blocker_profile_id",
            "blocked_profile_id",
            name="uq_profile_block"
        ),
    )


class DbReport(Base):
    __tablename__ = "profile_report"

    id = Column(Integer, primary_key=True, index=True)

    reporter_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False
    )

    reported_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False
    )

    reason = Column(Text, nullable=False)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )