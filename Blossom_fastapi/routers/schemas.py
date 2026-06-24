from typing import List, Optional
from pydantic_extra_types.phone_numbers import PhoneNumber
from pydantic import BaseModel,EmailStr, Field
from datetime import datetime
class UserBase(BaseModel):
    username: str
    email: EmailStr | None = Field(default=None)
    password: str = Field(min_length=8, max_length=100)
    phone_number: PhoneNumber

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



    height_cm: Optional[str]

    occupation: Optional[str]
    education: Optional[str]

    smoking: Optional[str]
    drinking: Optional[str]
    exercise_frequency: Optional[str]

    has_pets: str

    relationship_goal: Optional[str]

    has_children: str
    wants_children: Optional[str]

    personality_type: Optional[str]



    photos: List[ProfilePhotoDisplay]

    created_at: datetime
    user: User
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



    height_cm: Optional[str]

    occupation: Optional[str]
    education: Optional[str]

    smoking: Optional[str]
    drinking: Optional[str]
    exercise_frequency: Optional[str]

    has_pets: str

    relationship_goal: Optional[str]

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

class MessageDisplay(BaseModel):
    id: int
    sender_profile_id: int
    content: str
    created_at: datetime

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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=8, max_length=100)

