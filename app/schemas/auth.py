"""Authentication and user identity schemas for registration, login, and token management."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Request body for new user registration.

    Use this schema to validate registration form submissions. Password strength
    rules are enforced via a field validator requiring mixed case and digits.
    """

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validate that the password meets minimum strength requirements.

        Args:
            v: The raw password string to validate.

        Returns:
            The validated password string, unchanged.
        """
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    """Request body for user login with email and password credentials."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """Read-only representation of an authenticated user returned by the API.

    Use this schema for returning user profile data after login, registration,
    or token refresh. Includes BYOK (bring your own key) and free-tier fields.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    email: str
    role: str
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None
    has_api_key: bool = False
    free_runs_used: int = 0
    free_run_limit: int = 1


class TokenResponse(BaseModel):
    """Response body containing access and refresh tokens after successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class RefreshRequest(BaseModel):
    """Request body for refreshing an expired access token using a refresh token."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Request body for initiating a password reset flow via email."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request body for completing a password reset with a token and new password.

    Use this schema to validate password reset submissions. Password strength
    rules are enforced via a field validator requiring mixed case and digits.
    """

    token: str
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validate that the new password meets minimum strength requirements.

        Args:
            v: The raw password string to validate.

        Returns:
            The validated password string, unchanged.
        """
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class VerifyEmailRequest(BaseModel):
    """Request body for verifying a user's email address using a verification token."""

    token: str


def user_to_read(user: object) -> "UserRead":
    """Build a UserRead from a User ORM instance, including BYOK fields."""
    from app.config import settings as app_settings

    return UserRead(
        id=user.id,  # type: ignore[attr-defined]
        first_name=user.first_name,  # type: ignore[attr-defined]
        last_name=user.last_name,  # type: ignore[attr-defined]
        email=user.email,  # type: ignore[attr-defined]
        role=user.role,  # type: ignore[attr-defined]
        email_verified=user.email_verified,  # type: ignore[attr-defined]
        created_at=user.created_at,  # type: ignore[attr-defined]
        last_login_at=user.last_login_at,  # type: ignore[attr-defined]
        has_api_key=bool(user.encrypted_api_key),  # type: ignore[attr-defined]
        free_runs_used=user.free_runs_used,  # type: ignore[attr-defined]
        free_run_limit=app_settings.free_run_limit,
    )
