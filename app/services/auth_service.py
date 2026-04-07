"""Auth business logic: register, login, refresh, logout, OAuth, verify, password reset."""

import hashlib
import logging
from datetime import datetime, timezone

from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.email import send_password_reset_email, send_verification_email
from app.auth.jwt import (
    create_access_token,
    create_email_verify_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
)
from app.auth.password import hash_password, verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest

logger = logging.getLogger(__name__)

_ERR_INVALID_TOKEN_TYPE = "Invalid token type"
_ERR_USER_NOT_FOUND = "User not found"


def _hash_token(token: str) -> str:
    """SHA-256 hash of a refresh token for safe DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


async def _store_refresh_token(db: AsyncSession, user_id: str, token: str) -> None:
    """Store the hash of a refresh token in the database."""
    from app.auth.jwt import decode_token as _decode

    payload = _decode(token)
    rt = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(token),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )
    db.add(rt)
    await db.flush()


async def register_user(db: AsyncSession, body: RegisterRequest) -> tuple[User, str, str]:
    """Register a new user. Returns (user, access_token, refresh_token)."""
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Email already registered")

    # First user becomes admin
    count_result = await db.execute(select(func.count()).select_from(User))
    user_count = count_result.scalar() or 0
    role = "admin" if user_count == 0 else "user"

    user = User(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=role,
    )
    db.add(user)
    await db.flush()

    access = create_access_token(user.id, user.email, user.role)
    refresh = create_refresh_token(user.id)
    await _store_refresh_token(db, user.id, refresh)
    await db.commit()

    # Send verification email (non-blocking, errors are logged)
    try:
        verify_token = create_email_verify_token(user.id)
        send_verification_email(user.email, verify_token)
    except Exception:
        logger.exception("Failed to send verification email")

    return user, access, refresh


async def login_user(db: AsyncSession, body: LoginRequest) -> tuple[User, str, str]:
    """Authenticate and return tokens. Raises ValueError on bad credentials."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None:
        raise ValueError("Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise ValueError("Invalid email or password")

    user.last_login_at = datetime.now(timezone.utc)
    access = create_access_token(user.id, user.email, user.role)
    refresh = create_refresh_token(user.id)
    await _store_refresh_token(db, user.id, refresh)
    await db.commit()
    return user, access, refresh


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    """Rotate refresh token. Returns (new_access, new_refresh). Raises ValueError on invalid."""
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise ValueError("Invalid refresh token")

    if payload.get("type") != "refresh":
        raise ValueError(_ERR_INVALID_TOKEN_TYPE)

    token_hash = _hash_token(refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is None or stored.revoked:
        raise ValueError("Token revoked or not found")

    if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValueError("Token expired")

    # Revoke old token
    stored.revoked = True

    # Look up user for new access token
    user_result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise ValueError(_ERR_USER_NOT_FOUND)

    new_access = create_access_token(user.id, user.email, user.role)
    new_refresh = create_refresh_token(user.id)
    await _store_refresh_token(db, user.id, new_refresh)
    await db.commit()
    return new_access, new_refresh


async def logout_user(db: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh token."""
    token_hash = _hash_token(refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is not None:
        stored.revoked = True
        await db.commit()


async def google_login(db: AsyncSession, google_info: dict) -> tuple[User, str, str]:
    """Handle Google OAuth login/signup. Returns (user, access_token, refresh_token)."""
    google_id = google_info["google_id"]
    email = google_info["email"]

    # Try to find by google_id
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if user is None:
        # Try to find by email (link accounts)
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is not None:
            user.google_id = google_id
            if google_info.get("email_verified"):
                user.email_verified = True
        else:
            # First user becomes admin
            count_result = await db.execute(select(func.count()).select_from(User))
            user_count = count_result.scalar() or 0
            role = "admin" if user_count == 0 else "user"

            user = User(
                first_name=google_info.get("first_name", ""),
                last_name=google_info.get("last_name", ""),
                email=email,
                google_id=google_id,
                role=role,
                email_verified=google_info.get("email_verified", False),
            )
            db.add(user)

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    access = create_access_token(user.id, user.email, user.role)
    refresh = create_refresh_token(user.id)
    await _store_refresh_token(db, user.id, refresh)
    await db.commit()
    return user, access, refresh


async def verify_email(db: AsyncSession, token: str) -> None:
    """Verify a user's email address via token. Raises ValueError on invalid."""
    try:
        payload = decode_token(token)
    except JWTError:
        raise ValueError("Invalid or expired verification token")

    if payload.get("type") != "email_verify":
        raise ValueError(_ERR_INVALID_TOKEN_TYPE)

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(_ERR_USER_NOT_FOUND)

    user.email_verified = True
    await db.commit()


async def forgot_password(db: AsyncSession, email: str) -> None:
    """Send a password reset email. Silent if user not found (prevent enumeration)."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return  # Silent -- don't reveal whether email exists

    token = create_password_reset_token(user.id)
    try:
        send_password_reset_email(user.email, token)
    except Exception:
        logger.exception("Failed to send password reset email")


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    """Reset a user's password via token. Raises ValueError on invalid."""
    try:
        payload = decode_token(token)
    except JWTError:
        raise ValueError("Invalid or expired reset token")

    if payload.get("type") != "password_reset":
        raise ValueError(_ERR_INVALID_TOKEN_TYPE)

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(_ERR_USER_NOT_FOUND)

    user.password_hash = hash_password(new_password)
    await db.commit()
