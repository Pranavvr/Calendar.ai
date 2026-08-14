import os
import uuid
from datetime import datetime, timedelta, timezone

from authlib.jose import JoseError, jwt
from fastapi import Cookie, HTTPException, status

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = int(os.environ.get("JWT_TTL_HOURS", "168"))  # 7 days
# Distinct from Starlette SessionMiddleware's "session" cookie used for OAuth state.
SESSION_COOKIE_NAME = "cal_ai_session"

# Send the session cookie over HTTPS only. Defaults to on: the failure mode of
# forgetting to enable it in production (a 7-day token granting calendar access
# sent in cleartext) is far worse than the failure mode of forgetting to disable
# it locally (no session over plain-HTTP localhost).
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() not in {
    "false", "0", "no",
}


def create_session_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_TTL_HOURS)).timestamp()),
    }
    header = {"alg": JWT_ALGORITHM}
    return jwt.encode(header, payload, JWT_SECRET).decode("utf-8")


def verify_session_token(token: str) -> uuid.UUID:
    try:
        claims = jwt.decode(token, JWT_SECRET)
        claims.validate()
    except JoseError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid session: {e}",
        )
    return uuid.UUID(claims["sub"])


async def get_current_user_id(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> uuid.UUID:
    if session_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return verify_session_token(session_token)
