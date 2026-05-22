# Phase 1 — Concepts Reference

A reference for everything I learned during the Phase 1 multi-user refactor
of cal-ai. Organized by topic so I can grep this later in interviews.

---

## 1. Phase 1 plan & decisions

cal-ai migration plan, in 4 phases:

| Phase | Scope |
|---|---|
| **1** | Multi-user refactor (DB-backed users, per-user OAuth tokens, async FastAPI with JWT). Still deployable to EC2. |
| **2** | Push image to ECR via CI. |
| **3** | Terraform + migrate compute from EC2 → ECS Fargate. |
| **4** | CD pipeline (merge to main → live in prod). Only feasible once orchestrator (ECS) exists. |

**Branch:** `feat/multi-user`. Never touch `main` while EC2 demo runs from it.

**Constraints:** one thing at a time, no abstractions for hypothetical needs,
no tests beyond what falls out naturally.

**Final stack decisions (Option A′):**
- DB: **RDS Postgres** (12-month AWS free tier, then ~$15/mo)
- Auth: **roll-your-own with Authlib** (highest interview signal; demonstrates real OAuth understanding)
- Secrets: AWS Secrets Manager
- Compute: stays EC2 in Phase 1, becomes ECS Fargate in Phase 3
- Registry: **ECR** (canonical pairing with ECS; not GHCR)
- IaC: **Terraform from Phase 1** (RDS, ECR, Secrets Manager). Industry default.

---

## 2. OAuth 2.0 flow (what cal-ai will implement)

The 8-step authorization-code dance, done **once per user** at first login:

1. User clicks "Sign in with Google" on cal-ai
2. cal-ai redirects browser to `accounts.google.com/o/oauth2/auth?...`
3. Google shows consent screen ("cal-ai wants to read/write your calendar")
4. User clicks Allow
5. Google redirects browser back to cal-ai's `/auth/callback?code=...`
6. cal-ai POSTs the `code` to Google's token endpoint
7. Google responds with `access_token` (short-lived, ~1hr) + `refresh_token` (long-lived)
8. cal-ai stores the `refresh_token` in Postgres, keyed by user

Thereafter: every time the agent needs to act on Bob's calendar, cal-ai fetches
Bob's `refresh_token` from the DB, exchanges it for a fresh access_token, and
calls the Calendar API.

**Who writes steps 1–7?** Depends on auth provider:
- Authlib (our pick) → we write all 8 ourselves (~150 lines)
- Auth0 / Cognito / Supabase Auth → they write 1–7; we write step 8

---

## 3. Authlib

A **Python library** (`pip install authlib`), not a service. Implements
OAuth 2.0 / OpenID Connect / JWT specs. Same author as SQLAlchemy.

**When you need OAuth library:**
- "Sign in with X" buttons — you're the OAuth client
- Accessing user-owned data on another service's API (Google Calendar, GitHub, Spotify) — cal-ai's case
- Issuing your own OAuth tokens (rare — only if you're building Stripe-like API)
- JWT signing/verification

**Don't need it if:**
- You use Supabase Auth, Auth0, Cognito, Clerk (they wrap it)
- Username/password only (no third-party)

In cal-ai we use `authlib` for both OAuth (Google login) **and** JWT (our own session tokens). One library, two roles.

---

## 4. AWS OIDC

**OIDC = OpenID Connect**, an auth layer on OAuth 2.0. AWS uses it to let
GitHub Actions assume AWS roles **without long-lived AWS credentials**.

**Old pattern (bad):** store `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` as
GitHub secrets. Keys live forever; rotation is manual; leak risk persists.

**New pattern (industry-standard since ~2021):** AWS trusts GitHub as an OIDC
provider. GitHub Actions gets a short-lived OIDC JWT scoped to the repo.
The JWT is exchanged at AWS for temporary credentials (valid ~1 hour). No
long-lived secrets stored.

Three pieces:
1. AWS IAM OIDC identity provider pointing at GitHub
2. IAM role with trust policy allowing GitHub workflows from your repo
3. `aws-actions/configure-aws-credentials@v4` in the workflow YAML

---

## 5. Database choice — why RDS over Supabase / Neon

| | Postgres | Built-in OAuth | Free tier | AWS-native |
|---|---|---|---|---|
| **RDS** | ✅ | ❌ (use Authlib) | 12 mo | ✅ |
| Aurora | ✅ | ❌ | no | ✅ |
| Neon | ✅ | ❌ | forever | ❌ (specialist host) |
| Supabase | ✅ | ✅ (BaaS) | 500MB, pauses | ❌ |

Industry ranking for Postgres on AWS: **RDS > Aurora > specialist hosts > Supabase**.

Picked RDS+Authlib because: highest interview signal, industry-standard, all-AWS resume.

Honest tradeoff: 1–2 days extra to write OAuth ourselves vs. Supabase's "one SDK call." We pay it because the upskill matters.

---

## 6. SQLAlchemy

The **standard Python database library**. Two parts:

- **Core**: connection pooling, sessions, executing SQL. The "engine" stuff.
- **ORM** (Object-Relational Mapper): Python classes that map to SQL tables.
  Read/write rows as Python objects rather than string SQL.

```python
# ORM
user = await db.get(User, user_id)
print(user.email)      # → SELECT * FROM users WHERE id = $1

# Core
result = await db.execute("SELECT * FROM users WHERE id = $1", user_id)
```

**Why ORM over raw SQL for CRUD:**
1. Typos blow up at edit time (type checker), not runtime
2. Refactor safety (rename column → IDE shows every usage)
3. Composability (build queries from Python objects)
4. Database portability (same code, multiple DB dialects)

**When raw SQL still wins:** complex analytics, window functions, recursive
CTEs, perf-critical hot loops. Mix freely — SQLAlchemy supports both.

**Models in cal-ai** (`db/models.py`):
- `User` — id (UUID), google_sub, email, name, picture_url, created/updated_at
- `GoogleCredentials` — user_id (PK + FK), refresh_token, scope, updated_at
- 1-to-1 relationship between them (via `uselist=False`)

---

## 7. Alembic

A **database migration tool**, same author as SQLAlchemy.

**Problem it solves:** your schema (`models.py`) evolves over time. You need
to keep local Postgres, staging, RDS, and collaborators' DBs all in sync —
incrementally, reversibly, safely.

**Workflow:**
1. Edit `db/models.py` (add column, rename, etc.)
2. `alembic revision --autogenerate -m "..."` → creates migration file
3. Review the generated SQL
4. `alembic upgrade head` → applies to local DB
5. Commit `models.py` + migration to git
6. Deploy runs `alembic upgrade head` against RDS

Migration files have `upgrade()` (apply) and `downgrade()` (reverse). Each
has a unique revision ID; they form a linked list via `down_revision`.

**Why never `DROP TABLE; CREATE TABLE` in prod:** deletes data. `ALTER TABLE`
preserves data; that's what migrations emit.

`alembic_version` is a special table Alembic creates in your DB to track
which revisions are currently applied.

---

## 8. Docker concepts

### Images vs. containers

- **Image** = a snapshot (a Linux filesystem with software pre-installed). Like a class.
- **Container** = a running instance of an image. Like an object.

One image → many containers (each its own filesystem layer on top).

### Where images come from

| Pattern | How |
|---|---|
| **Pre-built** (postgres, nginx, python) | `docker pull <name>` — downloads from a registry (default: Docker Hub) |
| **Your own** | `docker build -t myapp .` — builds from your `Dockerfile` |
| **Push your own** to a registry | `docker push <registry>/<name>:<tag>` |
| **Pull your own** on another machine | `docker pull <registry>/<name>:<tag>` |

Full canonical name: `docker.io/library/postgres:16`. Omitting parts uses
defaults: `postgres:16` ⇒ `docker.io/library/postgres:16`.

For private registries (ECR): need `docker login` first.

### docker-compose

A YAML file describing multiple containers as one stack. `docker compose up`
starts them all on a shared Docker network. **Each `services:` entry is one
container.**

Containers on the same network reach each other by **service name**:
e.g. inside the app container, `localhost` means the app container itself,
and the DB is at `db:5432`.

### Ports

`"5432:5432"` = `<host>:<container>`. The right side (container-internal) is
fixed by the image's config. The left side (host) is your choice.

Common ports: 22 SSH, 80 HTTP, 443 HTTPS, 3000 Node dev, 5000 Flask, 5432
Postgres, 6379 Redis, 8000 FastAPI/Django dev, 27017 MongoDB.

### Volumes

Named volume (`cal_ai_pg_data`) survives container restarts/rebuilds.
Without it, Postgres data dies the moment you `docker compose down`.

### Healthcheck

Tells compose how to know a service is actually ready (not just "started").
For Postgres: `pg_isready -U cal_ai -d cal_ai`. Other services can
`depends_on: condition: service_healthy`.

---

## 9. Architecture — monolith vs. microservices

**Key insight:** "monolith vs microservices" is about how your **application
code** is split into runtime processes, NOT how many containers you have.

Postgres + Redis + FastAPI app = 3 containers but 1 application = **monolith**.

To be microservices, you need multiple processes of YOUR application logic,
communicating over HTTP/gRPC.

### Other architectures

| | What it is |
|---|---|
| Monolith | One app, one deployable unit. Default. |
| Modular monolith | Monolith with strict internal module boundaries. Current industry favorite. |
| Microservices | Many services, network-coupled. ~100+ engineers usually. |
| SOA | Older predecessor of microservices, coarser-grained. |
| Serverless / FaaS | Functions on Lambda etc. Event-driven. |
| Event-driven | Components publish/subscribe to a message bus (Kafka). |
| Layered / N-tier | Internal organization within an app. Orthogonal to above. |
| Hexagonal / Clean | Internal code structure pattern. Orthogonal to above. |

### When to use which

Default to **monolith**. Always. Then split reactively when concrete pain
appears (teams stepping on each other, scaling specific endpoints, divergent
deploy cadences).

Signals you've outgrown monolith: ~50+ engineers in the same codebase,
endpoints with wildly different scaling needs, team-autonomy bottlenecks.

Until then: monolith. Even at portfolio scale, even at series-B startup
scale.

### How each scales in prod

**Monolith:** load balancer fronts N replicas of the same app. Scale = add
more replicas. Drawback: scale the whole app even if only one endpoint is hot.

**Microservices:** each service has its own LB and replica count. Scale only
the busy service. Cost: every cross-service call is a network call (latency,
failures, retries needed). Distributed tracing required to debug.

---

## 10. Monorepo vs polyrepo

Independent of monolith/microservices — about **git repo structure**:

- **Polyrepo:** each service has its own git repo, its own CI. Older convention.
- **Monorepo:** all services in one git repo, CI uses path filters to run only
  the relevant pipelines on changes. Used by Google, Meta, Uber, Linear,
  Vercel.

You can have a monorepo + monolith (cal-ai today), a monorepo + microservices
(Google), polyrepo + monolith (single repo, multiple repos is unusual here),
polyrepo + microservices (older startups).

---

## 11. CI triggers — branches vs paths

Two orthogonal axes:

| Trigger axis | What controls it |
|---|---|
| **Event** | `on: push:` (any push), `on: pull_request:` (PRs), `on: schedule:` (cron), `on: workflow_dispatch:` (manual) |
| **Filter** | `branches:` filter (e.g. only main), `paths:` filter (e.g. only services/users/**) |

Standard small-repo pattern (cal-ai's):
```yaml
on:
  push:
  pull_request:
    branches: [main]
```
Runs whole pipeline on every push to any branch + every PR to main.

Path-filtered pattern (monorepo):
```yaml
on:
  push:
    branches: [main]
    paths: ["services/users/**"]
```
Runs only when files in `services/users/**` change AND the push is to main.

**Use path filtering when:** CI is slow, monorepo with multiple deploy units,
mixed-content repo (docs + code), or paying-per-minute CI.

**Don't bother for:** small single-app projects like cal-ai today.

---

## 12. Frontend architecture — why SPA frontends aren't a "service"

Modern web frontends (React/Vue/Svelte SPA pattern):

1. Browser visits `cal-ai.com`
2. CDN serves a tiny HTML + JS bundle (static files)
3. **JS code runs in the user's browser** (on their laptop CPU)
4. JS makes HTTP `fetch()` calls to your backend
5. Backend returns JSON
6. JS updates the page DOM

The "frontend" is **code that ships to and runs in the browser**. The static
file server (CloudFront + S3, Vercel, Netlify) is just file delivery — it
doesn't run your UI logic.

**There is no "frontend service process" running on a server.**

**Server-Side Rendering (SSR)** is the exception — Next.js, SvelteKit,
Django/Rails classic. The frontend code runs on a server, generates HTML,
sends to browser. That IS a server process. More complex, more expensive,
better for SEO + initial load.

**For cal-ai's eventual UI:** simplest = SPA on S3+CloudFront. No frontend
server. Static files only. Interview answer is "SPA on CDN."

---

## 13. AWS resources & costs

Phase 1 monthly cost (within 12-month free tier): ~$0.40 (just Secrets
Manager). After free tier: ~$22–25.

Phase 3 adds: Fargate (~$9), ALB (~$16/mo base), NAT Gateway (~$32/mo per AZ if
used). Total post-Phase-3: ~$60–80 unless you skip NAT.

### NAT Gateway

Sits in a public subnet. Resources in private subnets route outbound through
it; the NAT has a public IP, the resources don't.

**Cost meme:** ~$32/mo just for existing + $0.045/GB processed. Multi-AZ
"proper" setup is $65–100/mo.

**Skip-NAT pattern for portfolio:** put ECS Fargate in a public subnet with
restrictive security groups (inbound 443/80 only from the ALB SG). Saves
$32+/mo. Interview-defensible.

### IAM vs RDS master user

| | IAM | RDS master user |
|---|---|---|
| Lives where | AWS account level | Inside the Postgres DB |
| Used for | "this user can launch EC2" | "this user can SELECT from users" |
| Auth method | API keys / OIDC / SSO | Username + password |

Completely separate systems. Your app connects to RDS with a Postgres user +
password (stored in Secrets Manager). Your app uses an IAM role to *fetch*
that secret from Secrets Manager. Different layers.

(AWS has "IAM database authentication" as an opt-in feature where the two
merge; not the default and not what we'll use.)

---

## 14. Environment variables — `.env` vs `.env.example`

- `.env` — actual values, gitignored, lives only on your machine / server.
- `.env.example` — template, committed to git, documents which variables exist.

`load_dotenv()` (from `python-dotenv` package) reads `.env` and puts each
line into `os.environ`. After that call, `os.environ["DATABASE_URL"]` works.

In production: env vars come from the orchestrator (ECS task definition,
EC2 instance env, AWS Secrets Manager). `.env` file isn't present, but
`load_dotenv()` silently does nothing — same code works.

This is the 12-factor app principle: "config in the environment."

---

## 15. JWT-based sessions

Session model for cal-ai:

1. User logs in via Google OAuth → `/auth/callback`
2. Our handler creates/finds the user, stores credentials, signs a JWT
   containing `{user_id, exp}`
3. JWT is set as an HttpOnly Secure cookie in the response
4. Every subsequent `/schedule` request: middleware reads cookie, verifies
   JWT signature, extracts `user_id`, looks up the user's refresh_token

**No `sessions` table** — the JWT IS the session, signed with a server-side
secret stored in Secrets Manager. Verifying = checking signature, not a DB
lookup. This is "stateless sessions."

Tradeoff vs. server-side sessions: can't easily invalidate a JWT before it
expires (you'd need a revocation list). For short-lived JWTs (~1hr) and a
portfolio project, this is fine.

---

## 16. Schema (final, Phase 1)

```sql
CREATE TABLE users (
  id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  google_sub  TEXT         NOT NULL UNIQUE,    -- canonical identity (not email)
  email       TEXT         NOT NULL UNIQUE,
  name        TEXT,
  picture_url TEXT,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE google_credentials (
  user_id       UUID         PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  refresh_token TEXT         NOT NULL,
  scope         TEXT         NOT NULL,
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

**Intentionally omitted:** `password_hash` (OAuth only), `sessions` (JWT instead),
`timezone` per user (still global config), `chat_history` (agent is stateless
per request), `audit_log` (no observability needed yet).

`google_sub` is the canonical user identity — Google's stable `sub` claim
from the OIDC ID token. Email can change; sub never does.
