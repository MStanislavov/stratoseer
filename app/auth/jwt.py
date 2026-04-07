"""JWT token creation and decoding for authentication flows."""

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: str, email: str, role: str) -> str:
    """Create a short-lived access token for API authentication.

    Args:
        user_id: Unique identifier of the user.
        email: User's email address, included in the token payload.
        role: User's role (e.g., "admin", "user").

    Returns:
        An encoded JWT access token string.
    """
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token for obtaining new access tokens.

    Args:
        user_id: Unique identifier of the user.

    Returns:
        An encoded JWT refresh token string.
    """
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expiry_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_email_verify_token(user_id: str) -> str:
    """Create a token for email address verification, valid for 24 hours.

    Args:
        user_id: Unique identifier of the user.

    Returns:
        An encoded JWT email verification token string.
    """
    payload = {
        "sub": user_id,
        "type": "email_verify",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_password_reset_token(user_id: str) -> str:
    """Create a token for password reset, valid for 1 hour.

    Args:
        user_id: Unique identifier of the user.

    Returns:
        An encoded JWT password reset token string.
    """
    payload = {
        "sub": user_id,
        "type": "password_reset",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on invalid/expired."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
