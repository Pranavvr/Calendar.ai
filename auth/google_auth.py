import asyncio
import os
import uuid

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GoogleCredentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


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
