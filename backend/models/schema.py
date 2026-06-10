from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
import re


# ══════════════════════════════════════════════════════════════
# STEP 1 — Account details
# ══════════════════════════════════════════════════════════════

class Step1AccountCreate(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=100, example="Arun")
    last_name:  str = Field(..., min_length=1, max_length=100, example="Menon")
    email:      EmailStr = Field(..., example="arun@srilakshmimart.com")
    phone:      str = Field(..., example="+919876543210")
    password:   str = Field(..., min_length=8, max_length=128,
                            example="StrongPass@123")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not re.match(r"^(\+91)?[6-9]\d{9}$", cleaned):
            raise ValueError(
                "Enter a valid Indian phone number "
                "(10 digits starting with 6-9, optionally with +91)"
            )
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "first_name": "Arun",
                "last_name":  "Menon",
                "email":      "arun@srilakshmimart.com",
                "phone":      "+919876543210",
                "password":   "Secure@2025"
            }
        }
    }


class Step1Response(BaseModel):
    message: str
    user_id: int
    email:   str
    otp_sent_to: str


# ══════════════════════════════════════════════════════════════
# STEP 2 — OTP verification
# ══════════════════════════════════════════════════════════════

class Step2OTPVerify(BaseModel):
    user_id: int
    otp:     str = Field(..., min_length=6, max_length=6, example="482910")

    @field_validator("otp")
    @classmethod
    def otp_must_be_digits(cls, v):
        if not v.isdigit():
            raise ValueError("OTP must be 6 digits")
        return v

    model_config = {
        "json_schema_extra": {"example": {"user_id": 1, "otp": "123456"}}
    }


class Step2Response(BaseModel):
    message:           str
    user_id:           int
    is_phone_verified: bool


# ══════════════════════════════════════════════════════════════
# STEP 3 — Store setup
# ══════════════════════════════════════════════════════════════

class Step3StoreSetup(BaseModel):
    user_id:          int
    store_name:       str = Field(..., min_length=2, max_length=200)
    store_city:       str = Field(..., min_length=2, max_length=100)
    store_state:      str
    billing_software: str
    monthly_revenue:  str
    store_count:      str

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id":          1,
                "store_name":       "Sri Lakshmi Mart",
                "store_city":       "Thiruvananthapuram",
                "store_state":      "KL",
                "billing_software": "Marg ERP",
                "monthly_revenue":  "₹5–15 lakh",
                "store_count":      "1 store"
            }
        }
    }


class Step3Response(BaseModel):
    message:    str
    user_id:    int
    store_name: str


# ══════════════════════════════════════════════════════════════
# STEP 4 — Plan selection
# ══════════════════════════════════════════════════════════════

class Step4PlanSelect(BaseModel):
    user_id: int
    plan:    str = Field(..., example="growth")

    @field_validator("plan")
    @classmethod
    
    def plan_must_be_valid(cls, v):
     if v not in ("starter", "silver", "platinum"):
        raise ValueError("Plan must be one of: starter, silver, platinum")
     return v

    model_config = {
    "json_schema_extra": {"example": {"user_id": 1, "plan": "silver"}}
}


class Step4Response(BaseModel):
    message:       str
    user_id:       int
    plan:          str
    trial_ends_at: Optional[datetime]
    access_token:  str
    token_type:    str = "bearer"


# ══════════════════════════════════════════════════════════════
# RESEND OTP
# ══════════════════════════════════════════════════════════════

class ResendOTPRequest(BaseModel):
    user_id: int

    model_config = {
        "json_schema_extra": {"example": {"user_id": 1}}
    }


class ResendOTPResponse(BaseModel):
    message:     str
    otp_sent_to: str


# ══════════════════════════════════════════════════════════════
# FULL USER RESPONSE (safe — no password)
# ══════════════════════════════════════════════════════════════

class UserOut(BaseModel):
    id:                int
    first_name:        str
    last_name:         str
    email:             str
    phone:             str
    store_name:        Optional[str]
    store_city:        Optional[str]
    store_state:       Optional[str]
    billing_software:  Optional[str]
    monthly_revenue:   Optional[str]
    store_count:       Optional[str]
    plan:              str
    is_active:         bool
    is_phone_verified: bool
    is_email_verified: bool
    trial_ends_at:     Optional[datetime]
    created_at:        datetime

    model_config = {
        "from_attributes": True
    }
# ══════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email:    EmailStr = Field(..., example="arun@srilakshmimart.com")
    password: str = Field(..., example="Secure@2025")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email":    "arun@srilakshmimart.com",
                "password": "Secure@2025"
            }
        }
    }


class LoginResponse(BaseModel):
    message:       str
    user_id:       int
    first_name:    str
    email:         str
    store_name:    Optional[str]
    plan:          str
    plan_label:    str
    trial_ends_at: Optional[datetime]
    access_token:  str
    token_type:    str = "bearer"    
# --------------------------------------------------------------
# FORGOT / RESET PASSWORD
# --------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ForgotPasswordResponse(BaseModel):
    status: str
    message: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

class ResetPasswordResponse(BaseModel):
    status: str
    message: str

class AdminStatsResponse(BaseModel):
    status: str
    users: list[UserOut]
