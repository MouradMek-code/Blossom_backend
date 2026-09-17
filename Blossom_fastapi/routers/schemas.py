from typing import List, Optional
from pydantic_extra_types.phone_numbers import PhoneNumber
from pydantic import BaseModel,EmailStr, Field, field_validator
from datetime import datetime, date

MIN_SIGNUP_AGE = 18

class UserBase(BaseModel):
    username: str
    email: EmailStr | None = Field(default=None)
    password: str = Field(min_length=8, max_length=100)
    phone_number: PhoneNumber
    date_of_birth: date

    @field_validator("date_of_birth")
    @classmethod
    def must_be_adult(cls, value: date) -> date:
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < MIN_SIGNUP_AGE:
            raise ValueError(f"You must be at least {MIN_SIGNUP_AGE} years old to sign up")
        return value

class User(BaseModel):
    username:str
    email:str
    class Config:
        orm_mode = True

class UserDisplay(BaseModel):
    username: str
    email: str
    access_token:str
    phone_number:str
    class Config:
        orm_mode = True

class PostBase(BaseModel):
    image_url: str
    image_type:str
    caption: str

class PostDisplay(BaseModel):
    id:int
    image_url:str
    image_type:str
    caption:str
    timestamp:datetime
    comments:List[Comment]
    user:User
    class Config:
        orm_mode = True

class UserAuth(BaseModel):
    id:int
    username:str
    email:str

class CommentBase(BaseModel):
    content:str
    post_id:int

class CommentDisplay(BaseModel):
    id:int
    username:str
    content:str
    post:PostDisplay
    timestamp:datetime
    class Config:
        orm_mode = True

class Comment(BaseModel):
    username:str
    content:str
    timestamp:datetime
    post_id:int
    class Config:
        orm_mode = True
class Post(BaseModel):
    id:int
    image_url:str
    caption:str
    image_type:str
    timestamp:datetime

class Profile(BaseModel):
    first_name: str

    bio:str

    age: str

    gender: str
    sexual_orientation: str

    city:Optional[str] = None
    country: Optional[str] = None


    languages: List[ProfileLanguage]



    height_cm: str

    occupation: str
    education: str

    smoking: str
    drinking: str
    exercise_frequency: str

    has_pets: str

    relationship_goal: str

    has_children: str
    wants_children: str

    personality_type: str



    photos: List[ProfilePhotoDisplay]

    created_at: datetime

class ProfilePhotoBase(BaseModel):
    image_url: str

class ProfilePhotoDisplay(BaseModel):
    id: int
    image_url: str
    profile: ProfileDisplayforPhoto

    class Config:
        orm_mode = True


class ProfilePhotoLean(BaseModel):
    """A photo inside a profile: just what the apps show."""
    id: int
    image_url: str

    class Config:
        orm_mode = True


class ProfileBase(BaseModel):
    bio: Optional[str] = None

    age: str = None

    gender: Optional[str] = None
    sexual_orientation: Optional[str] = None
    city:Optional[str] = None
    country: Optional[str] = None





    # Physical
    height_cm: Optional[str] = None

    # Professional
    occupation: Optional[str] = None
    education: Optional[str] = None

    # Lifestyle
    smoking: Optional[str] = None
    drinking: Optional[str] = None
    exercise_frequency: Optional[str] = None

    has_pets: Optional[str] = None

    # Relationship
    relationship_goal: Optional[str] = None
    first_date_preference: Optional[str] = None
    past_relationships_count: Optional[str] = None
    last_breakup_reason: Optional[str] = None


    has_children: Optional[str] = None
    wants_children: Optional[str] = None

    # Personality
    personality_type: Optional[str] = None



class ProfileBaseLanguage(BaseModel):
    language_name: str

class ProfileLanguageDisplay(BaseModel):
    profile_id: int
    language_name: str
    profile:ProfileDisplay
    class Config:
        orm_mode = True

class ProfileLanguage(BaseModel):
    language_name: str


class ProfileLearningLanguage(BaseModel):
    language_name: str


class ProfileLearningLanguageDisplay(BaseModel):
    profile_id: int
    language_name: str
    profile: ProfileDisplay

    class Config:
        orm_mode = True


class ProfileDisplay(BaseModel):
    id: int

    first_name: str

    bio: Optional[str]

    age: Optional[str]

    gender: Optional[str]
    sexual_orientation: Optional[str]

    city:Optional[str] = None
    country: Optional[str] = None

    languages: List[ProfileLanguage]
    learning_languages: List[ProfileLearningLanguage] = []



    height_cm: Optional[str]

    occupation: Optional[str]
    education: Optional[str]

    smoking: Optional[str]
    drinking: Optional[str]
    exercise_frequency: Optional[str]

    has_pets: str

    relationship_goal: Optional[str]
    first_date_preference: Optional[str] = None
    past_relationships_count: Optional[str] = None
    last_breakup_reason: Optional[str] = None

    has_children: str
    wants_children: Optional[str]

    personality_type: Optional[str]



    # Just id + url. ProfilePhotoDisplay repeats the whole profile (bio
    # included) inside every photo, tripling the payload for nothing.
    photos: List[ProfilePhotoLean]

    created_at: datetime
    # No `user` here: it put every member's username and email into Browse /
    # Matches / Likes You responses (a privacy leak), and loading it cost one
    # extra database query per profile. No client uses it.
    class Config:
        orm_mode = True

class ProfileDisplayforPhoto(BaseModel):
    id: int

    first_name: str

    bio: Optional[str]

    age: Optional[str]
    city:Optional[str] = None
    country: Optional[str] = None
    gender: Optional[str]
    sexual_orientation: Optional[str]



    languages: List[ProfileLanguage]
    learning_languages: List[ProfileLearningLanguage] = []



    height_cm: Optional[str]

    occupation: Optional[str]
    education: Optional[str]

    smoking: Optional[str]
    drinking: Optional[str]
    exercise_frequency: Optional[str]

    has_pets: str

    relationship_goal: Optional[str]
    first_date_preference: Optional[str] = None
    past_relationships_count: Optional[str] = None
    last_breakup_reason: Optional[str] = None

    has_children: str
    wants_children: Optional[str]

    personality_type: Optional[str]



    photos: List[ProfilePhotoDisplayWithoutProfile]

    created_at: datetime
    user: User
    class Config:
        orm_mode = True

class ProfilePhotoDisplayWithoutProfile(BaseModel):
    profile_id: int
    image_url: str


    class Config:
        orm_mode = True


class ProfileLikeBase(BaseModel):
    liked_user_id: int

class ProfileLikeDisplay(BaseModel):
    id: int
    liker_profile_id: int
    liked_profile_id: int
    created_at: datetime

    class Config:
        orm_mode = True


class MatchDisplay(BaseModel):
    id: int
    user1_id: int
    user2_id: int
    matched_at: datetime

    class Config:
        orm_mode = True

class MessageCreate(BaseModel):
    content: str

class DateSpotSummary(BaseModel):
    """The slice of a date spot a chat invite card needs."""
    id: int
    name: str
    city: str
    country: str
    neighborhood: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    price: Optional[str] = None

    class Config:
        orm_mode = True

class MessageDisplay(BaseModel):
    id: int
    sender_profile_id: int
    content: str
    created_at: datetime
    # Present on "let's go here" invites; None for ordinary messages, or if
    # the spot has since been deleted.
    date_spot_id: Optional[int] = None
    date_spot: Optional[DateSpotSummary] = None

    class Config:
        orm_mode = True
class ConversationDisplay(BaseModel):
    id: int
    messages: list[MessageDisplay]

    class Config:
        orm_mode = True

class VerifyOTPRequest(BaseModel):
    phone_number: PhoneNumber
    email:str
    otp: str

class BioUpdate(BaseModel):
    bio: str

class ReportCreate(BaseModel):
    reported_profile_id: int
    reason: str = Field(min_length=1, max_length=1000)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=8, max_length=100)



class DateSpotAuthor(BaseModel):
    # id lets clients tell whether the viewer wrote the spot (to offer Edit).
    id: Optional[int] = None
    first_name: Optional[str] = None

    class Config:
        orm_mode = True


class DateSpotInvite(BaseModel):
    """Send a spot to a match as a chat message."""
    profile_id: int
    # Written in the sender's app language; the server falls back to English.
    content: Optional[str] = Field(default=None, max_length=500)


class PushTokenRegister(BaseModel):
    """A phone's Expo push token, sent by the app after login."""
    token: str = Field(min_length=10, max_length=255)
    # App language, so notifications arrive in it.
    language: Optional[str] = Field(default=None, max_length=8)


class PushTokenUnregister(BaseModel):
    token: str = Field(min_length=10, max_length=255)


class DateSpotInviteResult(BaseModel):
    conversation_id: int
    message: MessageDisplay


class DateSpotStatsUpdate(BaseModel):
    """Admin-set counters, e.g. to seed a venue's numbers."""
    view_count: Optional[int] = Field(default=None, ge=0)
    map_click_count: Optional[int] = Field(default=None, ge=0)


class DateSpotUpdate(BaseModel):
    """Partial edit: only the fields actually sent are applied (see
    model_fields_set in the router), so omitting a field leaves it alone."""
    name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    neighborhood: Optional[str] = None
    description: Optional[str] = None
    map_url: Optional[str] = None
    category: Optional[str] = None
    price: Optional[str] = None
    best_for: Optional[List[str]] = None


class DateSpotDisplay(BaseModel):
    id: int
    name: str
    city: str
    country: str
    description: str
    image_url: Optional[str] = None
    map_url: Optional[str] = None
    category: Optional[str] = None
    neighborhood: Optional[str] = None
    price: Optional[str] = None
    best_for: List[str] = []
    view_count: int = 0
    map_click_count: int = 0
    created_at: Optional[datetime] = None
    profile: Optional[DateSpotAuthor] = None

    # Stored as "First date,Casual"; clients get a proper list.
    @field_validator("best_for", mode="before")
    @classmethod
    def split_best_for(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    class Config:
        orm_mode = True
