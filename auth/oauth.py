import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import JWT_TTL_HOURS, SESSION_COOKIE_NAME, create_session_token
from db.models import GoogleCredentials, User
from db.session import get_db

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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth callback failed: {e}",
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

    result = await db.execute(select(User).where(User.google_sub == userinfo["sub"]))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            google_sub=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name"),
            picture_url=userinfo.get("picture"),
        )
        db.add(user)
        await db.flush()
    else:
        user.email = userinfo["email"]
        user.name = userinfo.get("name")
        user.picture_url = userinfo.get("picture")

    await db.merge(GoogleCredentials(
        user_id=user.id,
        refresh_token=refresh_token,
        scope=token.get("scope", ""),
    ))
    await db.commit()

    session_token = create_session_token(user.id)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=JWT_TTL_HOURS * 3600,
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
