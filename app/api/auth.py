"""Authentication endpoints: register, login, refresh, logout, Google OAuth, email verify, password reset."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.oauth import exchange_google_code, get_google_auth_url
from app.auth.rate_limit import limiter
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
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=TokenResponse)
@limiter.limit("10/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        user, access, refresh = await auth_service.register_user(db, body)
    except ValueError as e:
        if "already registered" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        user, access, refresh = await auth_service.login_user(db, body)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserRead.model_validate(user),
    )


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
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
    await auth_service.logout_user(db, body.refresh_token)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser):
    return UserRead.model_validate(user)


@router.get("/google")
async def google_login(request: Request):
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    redirect_uri = str(request.url_for("google_callback"))
    url = get_google_auth_url(redirect_uri)
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    redirect_uri = str(request.url_for("google_callback"))
    try:
        google_info = await exchange_google_code(code, redirect_uri)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to authenticate with Google")

    user, access, refresh = await auth_service.google_login(db, google_info)

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


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await auth_service.verify_email(db, body.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"detail": "Email verified successfully"}


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await auth_service.forgot_password(db, body.email)
    return {"detail": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await auth_service.reset_password(db, body.token, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"detail": "Password reset successfully"}
