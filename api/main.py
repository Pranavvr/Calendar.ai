import os

from dotenv import load_dotenv

load_dotenv()

import uuid  # noqa: E402

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from agent.graph import make_agent  # noqa: E402
from auth.jwt import get_current_user_id  # noqa: E402
from auth.oauth import router as oauth_router  # noqa: E402
from config import RECURSION_LIMIT  # noqa: E402
from db.models import User  # noqa: E402
from db.session import get_db  # noqa: E402

app = FastAPI(title="cal.ai", description="AI calendar scheduling agent")

# Authlib's OAuth client stores its CSRF `state` parameter in a server-side
# session cookie during the redirect dance. SessionMiddleware provides that.
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"])

app.include_router(oauth_router)


class ScheduleRequest(BaseModel):
    message: str


class ScheduleResponse(BaseModel):
    result: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    picture_url: str | None


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
      <title>cal.ai</title>
      <meta charset="utf-8">
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
               max-width: 640px; margin: 60px auto; padding: 0 24px; color: #222; }
        h1 { margin-bottom: 8px; }
        p.tagline { color: #666; margin-top: 0; }
        .actions { display: flex; flex-direction: column; gap: 12px; margin: 32px 0; }
        a.button {
          display: inline-block; padding: 12px 20px; background: #4285f4;
          color: white; text-decoration: none; border-radius: 6px;
          font-weight: 500; text-align: center;
        }
        a.button:hover { background: #3367d6; }
        a.secondary { color: #4285f4; text-decoration: none; }
        a.secondary:hover { text-decoration: underline; }
        .links { display: flex; gap: 20px; margin-top: 24px; font-size: 14px; }
      </style>
    </head>
    <body>
      <h1>cal.ai</h1>
      <p class="tagline">AI-powered calendar scheduling agent.</p>

      <div class="actions">
        <a class="button" href="/auth/google/login">Sign in with Google</a>
      </div>

      <div class="links">
        <a class="secondary" href="/me">View my profile</a>
        <a class="secondary" href="/docs">API docs</a>
        <a class="secondary" href="/health">Health</a>
      </div>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me", response_model=MeResponse)
async def me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        picture_url=user.picture_url,
    )


@app.post("/schedule", response_model=ScheduleResponse)
async def schedule(
    request: ScheduleRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    agent = await make_agent(user_id, db)

    result = ""
    async for chunk in agent.astream(
        {"messages": [{"role": "user", "content": request.message}]},
        stream_mode="values",
        config={"recursion_limit": RECURSION_LIMIT},
    ):
        last_msg = chunk["messages"][-1]
        if type(last_msg).__name__ == "AIMessage" and last_msg.content:
            result = last_msg.content

    return ScheduleResponse(result=result)
