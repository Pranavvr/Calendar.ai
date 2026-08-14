import logging
import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.crypto import encrypt_token
from auth.google_auth import fetch_primary_timezone
from auth.jwt import (
    COOKIE_SECURE,
    JWT_TTL_HOURS,
    SESSION_COOKIE_NAME,
    create_session_token,
)
from db.models import GoogleCredentials, User
from db.session import get_db

logger = logging.getLogger(__name__)

GOOGLE_REDIRECT_URI = os.environ["GOOGLE_REDIRECT_URI"]

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile https://www.googleapis.com/auth/calendar",
    },
)

router = APIRouter(prefix="/auth/google", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    return await oauth.google.authorize_redirect(
        request,
        GOOGLE_REDIRECT_URI,
        access_type="offline",
        prompt="consent",
    )


@router.get("/callback")
async def callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        # The exception text can contain the authorization code and provider
        # detail, so log the type and return a generic message rather than
        # echoing upstream errors to the caller.
        logger.warning("auth.callback_failed", extra={"error_type": type(e).__name__})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sign-in failed. Please try again.",
        )

    userinfo = token.get("userinfo")
    if userinfo is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No userinfo in token response",
        )

    refresh_token = token.get("refresh_token")
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google did not return a refresh_token. Revoke app access in your Google account settings and try again.",
        )

    # Read the user's calendar timezone while we still hold a fresh access
    # token. Returns None on failure, which is not fatal — scheduling falls
    # back to config.TIMEZONE.
    calendar_tz = await fetch_primary_timezone(token.get("access_token", ""))

    result = await db.execute(select(User).where(User.google_sub == userinfo["sub"]))
    user = result.scalar_one_or_none()

    is_new_user = user is None

    if user is None:
        user = User(
            google_sub=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name"),
            picture_url=userinfo.get("picture"),
            timezone=calendar_tz,
        )
        db.add(user)
        await db.flush()
    else:
        user.email = userinfo["email"]
        user.name = userinfo.get("name")
        user.picture_url = userinfo.get("picture")
        # Refresh on each login so a user who moves gets picked up, but never
        # overwrite a known-good value with a failed lookup.
        if calendar_tz:
            user.timezone = calendar_tz

    await db.merge(GoogleCredentials(
        user_id=user.id,
        refresh_token=encrypt_token(refresh_token),
        scope=token.get("scope", ""),
    ))
    await db.commit()

    logger.info(
        "auth.login_succeeded",
        extra={
            "user_id": str(user.id),
            "new_user": is_new_user,
            "timezone": calendar_tz or "fallback",
        },
    )

    session_token = create_session_token(user.id)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=JWT_TTL_HOURS * 3600,
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    # Attributes must match those used when setting it, or the browser will not
    # consider it the same cookie and the session survives "logout".
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )
    return response
