# ADR 0003 — POST /schedule is synchronous, accepting a 60s ceiling

**Status:** Accepted
**Date:** 2026-08-14

## Context

An agent run makes several LLM calls interleaved with Google Calendar round-trips.
Measured runs take 40-60 seconds.

CloudFront's `origin_read_timeout` maxes out at 60 seconds without a service quota
increase. So the ceiling sits at roughly the *expected* duration of the work, not
comfortably above it.

## Options

**Synchronous request/response.** Simplest, and the client gets its answer in one call.
But any run exceeding the ceiling returns 504 with no partial result and no way to
resume, and the user has already waited a minute to find that out.

**202 Accepted plus polling.** `POST /schedule` returns a job id immediately;
`GET /schedule/{id}` reports status. Removes the timeout coupling entirely and makes
retries meaningful. Costs a job store, a background worker or task, status endpoints, and
client-side polling — a substantially larger surface for a single-user app.

**Streaming (SSE or WebSocket).** Good UX, since the agent's intermediate steps are
genuinely interesting to watch. But CloudFront plus ALB plus Fargate streaming is fiddly,
and there is no frontend to consume it — the client today is Swagger UI.

## Decision

Stay synchronous. Raise the origin timeout to the 60s maximum and accept that requests
near the upper end of the expected range will fail.

## Consequences

**This is the least comfortable decision in the project.** The timeout is not
comfortably above expected latency; it is at it. A slow LLM response or a retried Calendar
call pushes a normal request over the edge, and the failure mode is a bare 504 after a
60-second wait.

There is no retry semantics and no partial result: a run that creates two of three events
and then times out leaves the calendar half-updated with no record returned to the caller.
The events *are* created, so the effect is not lost, but the user does not learn what
happened.

Mitigations in place rather than a fix: recursion is capped at 10 to bound the worst case,
and token counts and duration are logged per run so the latency distribution is
observable instead of guessed at.

## What would change this

Any latency increase — more tools, a larger model, more calendar round-trips — or the
first user-visible 504. The logged `duration_ms` on `schedule.completed` is the signal to
watch; a p95 approaching 50s means the async design is overdue. Adding a real frontend
would also tip this, since streaming becomes worth the complexity once something can
render it.
