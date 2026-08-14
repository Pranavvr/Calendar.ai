"""
Structured JSON logging.

Logs go to stdout as one JSON object per line, because that is what the awslogs
driver forwards to CloudWatch — where a JSON payload becomes queryable with
CloudWatch Logs Insights, while a formatted string does not.

Request context (request id, user id) travels in ContextVars rather than being
threaded through every call signature, so a log line emitted deep inside a tool
still correlates to the request that caused it.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

# Keys that must never appear in a log line even if a caller passes them.
# A Google refresh token grants durable calendar access and does not expire, so
# leaking one into CloudWatch is a real compromise, not an untidy log.
_REDACTED_KEYS = frozenset({
    "refresh_token",
    "access_token",
    "token",
    "client_secret",
    "authorization",
    "password",
    "jwt",
    "session_token",
    "api_key",
})

_RESERVED = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
})


def new_request_id() -> str:
    return uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id

        user_id = user_id_var.get()
        if user_id:
            payload["user_id"] = user_id

        # Anything passed via logger.info("event", extra={...}) lands as a
        # record attribute; promote those to top-level fields.
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_") or key in payload:
                continue
            payload[key] = "[redacted]" if key.lower() in _REDACTED_KEYS else value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """
    Install the JSON formatter on the root logger.

    Replaces existing handlers rather than adding to them, so uvicorn's default
    plain-text handlers do not produce a second, unparseable copy of every line.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn installs its own handlers; make them propagate to root instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(name)
        log.handlers = []
        log.propagate = True

    # httpx logs a line per outbound request at INFO, which for this app means
    # one per LLM call and one per Calendar call. Useful at DEBUG, noise here.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """
    Rough USD cost for one agent run.

    Deliberately an estimate: prices are a local constant that upstream can
    change at any time, so treat this as an order-of-magnitude signal for
    spotting a runaway loop, not as billing data.
    """
    from config import MODEL_PRICE_PER_1M_INPUT, MODEL_PRICE_PER_1M_OUTPUT

    return round(
        (input_tokens / 1_000_000) * MODEL_PRICE_PER_1M_INPUT
        + (output_tokens / 1_000_000) * MODEL_PRICE_PER_1M_OUTPUT,
        6,
    )
