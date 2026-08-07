# Multi-stage: wheels are built in the builder, so the compiler toolchain and
# pip's build caches never reach the runtime image.
#
# Base is pinned to bookworm rather than floating on python:3.12-slim, so a new
# Debian release cannot change the image underneath a rebuild. Pinning by digest
# would be stricter still, at the cost of manual bumps for security updates.

FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Only the lockfile, so this layer caches until dependencies actually change.
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim-bookworm AS runtime

# PYTHONUNBUFFERED matters here: without it, stdout is block-buffered when not a
# TTY and logs arrive in CloudWatch late or truncated on crash.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root. A container escape from a root process is a far worse day than one
# from an unprivileged one, and nothing here needs root.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

# --no-index: install strictly from the wheels built above, so the runtime stage
# cannot reach the network and silently resolve something unpinned.
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
