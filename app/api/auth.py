"""Auth endpoints: register, login, refresh, logout, Google OAuth, email verify, password reset."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.oauth import exchange_google_code, get_google_auth_url
from app.config import settings
from app.db import get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserRead,
    VerifyEmailRequest,
    user_to_read,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=201,
    response_model=TokenResponse,
    responses={
        409: {"description": "Email already registered"},
        422: {"description": "Validation error"},
    },
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Register a new user account.

    Args:
        body: Registration payload containing email, password, and name fields.
        db: Async database session.

    Returns:
        TokenResponse with access token, refresh token, and user details.
    """
    try:
        user, access, refresh = await auth_service.register_user(db, body)
    except ValueError as e:
        if "already registered" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=user_to_read(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"description": "Invalid email or password"}},
)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Authenticate a user with email and password.

    Args:
        body: Login payload containing email and password.
        db: Async database session.

    Returns:
        TokenResponse with access token, refresh token, and user details.
    """
    try:
        user, access, refresh = await auth_service.login_user(db, body)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=user_to_read(user),
    )


@router.post(
    "/refresh",
    responses={401: {"description": "Invalid or expired refresh token"}},
)
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Exchange a valid refresh token for a new access/refresh token pair.

    Args:
        body: Request payload containing the refresh token to exchange.
        db: Async database session.

    Returns:
        Dict with new access_token, refresh_token, and token_type.
    """
    try:
        access, new_refresh = await auth_service.refresh_tokens(db, body.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return {"access_token": access, "refresh_token": new_refresh, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Invalidate a refresh token, ending the user's session.

    Args:
        body: Request payload containing the refresh token to revoke.
        db: Async database session.

    Returns:
        Confirmation dict with detail message.
    """
    await auth_service.logout_user(db, body.refresh_token)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser):
    """Return the currently authenticated user's profile.

    Args:
        user: The authenticated user extracted from the request token.

    Returns:
        UserRead schema with the user's public fields.
    """
    return user_to_read(user)


@router.get(
    "/google",
    responses={501: {"description": "Google OAuth not configured"}},
)
async def google_login(request: Request):
    """Initiate the Google OAuth2 login flow.

    Args:
        request: The incoming HTTP request, used to build the callback URL.

    Returns:
        RedirectResponse pointing the browser to Google's consent screen.
    """
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    redirect_uri = str(request.url_for("google_callback"))
    url = get_google_auth_url(redirect_uri)
    return RedirectResponse(url)


@router.get(
    "/google/callback",
    responses={400: {"description": "Failed to authenticate with Google"}},
)
async def google_callback(
    request: Request,
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Handle the Google OAuth2 callback after user consent.

    Args:
        request: The incoming HTTP request, used to reconstruct the redirect URI.
        code: The authorization code returned by Google.
        db: Async database session.

    Returns:
        HTMLResponse that stores tokens in localStorage and redirects to the SPA.
    """
    redirect_uri = str(request.url_for("google_callback"))
    try:
        google_info = await exchange_google_code(code, redirect_uri)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to authenticate with Google")

    _, access, refresh = await auth_service.google_login(db, google_info)

    # Return an HTML page that stores tokens and redirects
    html = f"""<!DOCTYPE html>
<html><head><title>Logging in...</title></head><body>
<script>
localStorage.setItem('access_token', '{access}');
localStorage.setItem('refresh_token', '{refresh}');
window.location.href = '/';
</script>
</body></html>"""
    from fastapi.responses import HTMLResponse

    return HTMLResponse(html)


@router.post(
    "/verify-email",
    responses={400: {"description": "Invalid or expired verification token"}},
)
async def verify_email(
    body: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Verify a user's email address using a one-time token.

    Args:
        body: Request payload containing the email verification token.
        db: Async database session.

    Returns:
        Confirmation dict with detail message.
    """
    try:
        await auth_service.verify_email(db, body.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"detail": "Email verified successfully"}


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Request a password reset email for the given address.

    Args:
        body: Request payload containing the user's email address.
        db: Async database session.

    Returns:
        Generic confirmation dict (does not reveal whether the email exists).
    """
    await auth_service.forgot_password(db, body.email)
    return {"detail": "If an account with that email exists, a reset link has been sent."}


@router.post(
    "/reset-password",
    responses={400: {"description": "Invalid or expired reset token"}},
)
async def reset_password(
    body: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reset a user's password using a valid reset token.

    Args:
        body: Request payload containing the reset token and new password.
        db: Async database session.

    Returns:
        Confirmation dict with detail message.
    """
    try:
        await auth_service.reset_password(db, body.token, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"detail": "Password reset successfully"}
