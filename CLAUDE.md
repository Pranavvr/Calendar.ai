# cal.ai

AI calendar scheduling agent. Natural-language requests ("gym, study 2 hours, groceries")
get booked onto the user's Google Calendar, working around existing events and buffer time.

LangGraph ReAct loop → three calendar tools → FastAPI → ECS Fargate + RDS + ALB + CloudFront.

## Layout

| Path | Holds |
| --- | --- |
| `agent/` | LangGraph graph + system prompt |
| `api/` | FastAPI app (`/`, `/health`, `/me`, `/schedule`) |
| `auth/` | Google OAuth flow, JWT session cookie, per-user Calendar client |
| `tools/` | The three calendar tools exposed to the LLM |
| `db/` | SQLAlchemy models + async session |
| `alembic/` | Migrations |
| `terraform/` | All AWS infrastructure |

## Commands

Always use the project venv; there is no global install.

```sh
.venv/bin/python -m pytest tests/ -q     # tests
.venv/bin/ruff check .                   # lint (pinned 0.15.9, matches CI)
docker compose up -d                     # local Postgres
.venv/bin/alembic upgrade head           # migrations
./deploy.sh                              # provision + deploy to AWS (SPENDS MONEY)
./destroy.sh                             # tear down
```

## Hard rules

- **AWS: always `--profile cal-ai`.** The default profile has stale credentials and is a
  different account entirely.
- **Never run `terraform apply` or `deploy.sh` without asking.** They create billable
  resources (~$28–43/mo).
- **Assume infrastructure is torn down.** The normal resting state of this project is
  destroyed, to avoid cost. Verify before assuming anything is live.
- **Never commit `.venv/`.** It is gitignored but was tracked before that, so ~12k files
  are still in the index and `.git` is ~146MB. Do not add to the problem.
- **Never commit `notebooks/*.md`.** Personal learning notes, not project artifacts.
- **Secrets never enter git.** `.env`, `token.json`, `credentials.json`, `*.tfstate` are
  gitignored and history is currently clean. Keep it that way.

## Timezone hazard

The single most bug-prone area in this codebase. Three different clocks are in play:

- The app schedules in **`America/New_York`** (hardcoded in `tools/calendar_tools.py`;
  `config.TIMEZONE` is currently dead code).
- The **container runs UTC** — no `TZ` is set in the Dockerfile or task definition, so
  `datetime.now()` is UTC in production and local time on a laptop.
- **Google returns event times with an offset** (e.g. `-04:00`), not in UTC.

Any change touching dates, event windows, or "today" must state explicitly which clock it
is using. Never compare a naive datetime against an offset-aware one.

## Deliberate tradeoffs — do not flag these as defects

These are conscious cost decisions for a portfolio project. Re-raising them as findings is
noise. If a change would alter one, say so explicitly and explain the cost delta.

- Single-AZ RDS on `db.t4g.micro`, and `skip_final_snapshot` on destroy
- ECS `desired_count = 1`, no autoscaling
- The account's **default VPC**, public subnets, no NAT gateway (a NAT alone is ~$32/mo)
- CloudFront `PriceClass_100` and the default `*.cloudfront.net` certificate, chosen
  because Google requires HTTPS redirect URIs for sensitive scopes and this avoids buying
  a domain
- CloudWatch log retention of 7 days
- Local Terraform state

Each of these is written up in `docs/adr/` with the constraint that forced it and the
condition that would change it. Read the relevant record before proposing a change to one.

Genuine gaps not on that list are fair game. Currently open: no Dependabot, so pinned
dependencies get no security updates (ADR 0008); `POST /schedule` is synchronous with a
timeout at expected latency (ADR 0003); sessions cannot be revoked before expiry
(ADR 0005); evals cost money so behaviour regressions are not caught in CI (ADR 0010);
and `Environment` is still a hardcoded tag rather than a variable (ADR 0001).

## Git

- One concern per branch. `fix/` for behavior, `feat/` for capability, `chore/` for tooling.
- Branch from `main` unless the work genuinely depends on something unmerged.
- **Never commit directly to `main`.**
- Conventional commits with a scope: `fix(ecs):`, `feat(infra):`, `chore(ci):`.
- The commit body explains **why**, including the constraint that forced the decision — not
  what changed, which the diff already shows. This history is a portfolio artifact; someone
  will read `git log`. Preserve that standard.
- Commit at logical checkpoints once lint and tests are green. No need to ask.
- **Ask before `git push`, opening a PR, or merging.** These are outward-facing and the
  repo is public.

## Dependencies

`requirements.txt` is currently unpinned, which has already caused a CI failure with no code
change (ruff 0.16 expanded its default rule set overnight). Until that is fixed, treat any
"works locally, fails in CI" result as a version-drift suspect first. Pin anything new you add.

## Working style

- **One thing at a time.** Finish and verify before starting the next.
- **Explain before implementing.** Define jargon inline. The goal here is upskilling and
  interview readiness, not just shipped code — so reasoning matters more than speed.
- **Architectural decisions belong to Pranav.** Lay out the tradeoff and recommend, but do
  not silently choose. A design choice he did not make is one he cannot defend.
- **No hypothetical abstractions.** Build for what exists now.
- **No premature tests.** Tests that lock in behavior we are about to change are waste.
- Report failures plainly with the actual output. Do not describe unverified work as done.
