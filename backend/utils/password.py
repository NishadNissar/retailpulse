import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a plain password using bcrypt. Store the result — never the original."""
    password_bytes = plain_password.encode("utf-8")
    salt   = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )
