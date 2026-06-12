import random
import string
from datetime import datetime, timedelta


def generate_otp(length: int = 6) -> str:
    """Generate a random numeric OTP of given length."""
    return "".join(random.choices(string.digits, k=length))


def otp_expiry(minutes: int = 10) -> datetime:
    """Return a datetime that is `minutes` from now — OTP expires then."""
    return datetime.now() + timedelta(minutes=minutes)


def mask_phone(phone: str) -> str:
    """
    Mask phone for display in API response.
    '+919876543210' → '+91******3210'
    """
    if len(phone) >= 6:
        visible_start = phone[:3]   # e.g. +91
        visible_end   = phone[-4:]  # last 4 digits
        masked_middle = "*" * (len(phone) - 7)
        return f"{visible_start}{masked_middle}{visible_end}"
    return "****"


# ── In production: send OTP via SMS API (Twilio, MSG91, Fast2SMS etc.) ────────
# For now: prints to console (development mode)
def send_otp_sms(phone: str, otp: str) -> bool:
    """
    Send OTP via SMS.
    Replace the print() below with your SMS provider API call.

    Example with MSG91 (popular in India):
        import requests
        url = "https://api.msg91.com/api/v5/otp"
        payload = {"mobile": phone, "otp": otp, "authkey": MSG91_AUTH_KEY}
        response = requests.post(url, json=payload)
        return response.status_code == 200
    """
    print(f"\n{'='*40}")
    print(f"📱 OTP for {phone}: {otp}")
    print(f"   Expires in 10 minutes")
    print(f"{'='*40}\n")
    return True
