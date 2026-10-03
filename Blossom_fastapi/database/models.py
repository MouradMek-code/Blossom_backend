from sqlalchemy import  ForeignKey, DateTime,Column, Integer, String, Text, Boolean,Date,UniqueConstraint
from .database import Base
from sqlalchemy.orm import relationship
from datetime import datetime


class DbUser(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True,index=True)
    # Indexed: every logged-in request looks the user up by username.
    username = Column(String, index=True)
    email = Column(String, index=True)
    password = Column(String)
    phone_number = Column(String)
    date_of_birth = Column(Date)
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    # Login sessions issued before this moment are no longer accepted (set on
    # password reset). Whole seconds, to line up with the token's "iat".
    sessions_valid_after = Column(DateTime, nullable=True)
    # When the account was created (UTC). Empty for accounts from before it
    # was recorded.
    created_at = Column(DateTime, nullable=True)
    # Profiles an admin made for a friend (see db_friend_profiles): who made it,
    # and the friend's confirmation. Until they confirm from the email link
    # (claimed_at), the profile stays out of Browse and nobody can log in.
    created_by = Column(Integer, nullable=True)
    claim_token = Column(String(64), nullable=True, unique=True, index=True)
    claim_sent_at = Column(DateTime, nullable=True)
    claim_language = Column(String(5), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
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
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    profile = relationship("DbProfile",back_populates="languages")


class DbLearningLanguage(Base):
    __tablename__ = "learning_language"
    id = Column(Integer, primary_key=True, index=True)
    language_name = Column(String)
    profile_id = Column(Integer, ForeignKey("profiles.id"), index=True)
    profile = relationship("DbProfile", back_populates="learning_languages")


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
    # What they're on Blossom for: "dating", "language" (language exchange, as
    # friends) or "both" - the default, and what existing profiles were given.
    connection_type = Column(String(20), nullable=False, default="both", server_default="both")
    # When sign-up was finished (2nd photo) - the admins are notified then, once.
    completed_at = Column(DateTime, nullable=True)

    # Personality
    personality_type = Column(String(50))
    city = Column(String(50))
    country = Column(String(50))



    created_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("user.id"), unique=True)
    # Relationships
    user = relationship("DbUser", back_populates="profile")
    languages=relationship("DbLanguage",back_populates="profile")
    learning_languages=relationship("DbLearningLanguage",back_populates="profile")
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
            nullable=False,
            index=True
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

    # liker_profile_id is covered by uq_profile_like (it's the leading column).
    liked_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False,
        index=True
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
            nullable=False,
            index=True
        )

        profile2_id = Column(
            Integer,
            ForeignKey("profiles.id"),
            nullable=False,
            index=True
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
        # Made by an event's organiser (see db_events.answer_interest).
        event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
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
        nullable=False,
        index=True
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

    # Set when the message is a "let's go here" date spot invite, so clients
    # can render the place as a card. content still carries a readable line,
    # which is what older app versions that don't know about invites show.
    date_spot_id = Column(
        Integer,
        ForeignKey("date_spots.id", ondelete="SET NULL"),
        nullable=True
    )
    date_spot = relationship("DbDateSpot")

    # When the other person said "I'm in" to this date spot invite.
    accepted_at = Column(DateTime, nullable=True)

    # Whether the recipient has opened the conversation since this arrived.
    # Chats are 1:1, so "recipient" is simply the participant who didn't send
    # it. Drives the unread badges on Messages.
    is_read = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false"
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

    # blocker_profile_id is covered by uq_profile_block (the leading column).
    blocked_profile_id = Column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False,
        index=True
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

class DbDateSpot(Base):
    """A place a user actually had a good date at, shared with the community."""

    __tablename__ = "date_spots"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(150), nullable=False)
    city = Column(String(120), nullable=False, index=True)
    country = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=False)

    image_url = Column(String(500), nullable=True)
    public_id = Column(String(255), nullable=True)

    # Optional Google Maps link so people can actually navigate there.
    map_url = Column(String(500), nullable=True)

    # Vibe tag, drawn from the same list as a profile's first_date_preference
    # so spots and people speak the same language.
    category = Column(String(60), nullable=True, index=True)

    # Optional area within the city ("Le Marais", "Châtelet"). Kept apart from
    # city on purpose: when people typed neighborhoods into the city field,
    # Paris got split into several fake "cities" in the filters.
    neighborhood = Column(String(120), nullable=True)

    # "Free", "€", "€€" or "€€€" - see PRICES in routers/date_spot.py.
    price = Column(String(8), nullable=True)

    # Comma-separated subset of BEST_FOR in routers/date_spot.py, e.g.
    # "First date,Casual". A plain string rather than an array type so it
    # stays portable and trivially filterable.
    best_for = Column(String(120), nullable=True)

    # Engagement counters, so a venue can be shown proof the listing is worth
    # something. view_count is curiosity; map_click_count is intent to
    # actually go, which is the number an owner really cares about.
    view_count = Column(Integer, default=0, nullable=False)
    map_click_count = Column(Integer, default=0, nullable=False)

    # Author. Kept nullable-on-delete so removing an account doesn't wipe
    # useful community content - the spot simply loses its attribution.
    profile_id = Column(
        Integer,
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True
    )
    profile = relationship("DbProfile")

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    # A member's place is a suggestion ("pending") until an admin approves it;
    # only "published" spots are listed. Admins' own spots are published at once.
    status = Column(String(12), nullable=False, default="published", server_default="published", index=True)
    # The member would love this place to offer a gift to couples - a lead
    # for the admins to contact the venue.
    wants_gift = Column(Boolean, nullable=False, default=False, server_default="false")


class DbPushToken(Base):
    """An Expo push token for one phone, so the backend can notify it (new
    message, match, like) while the app is closed."""

    __tablename__ = "push_token"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # One row per phone. If someone else logs in on the same phone, the token
    # moves to their account.
    token = Column(String(255), nullable=False, unique=True)

    # App language on that phone ("en", "fr", "zh", "ar"), so notification
    # texts can be sent in it.
    language = Column(String(8), nullable=True)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class DbVisit(Base):
    """One visit to the app or the website (admin dashboard).

    A visit is one sitting: coming back within 30 minutes of the last
    activity continues it rather than starting a new one. Members are "p:<profile
    id>" and are counted once per period on the dashboard however often they come;
    visitors without a profile are "d:<device id>" (a random id the app/browser
    keeps) and each of their visits counts. No IP address is stored."""
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, index=True)  # UTC
    last_seen_at = Column(DateTime, nullable=False)  # UTC
    visitor = Column(String(80), nullable=False, index=True)
    profile_id = Column(Integer, nullable=True, index=True)  # kept if the profile is deleted
    device_id = Column(String(64), nullable=True, index=True)
    platform = Column(String(10), nullable=True)  # "app" | "web"
    entry = Column(String(120), nullable=True)  # first screen / page
    language = Column(String(8), nullable=True)
    timezone = Column(String(64), nullable=True)


class DbVisitPage(Base):
    """A page (website) or screen (app) seen during a visit, in order - the
    dashboard's day view shows what each person did. Secret links (a friend's
    activation link, a venue's manager link) are stored masked."""
    __tablename__ = "visit_pages"
    id = Column(Integer, primary_key=True)
    visit_id = Column(Integer, ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True)
    at = Column(DateTime, nullable=False)  # UTC
    path = Column(String(120), nullable=False)


class DbAdminDevice(Base):
    """Phones and browsers an admin has used: never counted as visitors, even
    logged out."""
    __tablename__ = "analytics_admin_devices"
    device_id = Column(String(64), primary_key=True)


class DbAdminAlertToken(Base):
    """A phone an admin has used. It keeps getting the "new profile"
    notifications even after logging out or switching to another account on
    it - the push_token row follows whoever is logged in, this one stays."""
    __tablename__ = "admin_alert_token"
    token = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    language = Column(String(8), nullable=True)


class DbSpotOffer(Base):
    """A venue's promotion for Blossom couples ("-20% on the bill", "a free
    dessert"...), published by an admin on a date spot. A matched couple gets
    it when one invites the other to the spot and the other says yes - first
    come, first served when max_couples is set. The venue gives it, Blossom
    doesn't pay anything."""
    __tablename__ = "spot_offers"
    id = Column(Integer, primary_key=True)
    spot_id = Column(Integer, ForeignKey("date_spots.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    details = Column(Text, nullable=True)
    max_couples = Column(Integer, nullable=True)  # None = no limit
    ends_at = Column(DateTime, nullable=False)  # UTC: no new couples after this
    valid_hours = Column(Integer, nullable=False)  # how long a couple has to use it
    # Typed by the venue's staff on the couple's phone to mark it used.
    staff_code = Column(String(8), nullable=False)
    active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False)
    spot = relationship("DbDateSpot")


class DbSpotVoucher(Base):
    """A couple's promotion: one code for the two of them, to use before
    expires_at (then it's lost)."""
    __tablename__ = "spot_vouchers"
    __table_args__ = (UniqueConstraint("offer_id", "profile1_id", "profile2_id", name="uq_voucher_couple"),)
    id = Column(Integer, primary_key=True)
    offer_id = Column(Integer, ForeignKey("spot_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    # The couple, smaller profile id first. Plain ids: a voucher outlives an unmatch.
    profile1_id = Column(Integer, nullable=False, index=True)
    profile2_id = Column(Integer, nullable=False, index=True)
    message_id = Column(Integer, nullable=True)  # the invite it came from
    code = Column(String(12), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    # When both were reminded that the code is about to expire.
    reminded_at = Column(DateTime, nullable=True)
    offer = relationship("DbSpotOffer")


class DbVenue(Base):
    """A partner café/restaurant/bar, attached to its date spot. No Blossom
    account: the owner manages its promotions with a private link
    (manage_token), the staff check codes with staff_code - one staff code
    for all its promotions."""
    __tablename__ = "venues"
    id = Column(Integer, primary_key=True)
    spot_id = Column(Integer, ForeignKey("date_spots.id", ondelete="CASCADE"), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    contact_name = Column(String(120), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(40), nullable=True)
    language = Column(String(8), nullable=True)
    manage_token = Column(String(64), nullable=False, unique=True, index=True)
    staff_code = Column(String(8), nullable=False)
    created_at = Column(DateTime, nullable=False)
    spot = relationship("DbDateSpot")


class DbPartnerRequest(Base):
    """"Partner with Blossom": a venue asks to offer a promotion to couples -
    from the public form (a new venue) or its manager page (a new offer).
    An admin approves (spot, venue and promotion are created) or refuses."""
    __tablename__ = "partner_requests"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(12), nullable=False, default="pending", index=True)  # pending | approved | refused
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"), nullable=True)  # from a manager page
    venue_name = Column(String(150), nullable=False)
    map_url = Column(String(500), nullable=True)
    city = Column(String(120), nullable=True)
    country = Column(String(120), nullable=True)
    about = Column(Text, nullable=True)
    offer_title = Column(String(120), nullable=False)
    offer_details = Column(Text, nullable=True)
    max_couples = Column(Integer, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    valid_hours = Column(Integer, nullable=True)
    contact_name = Column(String(120), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(40), nullable=True)
    message = Column(Text, nullable=True)
    language = Column(String(8), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    refuse_reason = Column(Text, nullable=True)
    offer_id = Column(Integer, ForeignKey("spot_offers.id", ondelete="SET NULL"), nullable=True)
    # The date spot the venue picked on the form ("my place is already on
    # Blossom"): approving puts the promotion on it instead of a new spot.
    spot_id = Column(Integer, ForeignKey("date_spots.id", ondelete="SET NULL"), nullable=True)
    venue = relationship("DbVenue")
    spot = relationship("DbDateSpot")


class DbBusinessMessage(Base):
    """"Contact us" from blossom-date.com/business: a café, restaurant or any
    business writing to Blossom. Admins read them in Admin and answer by
    email."""
    __tablename__ = "business_messages"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    business = Column(String(150), nullable=True)
    email = Column(String(200), nullable=False)
    phone = Column(String(40), nullable=True)
    topic = Column(String(20), nullable=False)  # partnership | question | problem | other
    message = Column(Text, nullable=False)
    language = Column(String(8), nullable=True)
    handled = Column(Boolean, nullable=False, default=False, server_default="false")


class DbEvent(Base):
    """An event a member organises: a date idea (one person), a group outing
    or a language exchange - a set time, a public place. Members comment and
    say "I'm interested"; the organiser matches the people they'd like to
    meet (a normal match, see db_events). Date spots are places; events are
    moments, possibly at a date spot."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(12), nullable=False, default="group")  # date | group | language
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    starts_at = Column(DateTime, nullable=False, index=True)  # UTC
    ends_at = Column(DateTime, nullable=True)
    place_name = Column(String(150), nullable=False)
    map_url = Column(String(500), nullable=True)
    city = Column(String(120), nullable=False, index=True)
    country = Column(String(120), nullable=False)
    spot_id = Column(Integer, ForeignKey("date_spots.id", ondelete="SET NULL"), nullable=True, index=True)
    max_people = Column(Integer, nullable=True)  # group outings
    languages = Column(String(200), nullable=True)  # "French,Spanish" - language exchange
    women_only = Column(Boolean, nullable=False, default=False, server_default="false")
    comments_open = Column(Boolean, nullable=False, default=True, server_default="true")
    image_url = Column(String(500), nullable=True)
    public_id = Column(String(255), nullable=True)
    status = Column(String(12), nullable=False, default="active", server_default="active", index=True)  # active | cancelled | removed
    created_at = Column(DateTime, nullable=False)
    profile = relationship("DbProfile")
    spot = relationship("DbDateSpot")


class DbEventComment(Base):
    """A comment under an event (members only). A reply has parent_id. Deleted
    ones keep their place in the thread, without the text."""
    __tablename__ = "event_comments"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("event_comments.id", ondelete="CASCADE"), nullable=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    profile = relationship("DbProfile")


class DbEventInterest(Base):
    """"I'm interested" in an event - the member's yes. The organiser answers:
    matched (a normal match is made) or declined (never told)."""
    __tablename__ = "event_interests"
    __table_args__ = (UniqueConstraint("event_id", "profile_id", name="uq_event_interest"),)
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    status = Column(String(10), nullable=False, default="pending")  # pending | matched | declined
    answered_at = Column(DateTime, nullable=True)
    profile = relationship("DbProfile")


class DbEventReport(Base):
    """An event, or a comment under it, reported by a member - for the admins."""
    __tablename__ = "event_reports"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    comment_id = Column(Integer, ForeignKey("event_comments.id", ondelete="CASCADE"), nullable=True)
    reporter_profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    handled = Column(Boolean, nullable=False, default=False, server_default="false")
