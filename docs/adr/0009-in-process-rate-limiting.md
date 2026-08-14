# ADR 0009 — Rate limiting is in-process, which is correct only while there is one task

**Status:** Accepted
**Date:** 2026-08-14

## Context

`POST /schedule` fans out to an LLM and to the Google Calendar API and takes 40-60
seconds. It had no rate limit, so one authenticated user could drive unbounded spend.

The realistic threat is not a malicious actor. It is a retry loop, a stuck browser tab, or
a client that resends on timeout — and given ADR 0003, timeouts are expected.

## Options

**No limit.** What existed. `RECURSION_LIMIT` bounds a single run but says nothing about
how many runs a caller may start.

**In-process counter.** A few dozen lines, no dependency, no new infrastructure. State
lives in one process, so it is only complete if there is only one process.

**Redis or ElastiCache.** Correct under any topology. The smallest ElastiCache node costs
more per month than the rest of this stack, for a single-user application.

**API Gateway or WAF rate rules.** Enforced before traffic reaches the app, but keyed on
IP rather than on user, and adds a service.

## Decision

An in-process sliding-window limiter: 10 requests per 5 minutes per user, returning 429
with `Retry-After`.

Keyed on user id, not IP. Every caller is authenticated, and IP keying would punish users
behind a shared NAT while doing nothing about a single account looping.

A sliding window rather than a fixed one, because a fixed window lets a caller send twice
the limit across a bucket boundary — meaningful when each request is a 60-second LLM call.

## Consequences

**The limit is per task, so it is only the configured value while `desired_count` is 1.**
With N tasks the effective limit becomes N times the configured value, because each task
counts independently. This is the single assumption that breaks on scale-out and it is
recorded in the module docstring as well as here.

Counters are lost on restart or redeploy, so a caller's budget resets. For bounding
accidental spend that is acceptable; for enforcing a quota it would not be.

The key dictionary grows once per user and never shrinks on its own, so there is an
explicit `evict_idle()`. It is called opportunistically rather than on a timer, since there
is no scheduler in the process.

The chosen numbers are a judgement, not a measurement: comfortably above what a person
does by hand, low enough to bound a runaway loop. They may be wrong, and the
`schedule.rate_limited` log line is what would show it.

## What would change this

`desired_count` changing to anything above 1. That single edit silently multiplies the
limit, which is why it is called out here rather than left implicit. At that point the
counter moves to Redis, or rate limiting moves in front of the application.
