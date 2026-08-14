"""
Per-user rate limiting for expensive endpoints.

POST /schedule fans out to an LLM and to the Google Calendar API and takes
40-60s. Without a limit, one authenticated user can drive unbounded spend — the
practical risk here is not a malicious actor but a retry loop or a stuck browser
tab.

Keyed on user id rather than IP: every caller is authenticated, and IP keying
would punish users behind a shared NAT while doing nothing about a single
account looping.

Deliberately in-process, with no Redis. The service runs a single task
(desired_count = 1), so process-local state is the whole picture. This is the
one assumption that breaks on scale-out: with N tasks the effective limit
becomes N x the configured value, because each task counts independently.
Fixing that means moving the counter to Redis or ElastiCache, which is not worth
a new managed service at this size. Revisit when desired_count changes.
"""

import logging
import threading
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """
    Allows `max_requests` per `window_seconds`, per key.

    A sliding window rather than a fixed one: a fixed window lets a caller send
    2x the limit across a bucket boundary, which for a 60s LLM request is a
    meaningful burst.
    """

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        # Endpoint handlers run in the event loop, but starlette may dispatch
        # sync work to a threadpool; a lock keeps the deques consistent either way.
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def check(self, key: str) -> tuple[bool, float]:
        """
        Record an attempt.

        Returns (allowed, retry_after_seconds). retry_after is 0 when allowed.
        """
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)

            if len(hits) >= self.max_requests:
                retry_after = max(0.0, self.window_seconds - (now - hits[0]))
                return False, retry_after

            hits.append(now)
            return True, 0.0

    def reset(self, key: str | None = None) -> None:
        """Clear state. Used by tests; `key=None` clears everything."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def evict_idle(self) -> int:
        """
        Drop keys with no recent hits.

        Without this the dict grows once per user forever. Called opportunistically
        rather than on a timer, since there is no scheduler in this process.
        """
        now = time.monotonic()
        with self._lock:
            stale = [k for k in self._hits if not self._prune(k, now)]
            for k in stale:
                del self._hits[k]
        return len(stale)
