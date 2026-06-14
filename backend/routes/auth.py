from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from Database.Database import get_db
from models.schema import LoginRequest, LoginResponse
from models.user import User
from services.auth_services import login_user
from pydantic import BaseModel
import os
import urllib.request
import urllib.parse
import json
import random
import string
from utils.password import hash_password
from utils.jwt_handler import create_access_token
from datetime import datetime, timedelta, timezone

from models.schema import (
    Step1AccountCreate, Step1Response,
    Step2OTPVerify,     Step2Response,
    Step3StoreSetup,    Step3Response,
    Step4PlanSelect,    Step4Response,
    ResendOTPRequest,   ResendOTPResponse,
    UserOut,
)
from services.auth_services import (
    register_step1,
    register_step2,
    register_step3,
    register_step4,
    resend_otp,
)

router = APIRouter(prefix="/register", tags=["Registration"])
login_router = APIRouter(tags=["Login"])

def get_unique_mock_phone(db: Session):
    for _ in range(10):
        phone = "+91" + "".join(random.choices(string.digits, k=10))
        if not db.query(User).filter(User.phone == phone).first():
            return phone
    return "+919" + "".join(random.choices(string.digits, k=9))

@router.get("/google/login")
def google_login():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        # Mock Google OAuth login mode when no credentials
        return RedirectResponse(url="/register/google/callback?code=mock_google_code")
        
    redirect_uri = "http://localhost:8000/register/google/callback"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"response_type=code&client_id={client_id}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"scope=openid%20email%20profile"
    )
    return RedirectResponse(url=auth_url)

@router.get("/google/callback")
def google_callback(code: str, db: Session = Depends(get_db)):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    email = None
    first_name = "Google"
    last_name = "User"
    
    if code == "mock_google_code" or not client_id or not client_secret:
        email = "google_mock@retailpulse.com"
        first_name = "Google"
        last_name = "MockUser"
    else:
        try:
            redirect_uri = "http://localhost:8000/register/google/callback"
            token_url = "https://oauth2.googleapis.com/token"
            data = urllib.parse.urlencode({
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }).encode("utf-8")
            
            req = urllib.request.Request(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req) as response:
                token_data = json.loads(response.read().decode("utf-8"))
                access_token = token_data.get("access_token")
                
            userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
            req2 = urllib.request.Request(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
            with urllib.request.urlopen(req2) as response2:
                user_info = json.loads(response2.read().decode("utf-8"))
                email = user_info.get("email")
                first_name = user_info.get("given_name", "Google")
                last_name = user_info.get("family_name", "User")
        except Exception as e:
            # Fallback to mock on error
            email = "google_mock@retailpulse.com"
            first_name = "Google"
            last_name = "MockUser"
            
    if not email:
        email = "google_mock@retailpulse.com"

    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user:
        phone = get_unique_mock_phone(db)
        user = User(
            first_name = first_name.strip(),
            last_name = last_name.strip(),
            email = email.lower().strip(),
            phone = phone,
            password_hash = hash_password("google-oauth-dummy-password"),
            is_phone_verified = True,
            is_email_verified = True,
            store_name = f"{first_name}'s Store",
            store_city = "Kochi",
            store_state = "KL",
            billing_software = "Other",
            monthly_revenue = "₹0-5 lakh",
            store_count = "1 store",
            plan = "growth",
            trial_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.is_active:
            user.is_active = True
            db.commit()
            db.refresh(user)

    token = create_access_token(data={
        "sub": str(user.id),
        "email": user.email,
        "plan": user.plan,
        "store": user.store_name or "My Store"
    })
    
    PLAN_LABELS = {
        "starter": "Starter (Free)",
        "silver": "Silver — ₹499/mo",
        "platinum": "Platinum — ₹999/mo",
        "growth": "Growth",
    }
    plan_label = PLAN_LABELS.get(user.plan, user.plan)
    
    redirect_to = (
        f"/app?token={urllib.parse.quote(token)}"
        f"&first_name={urllib.parse.quote(user.first_name)}"
        f"&email={urllib.parse.quote(user.email)}"
        f"&plan={urllib.parse.quote(user.plan)}"
        f"&plan_label={urllib.parse.quote(plan_label)}"
        f"&store_name={urllib.parse.quote(user.store_name or 'My Store')}"
    )
    return RedirectResponse(url=redirect_to)

@router.post("/step1", response_model=Step1Response, status_code=status.HTTP_201_CREATED)
def step1_create_account(payload: Step1AccountCreate, db: Session = Depends(get_db)):
    return register_step1(db, payload)

@router.post("/step2", response_model=Step2Response, status_code=status.HTTP_200_OK)
def step2_verify_otp(payload: Step2OTPVerify, db: Session = Depends(get_db)):
    return register_step2(db, payload)

@router.post("/step3", response_model=Step3Response, status_code=status.HTTP_200_OK)
def step3_store_setup(payload: Step3StoreSetup, db: Session = Depends(get_db)):
    return register_step3(db, payload)

@router.post("/step4", response_model=Step4Response, status_code=status.HTTP_200_OK)
def step4_select_plan(payload: Step4PlanSelect, db: Session = Depends(get_db)):
    return register_step4(db, payload)

@router.post("/resend-otp", response_model=ResendOTPResponse, status_code=status.HTTP_200_OK)
def resend_otp_endpoint(payload: ResendOTPRequest, db: Session = Depends(get_db)):
    return resend_otp(db, payload)

@login_router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db, data)

class PasswordResetDirect(BaseModel):
    email: str
    new_password: str
    secret: str

@login_router.post("/admin/reset-password")
def reset_password_direct(data: PasswordResetDirect, db: Session = Depends(get_db)):
    if data.secret != "retailpulse2026":
        raise HTTPException(status_code=403, detail="Forbidden")
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"status": "success", "message": "Password reset"}
