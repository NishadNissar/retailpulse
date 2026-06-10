from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os

# ── Config ────────────────────────────────────────────────────────────────────
# In production: set SECRET_KEY as an environment variable — never hardcode it
SECRET_KEY      = os.getenv("SECRET_KEY", "retailpulse-super-secret-key-change-in-prod")
ALGORITHM       = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7   # 7 days


# ── Create token ──────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT token.
    data should include {"sub": str(user_id), "email": email}
    """
    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta if expires_delta
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ── Verify token ──────────────────────────────────────────────────────────────
def verify_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT.
    Returns the payload dict on success, None on failure.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ── Extract user_id from token ────────────────────────────────────────────────
def get_user_id_from_token(token: str) -> Optional[int]:
    payload = verify_token(token)
    if payload is None:
        return None
    sub = payload.get("sub")
    return int(sub) if sub else None
