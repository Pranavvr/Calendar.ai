# cal.ai

An AI calendar scheduling agent that takes natural-language requests (e.g. *"Gym, study 2 hours, groceries"*) and books them onto your Google Calendar, working around existing events and respecting buffer time.

Multi-user, with per-user Google OAuth. Runs on ECS Fargate behind an ALB and CloudFront, with RDS Postgres, provisioned by Terraform.

Built with [LangGraph](https://langchain-ai.github.io/langgraph/), the Google Calendar API, and FastAPI.

## How it works

A LangGraph ReAct loop with three tools:

- `get_calendar_events(date)` — list everything already booked on a day
- `get_free_slots(date)` — compute open windows between events, accounting for the buffer
- `create_calendar_event(title, date, start_time, end_time)` — book a new event

The model is instructed to check free slots before scheduling and never to double-book.

**The tools are closed over a Calendar client already authorized for one user**, so the
model never receives a user identifier and has no argument through which it could be
redirected to someone else's calendar. That makes cross-tenant access structurally
impossible rather than prompt-dependent — see [ADR 0007](docs/adr/0007-tools-closed-over-per-user-client.md).

## Project layout

```
agent/       LangGraph graph, system prompt, token accounting
api/         FastAPI app + per-user rate limiter
auth/        Google OAuth, JWT session, refresh-token encryption
tools/       Calendar tools exposed to the agent
db/          SQLAlchemy models + async session
alembic/     Migrations
evals/       Agent eval harness (see evals/README.md)
terraform/   All AWS infrastructure
docs/adr/    Architecture decision records
config.py    Model, day window, buffer, rate limit, recursion limit
```

## Setup

1. **Google OAuth client.** Create a **Web application** client in Google Cloud Console.
   Add `http://localhost:8000/auth/google/callback` as an authorized redirect URI for local
   development. Note the client ID and secret.

   Requesting the Calendar scope makes this a *sensitive* scope, which means Google requires
   HTTPS redirect URIs in production. That constraint is why CloudFront exists here — see
   [ADR 0002](docs/adr/0002-cloudfront-for-https.md).

2. **Environment.** Copy `.env.example` to `.env` and fill it in. Generate the secrets:

   ```sh
   openssl rand -hex 32                     # JWT_SECRET, SESSION_SECRET
   .venv/bin/python -c "from auth.crypto import generate_key; print(generate_key())"
   ```

   Set `COOKIE_SECURE=false` locally — the session cookie is HTTPS-only by default and is
   never sent over plain-HTTP localhost.

3. **Install and migrate.**

   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
   docker compose up -d                     # local Postgres
   .venv/bin/alembic upgrade head
   ```

   Dependencies are fully locked. Edit `requirements.in` / `requirements-dev.in`, never the
   `.txt` files, and regenerate with `pip-compile` — see [ADR 0008](docs/adr/0008-pin-all-dependencies.md).

## Run

```sh
.venv/bin/uvicorn api.main:app --reload
```

Then open <http://localhost:8000> and sign in with Google. Once signed in:

```sh
curl -X POST http://localhost:8000/schedule \
  -H 'Content-Type: application/json' \
  -b 'cal_ai_session=<your cookie>' \
  -d '{"message": "gym at 7am, study 2 hours"}'
```

Docker:

```sh
docker build -t cal-ai .
docker run -p 8000:8000 --env-file .env cal-ai
```

## Deploy

```sh
./deploy.sh     # provision + build + push + migrate. Costs ~$28-43/mo while running.
./destroy.sh    # tear down
```

Requires an AWS profile named `cal-ai`. `deploy.sh` prints the CloudFront redirect URI to
add to your Google OAuth client — that step is manual because the CloudFront domain is
assigned at creation.

Migrations run as a one-off ECS task inside the VPC, because RDS is not publicly reachable.

## Configuration

| Setting | Default | Meaning |
| --- | --- | --- |
| `TIMEZONE` | `America/New_York` | **Fallback only.** Each user's real timezone is read from their primary Google Calendar at login and stored on `users.timezone` |
| `MODEL_NAME` | `gpt-4o-mini` | LLM driving the agent |
| `DAY_START_HOUR` / `DAY_END_HOUR` | `8` / `22` | Bounds of the schedulable day, in the user's zone |
| `BUFFER_MINUTES` | `15` | Padding inserted between events |
| `RECURSION_LIMIT` | `10` | Max agent steps per request |
| `SCHEDULE_RATE_LIMIT_REQUESTS` | `10` | Per user, per window |
| `SCHEDULE_RATE_LIMIT_WINDOW_SECONDS` | `300` | Rate limit window |

Timezone handling is the most bug-prone area of this codebase: the app schedules in the
user's zone, the container runs UTC, and Google returns offset-aware times. Any change
touching dates should say which clock it means.

## Tests

```sh
.venv/bin/python -m pytest tests/ -q     # 82 tests
.venv/bin/ruff check .                   # pinned 0.15.9, matches CI
```

Unit tests cover the tools, the log formatter and its redaction, encryption, and the rate
limiter.

**Agent behaviour is measured separately**, by an eval harness that runs the agent against
a stateful fake calendar and checks the *resulting calendar* for double-bookings, buffer
violations, and out-of-bounds events — rather than checking what the model claimed it did.
It calls a real model, so it costs money and is not part of the test suite:

```sh
.venv/bin/python -m evals.runner --repeat 5
```

See [evals/README.md](evals/README.md) and [ADR 0010](docs/adr/0010-evals-score-final-calendar-state.md).

## Design decisions

Non-obvious choices — and the deliberate cost tradeoffs — are written up in
[docs/adr/](docs/adr/README.md), each with the constraint that forced it and the condition
that would change it.
