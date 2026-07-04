import redis
from  fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import http.client
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import json
from vonage import Auth, Vonage
from vonage_messages import Sms
from routers.schemas import VerifyOTPRequest, ForgotPasswordRequest, ResetPasswordRequest
from database.models import DbUser
from datetime import datetime, timedelta
from database import db_user, db_profile
from database.database import get_db
from routers.schemas import UserDisplay, UserBase, UserAuth
from database.models import OTP
from methods import HashedPassword
from auth.oauth2 import get_current_user
from dotenv import load_dotenv
import os

load_dotenv()

INFOBIP_API_KEY = os.getenv("INFOBIP_API_KEY")
INFOBIP_BASE_URL = os.getenv("INFOBIP_BASE_URL")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
import random
router = APIRouter(
    tags=["user"],
    prefix="/user",
)
import re
@router.post('', response_model=UserDisplay)
async def create_user(request:UserBase,db:Session = Depends(get_db)):

    return db_user.create_user(db,request)
@router.post("/verify")
async def verify_user(request:UserBase,db:Session = Depends(get_db)):
    db_username = db.query(DbUser).filter(DbUser.username == request.username).first()
    if db_username:
        raise HTTPException(status_code=400, detail="User with this username already exists")
    db_email = db.query(DbUser).filter(DbUser.email == request.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    phone_number=request.phone_number
    otp = str(random.randint(100000, 999999))

    db_otp = OTP(
        phone_number=phone_number,
        code=otp,
        expires_at=datetime.now() + timedelta(minutes=10)
    )

    db.add(db_otp)
    db.commit()
    phone_number = str(phone_number)

    phone_number = phone_number.replace("tel:", "")
    phone_number = re.sub(r"[^\d+]", "", phone_number)
    result=await send_sms_vonage(phone_number, otp)

    if result.get("messages"):
        return {"messages": "sent","detail":result,"phone":phone_number}

    raise HTTPException(status_code=400, detail=result)


@router.get('/all', response_model=list[UserDisplay])
def get_all_users(db:Session = Depends(get_db)):
    return db_user.get_all_users(db)

@router.get('/{id}', response_model=UserDisplay)
def get_user_by_id(id:int,db:Session = Depends(get_db)):
    return db_user.get_user_by_id(db,id)

@router.delete('/me')
def delete_my_account(db: Session = Depends(get_db), current_user: UserAuth = Depends(get_current_user)):
    return db_profile.delete_account(db, current_user)

@router.delete('/all')
def delete_all_users(db:Session = Depends(get_db)):
    return db_user.delete_all_users(db)

@router.delete('/{id}')
def delete_user_by_id(id:int,db:Session = Depends(get_db)):
    return db_user.delete_user_by_id(db,id)


@router.post("/verify-phone")
async def verify_otp(request:VerifyOTPRequest,db:Session = Depends(get_db)):

    record = db.query(OTP).filter(
        OTP.phone_number == request.phone_number
    ).order_by(OTP.id.desc()).first()

    if not record:
        raise HTTPException(400, "OTP not found")

    if record.expires_at < datetime.utcnow():
        raise HTTPException(400, "OTP expired")

    if record.code != request.otp:
        raise HTTPException(400, "Invalid OTP")

    # delete after success
    db.query(OTP).delete()
    db.commit()
    return {"message": "Phone verified"}

async def send_sms(phone_number: str, otp: str):

    conn = http.client.HTTPSConnection(f"{INFOBIP_BASE_URL}")

    headers = {
        "Authorization": f"App {INFOBIP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


    payload = json.dumps({
        "messages": [
            {
                "destinations": [
                    {
                        "to": phone_number
                    }
                ],
                "sender": "ServiceSMS",
                "content": {
                    "text": f"BLOSSOM dating App,Your verification code is: {otp}"
                }
            }
        ]
    })
    conn.request("POST", "/sms/3/messages", payload, headers)
    res = conn.getresponse()

    data = res.read().decode("utf-8")

    return json.loads(data)

async def send_sms_vonage(phone_number: str, otp: str):
    client = Vonage(
        Auth(
            api_key="fc2f40f2",
            api_secret="8xh74e0vM6pIofw0",
        )
    )

    response = client.messages.send(
        Sms(to="33663376944", from_="Vonage APIs", text=f"BLOSSOM dating App,Your verification code is: {otp}")
    )

    return response



async def send_email_otp(email: str,phone_number:str, otp: str):

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = BREVO_API_KEY

    api = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    email_data = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={
            "name": "Blossom",
            "email": "mourad.meknioui@gmail.com"
        },
        subject="🌹 Your Blossom Dating App Verification Code",
        html_content=f"""
    <div style="background:#fff5f7;padding:30px 15px;font-family:Arial,sans-serif;">
        <div style="
            max-width:520px;
            margin:auto;
            background:#ffffff;
            border-radius:20px;
            padding:40px 30px;
            text-align:center;
            box-shadow:0 3px 15px rgba(0,0,0,0.08);
        ">

            <div style="font-size:50px;margin-bottom:10px;">
                🌸
            </div>

            <h1 style="
                color:#e91e63;
                margin:0;
                font-size:32px;
            ">
                Blossom Dating
            </h1>

            <p style="
                color:#666;
                font-size:16px;
                margin-top:20px;
                line-height:1.6;
            ">
                Welcome to Blossom Dating.
                Use the verification code below to verify your account.
            </p>

            <div style="
                display:inline-block;
                background:#fde7ef;
                color:#e91e63;
                padding:10px 18px;
                border-radius:999px;
                margin:10px 0 25px;
                font-size:14px;
                font-weight:bold;
            ">
                📱 {phone_number}
            </div>

            <div style="
                background:#e91e63;
                color:white;
                font-size:42px;
                font-weight:bold;
                letter-spacing:10px;
                padding:22px;
                border-radius:14px;
                margin:20px 0;
            ">
                {otp}
            </div>

            <p style="
                color:#666;
                font-size:15px;
            ">
                This code expires in
                <strong>10 minutes</strong>.
            </p>

            <div style="
                background:#fff0f4;
                border-radius:10px;
                padding:15px;
                margin-top:25px;
                color:#777;
                font-size:13px;
                line-height:1.5;
            ">
                🔒 Never share this code with anyone.
                Blossom support will never ask for your verification code.
            </div>

            <hr style="
                border:none;
                border-top:1px solid #eeeeee;
                margin:30px 0;
            ">

            <p style="
                color:#999;
                font-size:12px;
                line-height:1.6;
            ">
                If you did not request this verification code,
                you can safely ignore this email.
            </p>

            <p style="
                color:#e91e63;
                font-size:13px;
                margin-top:20px;
                font-weight:bold;
            ">
                Made with ❤️ by Blossom
            </p>

        </div>
    </div>
    """
    )

    try:
        response = api.send_transac_email(email_data)

        return {
            "success": True,
            "message_id": response.message_id,
            "message": "email sent"
        }

    except ApiException as e:
        return {
            "success": False,
            "error": str(e)
        }

async def send_password_reset_email(email: str, otp: str):
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = BREVO_API_KEY

    api = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    email_data = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={
            "name": "Blossom",
            "email": "mourad.meknioui@gmail.com"
        },
        subject="🌹 Reset your Blossom password",
        html_content=f"""
    <div style="background:#fff5f7;padding:30px 15px;font-family:Arial,sans-serif;">
        <div style="
            max-width:520px;
            margin:auto;
            background:#ffffff;
            border-radius:20px;
            padding:40px 30px;
            text-align:center;
            box-shadow:0 3px 15px rgba(0,0,0,0.08);
        ">

            <div style="font-size:50px;margin-bottom:10px;">
                🌸
            </div>

            <h1 style="
                color:#e91e63;
                margin:0;
                font-size:32px;
            ">
                Blossom Dating
            </h1>

            <p style="
                color:#666;
                font-size:16px;
                margin-top:20px;
                line-height:1.6;
            ">
                We received a request to reset your password.
                Use the code below to choose a new one.
            </p>

            <div style="
                background:#e91e63;
                color:white;
                font-size:42px;
                font-weight:bold;
                letter-spacing:10px;
                padding:22px;
                border-radius:14px;
                margin:20px 0;
            ">
                {otp}
            </div>

            <p style="
                color:#666;
                font-size:15px;
            ">
                This code expires in
                <strong>10 minutes</strong>.
            </p>

            <div style="
                background:#fff0f4;
                border-radius:10px;
                padding:15px;
                margin-top:25px;
                color:#777;
                font-size:13px;
                line-height:1.5;
            ">
                🔒 If you didn't request this, you can safely ignore this
                email - your password won't be changed.
            </div>

            <p style="
                color:#e91e63;
                font-size:13px;
                margin-top:20px;
                font-weight:bold;
            ">
                Made with ❤️ by Blossom
            </p>

        </div>
    </div>
    """
    )

    try:
        response = api.send_transac_email(email_data)
        return {
            "success": True,
            "message_id": response.message_id,
        }
    except ApiException as e:
        return {
            "success": False,
            "error": str(e)
        }

def require_admin(current_user: UserAuth = Depends(get_current_user)):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

@router.get("/admin/users")
def admin_get_all_users(db: Session = Depends(get_db), _: UserAuth = Depends(require_admin)):
    users = db.query(DbUser).order_by(DbUser.id.desc()).all()
    result = []
    for u in users:
        profile = u.profile
        result.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "date_of_birth": str(u.date_of_birth) if u.date_of_birth else None,
            "is_admin": u.is_admin,
            "profile": {
                "id": profile.id,
                "first_name": profile.first_name,
                "gender": profile.gender,
                "age": profile.age,
                "city": profile.city,
                "country": profile.country,
                "created_at": str(profile.created_at) if profile.created_at else None,
                "photo": profile.photos[0].image_url if profile.photos else None,
            } if profile else None,
        })
    return result

@router.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: int, db: Session = Depends(get_db), _: UserAuth = Depends(require_admin)):
    user = db.query(DbUser).filter(DbUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db_profile.delete_account(db, user)
    return {"detail": "User deleted"}

@router.post("/forgot_password")
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(DbUser).filter(DbUser.email == request.email).first()
    if not user:
        # Don't reveal whether the email is registered.
        return {"message": "If that email exists, a reset code has been sent."}

    otp = str(random.randint(100000, 999999))

    db_otp = OTP(
        phone_number=user.phone_number,
        email=request.email,
        code=otp,
        expires_at=datetime.now() + timedelta(minutes=10)
    )
    db.add(db_otp)
    db.commit()

    await send_password_reset_email(request.email, otp)

    return {"message": "If that email exists, a reset code has been sent."}

@router.post("/reset_password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    record = db.query(OTP).filter(
        OTP.email == request.email
    ).order_by(OTP.id.desc()).first()

    if not record:
        raise HTTPException(400, "Reset code not found")
    if record.expires_at < datetime.now():
        raise HTTPException(400, "Reset code expired")
    if record.code != request.otp:
        raise HTTPException(400, "Invalid reset code")

    user = db.query(DbUser).filter(DbUser.email == request.email).first()
    if not user:
        raise HTTPException(404, "User not found")

    user.password = HashedPassword.HashedPassword.hash_password(request.new_password)
    db.commit()

    db.query(OTP).filter(OTP.email == request.email).delete()
    db.commit()

    return {"message": "Password updated"}

@router.post("/send_email")
async def send_email_verification(request:UserBase,db:Session = Depends(get_db)):
    db_username = db.query(DbUser).filter(DbUser.username == request.username).first()
    if db_username:
        raise HTTPException(status_code=400, detail="User with this username already exists")
    db_email = db.query(DbUser).filter(DbUser.email == request.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    phone_number=request.phone_number
    email = request.email
    otp = str(random.randint(100000, 999999))
    phone_number = phone_number.replace("tel:", "")
    phone_number = re.sub(r"[^\d+]", "", phone_number)
    result=await send_email_otp(email,phone_number, otp)

    db_otp = OTP(
        phone_number=phone_number,
        email=email,
        code=otp,
        expires_at=datetime.now() + timedelta(minutes=10)
    )

    db.add(db_otp)
    db.commit()



    if "message_id" in result:
        return {"messages": "sent","detail":result,"email":email}

    raise HTTPException(status_code=400, detail=result)


@router.post("/resend_email")
async def resend_email_verification(email: str, phone_number: str, db: Session = Depends(get_db)):
    otp = str(random.randint(100000, 999999))
    clean_phone = re.sub(r'[^\d+]', '', phone_number.replace('tel:', ''))
    result = await send_email_otp(email, clean_phone, otp)
    db_otp = OTP(
        phone_number=clean_phone,
        email=email,
        code=otp,
        expires_at=datetime.now() + timedelta(minutes=10)
    )
    db.add(db_otp)
    db.commit()
    if 'message_id' in result:
        return {'messages': 'sent'}
    raise HTTPException(status_code=400, detail=result)

@router.post("/verify-email")
async def verify_otp_email(request:VerifyOTPRequest,db:Session = Depends(get_db)):

    record = db.query(OTP).filter(
        OTP.email == request.email
    ).order_by(OTP.id.desc()).first()

    if not record:
        raise HTTPException(400, "OTP not found")

    if record.expires_at < datetime.now():
        raise HTTPException(400, "OTP expired")

    if record.code != request.otp:
        raise HTTPException(400, "Invalid OTP")

    # delete after success
    db.query(OTP).delete()
    db.commit()
    return {"message": "Email verified"}

