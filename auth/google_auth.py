import asyncio
import os
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GoogleCredentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


async def fetch_primary_timezone(access_token: str) -> str | None:
    """
    Read the IANA timezone of the user's primary calendar, e.g. "Europe/Berlin".

    Called once during the OAuth callback, where we already hold a fresh access
    token, so this avoids a refresh round-trip.

    Returns None on any failure. Timezone is a convenience, not a credential —
    a lookup failure must never block sign-in, and callers fall back to
    config.TIMEZONE.
    """

    def _fetch() -> str | None:
        service = build("calendar", "v3", credentials=Credentials(token=access_token))
        calendar = service.calendars().get(calendarId="primary").execute()
        return calendar.get("timeZone")

    try:
        name = await asyncio.to_thread(_fetch)
    except Exception:
        return None

    if not name:
        return None

    # Only store something zoneinfo can actually load, so a bad value fails
    # here at login rather than later inside a scheduling request.
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None

    return name


async def get_calendar_service_for_user(user_id: uuid.UUID, db: AsyncSession):
    creds_row = await db.get(GoogleCredentials, user_id)
    if creds_row is None:
        raise RuntimeError(f"No Google credentials stored for user {user_id}")

    credentials = Credentials(
        token=None,
        refresh_token=creds_row.refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )

    # google-auth uses a sync HTTP client. Run in a thread so we don't block
    # the event loop during the token refresh round-trip.
    await asyncio.to_thread(credentials.refresh, Request())

    return build("calendar", "v3", credentials=credentials)
