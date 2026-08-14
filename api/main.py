import os

from dotenv import load_dotenv

load_dotenv()

import logging  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402

from fastapi import Depends, FastAPI, HTTPException, Request, status  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from agent.graph import make_agent  # noqa: E402
from api.rate_limit import SlidingWindowRateLimiter  # noqa: E402
from auth.google_auth import GoogleCredentialsError  # noqa: E402
from auth.jwt import get_current_user_id  # noqa: E402
from auth.oauth import router as oauth_router  # noqa: E402
from config import (  # noqa: E402
    RECURSION_LIMIT,
    SCHEDULE_RATE_LIMIT_REQUESTS,
    SCHEDULE_RATE_LIMIT_WINDOW_SECONDS,
)
from db.models import User  # noqa: E402
from db.session import get_db  # noqa: E402
from observability import (  # noqa: E402
    configure_logging,
    estimate_cost_usd,
    new_request_id,
    request_id_var,
    user_id_var,
)

configure_logging()
logger = logging.getLogger(__name__)

schedule_limiter = SlidingWindowRateLimiter(
    max_requests=SCHEDULE_RATE_LIMIT_REQUESTS,
    window_seconds=SCHEDULE_RATE_LIMIT_WINDOW_SECONDS,
)

app = FastAPI(title="cal.ai", description="AI calendar scheduling agent")


@app.middleware("http")
async def request_context(request: Request, call_next):
    """
    Tag every request with an id and log its outcome.

    The id is echoed back in X-Request-Id so a user reporting a failure can be
    matched to the exact log lines for their request.

    Note what is deliberately absent: no request bodies, no query strings. The
    body of POST /schedule is the user's own words about their day, which is
    personal data with no operational value in a log.
    """
    incoming = request.headers.get("x-request-id")
    request_id = incoming if incoming else new_request_id()
    token = request_id_var.set(request_id)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http.request_failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        request_id_var.reset(token)
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    # /health is polled by the ALB every 30s; logging it would bury everything
    # else at a cost of ~2,900 lines a day.
    if request.url.path != "/health":
        logger.info(
            "http.request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )

    response.headers["X-Request-Id"] = request_id
    request_id_var.reset(token)
    return response

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
    user_id_var.set(str(user_id))

    allowed, retry_after = schedule_limiter.check(str(user_id))
    if not allowed:
        logger.warning(
            "schedule.rate_limited",
            extra={"retry_after_s": round(retry_after, 1)},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many scheduling requests. Please wait and try again.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    started = time.perf_counter()

    try:
        agent, usage = await make_agent(user_id, db)
    except GoogleCredentialsError:
        # Recoverable by the user, so say so rather than returning a 500.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Calendar access is no longer authorized. Sign in again.",
        )

    # Message length rather than content: what the user wants scheduled is
    # personal, but length is useful for correlating cost with input size.
    logger.info("schedule.started", extra={"message_chars": len(request.message)})

    result = ""
    try:
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": request.message}]},
            stream_mode="values",
            config={"recursion_limit": RECURSION_LIMIT},
        ):
            last_msg = chunk["messages"][-1]
            if type(last_msg).__name__ == "AIMessage" and last_msg.content:
                result = last_msg.content
    except Exception:
        logger.exception(
            "schedule.failed",
            extra={
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                **usage,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Scheduling failed. Please try again.",
        )

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "schedule.completed",
        extra={
            "duration_ms": duration_ms,
            "estimated_cost_usd": estimate_cost_usd(
                usage["input_tokens"], usage["output_tokens"]
            ),
            "produced_result": bool(result),
            **usage,
        },
    )

    if not result:
        # The graph can finish without a final assistant message, e.g. on
        # hitting the recursion limit. Previously this returned HTTP 200 with an
        # empty string, which looks like success to the caller.
        logger.warning("schedule.no_result", extra={"recursion_limit": RECURSION_LIMIT})
        raise HTTPException(
            status_code=502,
            detail="The agent did not produce a response. Please rephrase and try again.",
        )

    return ScheduleResponse(result=result)
