from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from datetime import datetime, timedelta ,timezone
from models.schema import LoginRequest, LoginResponse
from utils.password import verify_password

from models.user     import User
from models.schema  import (
    Step1AccountCreate, Step1Response,
    Step2OTPVerify,     Step2Response,
    Step3StoreSetup,    Step3Response,
    Step4PlanSelect,    Step4Response,
    ResendOTPRequest,   ResendOTPResponse,
)
from utils.password    import hash_password
from utils.jwt_handler import create_access_token
from utils.otp         import generate_otp, otp_expiry, mask_phone, send_otp_sms


# ══════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════

def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found"
        )
    return user


# ══════════════════════════════════════════════════════════════
# STEP 1 — Create account
# ══════════════════════════════════════════════════════════════

def register_step1(db: Session, data: Step1AccountCreate) -> Step1Response:
    """
    1. Check email & phone uniqueness
    2. Hash password
    3. Save user with is_phone_verified=False
    4. Generate OTP, save it, send via SMS
    """

    # ── Duplicate email check ─────────────────────────────────────────────────
    existing_email = db.query(User).filter(User.email == data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please log in."
        )

    # ── Duplicate phone check ─────────────────────────────────────────────────
    existing_phone = db.query(User).filter(User.phone == data.phone).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This phone number is already registered. Please log in."
        )

    # ── Create user ───────────────────────────────────────────────────────────
    otp        = generate_otp()
    otp_expiry_time = otp_expiry(minutes=10)

    new_user = User(
        first_name    = data.first_name.strip(),
        last_name     = data.last_name.strip(),
        email         = data.email.lower().strip(),
        phone         = data.phone,
        password_hash = hash_password(data.password),
        otp_code      = otp,
        otp_expires_at= otp_expiry_time,
        is_phone_verified = False,
        plan          = "growth",     # default plan until step 4
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration failed due to a conflict. Please try again."
        )

    # ── Send OTP ──────────────────────────────────────────────────────────────
    send_otp_sms(new_user.phone, otp)

    return Step1Response(
        message     = "Account created. OTP sent to your phone.",
        user_id     = new_user.id,
        email       = new_user.email,
        otp_sent_to = mask_phone(new_user.phone)
    )


# ══════════════════════════════════════════════════════════════
# STEP 2 — Verify OTP
# ══════════════════════════════════════════════════════════════

def register_step2(db: Session, data: Step2OTPVerify) -> Step2Response:
    """
    1. Find user
    2. Check OTP matches and hasn't expired
    3. Mark phone as verified, clear OTP
    """
    user = _get_user_or_404(db, data.user_id)

    # ── Already verified? ─────────────────────────────────────────────────────
    if user.is_phone_verified:
        return Step2Response(
            message           = "Phone already verified. Continue to next step.",
            user_id           = user.id,
            is_phone_verified = True
        )

    # ── OTP exists? ───────────────────────────────────────────────────────────
    if not user.otp_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found. Please request a new OTP."
        )

    # ── OTP expired? ──────────────────────────────────────────────────────────
    if user.otp_expires_at and datetime.now(timezone.utc) > user.otp_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one."
        )

    # ── OTP mismatch? ─────────────────────────────────────────────────────────
    if user.otp_code != data.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP. Please check and try again."
        )

    # ── Verify and clear OTP ──────────────────────────────────────────────────
    user.is_phone_verified = True
    user.otp_code          = None
    user.otp_expires_at    = None
    db.commit()
    db.refresh(user)

    return Step2Response(
        message           = "Phone verified successfully.",
        user_id           = user.id,
        is_phone_verified = True
    )


# ══════════════════════════════════════════════════════════════
# STEP 3 — Store setup
# ══════════════════════════════════════════════════════════════

def register_step3(db: Session, data: Step3StoreSetup) -> Step3Response:
    """
    Save store details — name, city, state, billing software, size
    """
    user = _get_user_or_404(db, data.user_id)

    # ── Phone must be verified before proceeding ──────────────────────────────
    if not user.is_phone_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your phone number before setting up your store."
        )

    user.store_name       = data.store_name.strip()
    user.store_city       = data.store_city.strip()
    user.store_state      = data.store_state
    user.billing_software = data.billing_software
    user.monthly_revenue  = data.monthly_revenue
    user.store_count      = data.store_count

    db.commit()
    db.refresh(user)

    return Step3Response(
        message    = "Store details saved.",
        user_id    = user.id,
        store_name = user.store_name
    )


# ══════════════════════════════════════════════════════════════
# STEP 4 — Plan selection + issue JWT
# ══════════════════════════════════════════════════════════════

def register_step4(db: Session, data: Step4PlanSelect) -> Step4Response:
    user = _get_user_or_404(db, data.user_id)

    if not user.store_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please complete store setup (step 3) before selecting a plan."
        )

    # ── Save plan and trial ───────────────────────────────────────────────────
    PLAN_CONFIG = {
        "starter":  {"price": 0,   "trial_days": 0,  "label": "Starter (Free)"},
        "silver":   {"price": 499, "trial_days": 30, "label": "Silver"},
        "platinum": {"price": 999, "trial_days": 30, "label": "Platinum"},
    }

    user.plan = data.plan

    # Starter is free forever — no trial needed
    if data.plan == "starter":
        user.trial_ends_at = None
    else:
        user.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=30)

    db.commit()
    db.refresh(user)

    # ── Issue JWT ─────────────────────────────────────────────────────────────
    token = create_access_token(data={
        "sub":   str(user.id),
        "email": user.email,
        "plan":  user.plan,
        "store": user.store_name
    })

    return Step4Response(
        message       = "Registration complete! Welcome to RetailPulse 🎉",
        user_id       = user.id,
        plan          = user.plan,
        trial_ends_at = user.trial_ends_at,
        access_token  = token,
        token_type    = "bearer"
    )


# ══════════════════════════════════════════════════════════════
# RESEND OTP
# ══════════════════════════════════════════════════════════════

def resend_otp(db: Session, data: ResendOTPRequest) -> ResendOTPResponse:
    """Generate a fresh OTP and re-send it. Rate limiting should be added in production."""
    user = _get_user_or_404(db, data.user_id)

    if user.is_phone_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone is already verified."
        )

    otp                 = generate_otp()
    user.otp_code       = otp
    user.otp_expires_at = otp_expiry(minutes=10)

    db.commit()
    send_otp_sms(user.phone, otp)

    return ResendOTPResponse(
        message     = "New OTP sent.",
        otp_sent_to = mask_phone(user.phone)
    )
# ══════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════

def login_user(db: Session, data: LoginRequest) -> LoginResponse:
    # ── Find user by email ────────────────────────────────────
    user = db.query(User).filter(
        User.email == data.email.lower().strip()
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # ── Verify password ───────────────────────────────────────
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # ── Check account is active ───────────────────────────────
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact support."
        )

    # ── Issue JWT ─────────────────────────────────────────────
    token = create_access_token(data={
        "sub":   str(user.id),
        "email": user.email,
        "plan":  user.plan,
        "store": user.store_name
    })

    PLAN_LABELS = {
    "starter":  "Starter (Free)",
    "silver":   "Silver — ₹499/mo",
    "platinum": "Platinum — ₹999/mo",
}

    return LoginResponse(
       message       = f"Welcome back, {user.first_name}! 👋",
       user_id       = user.id,
       first_name    = user.first_name,
       email         = user.email,
       store_name    = user.store_name,
       plan          = user.plan,
       plan_label    = PLAN_LABELS.get(user.plan, user.plan),
       trial_ends_at = user.trial_ends_at,
       access_token  = token,
       token_type    = "bearer"
)