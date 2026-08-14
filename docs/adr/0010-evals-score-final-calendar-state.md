# ADR 0010 — Evals score the calendar's final state, not the model's description of it

**Status:** Accepted
**Date:** 2026-08-14

## Context

The README promises the agent works around existing events, respects buffer time, and never
double-books. Nothing measured whether any of that is true.

The existing tests could not have. They drive the tools with `MagicMock`, which returns
whatever it was told regardless of the query and never stores anything — so there is no
calendar state for a new event to conflict with. A double-booking is unrepresentable.

## Options

**Assert on the agent's final message.** Easy, and worthless: the model produces fluent
prose. An agent will describe a conflict-free schedule while having inserted an overlapping
event, and a string match cannot tell the difference.

**LLM-as-judge.** Ask a model whether the schedule looks right. Useful for qualities that
resist encoding, like tone. For "do these two intervals overlap," it substitutes a
probabilistic answer for an arithmetic one.

**Assert on the calendar's final state.** Run the agent against a stateful fake, then check
the resulting events against explicit invariants. Requires building a fake faithful enough
that a tool bug still shows up.

## Decision

Score final state. `FakeCalendar` persists inserted events and filters `list()` by
`timeMin`/`timeMax` the way Google does. `invariants.py` holds pure checks for overlaps,
buffer, day bounds, and duration.

## Consequences

The fake's window filtering is what makes the harness meaningful, and it is verified rather
than assumed. Replaying the old UTC day window reproduces the original bug end to end: an
8:30pm Eastern event is withheld exactly as Google withheld it, the agent believes the
evening is free, and the checker reports the resulting double-booking. **The harness
demonstrably catches the bug that shipped.**

Invariants are scoped asymmetrically on purpose. Overlap and buffer are checked against all
events, since new events must not collide with existing ones. Day bounds and duration are
checked only against events the agent created — a user's own 7am standup is not the agent's
fault, and flagging it would make the harness unusable against a real calendar.

The checkers are pure functions and are unit-tested, including a forced double-booking that
confirms the checker does not silently pass. Without that, a broken checker would make
every eval succeed, which is worse than having no evals.

The runner calls a real model, so it costs money and cannot run in CI. What runs in CI is
the harness machinery. That means **a regression in agent behaviour is not caught
automatically** — someone has to run the evals.

`--repeat` exists because the agent is non-deterministic. A case that passes once and fails
once is not a passing case, and a single-run report would be misleading.

Nothing here evaluates the quality of the agent's explanation, only the correctness of what
it did.

## What would change this

Caring about response phrasing, which is where an LLM-judge becomes the right tool
alongside these checks rather than instead of them. Also: if runs became cheap or a smaller
model were good enough, the evals could move into CI on a schedule — which is what would
turn this from a manual check into a real regression gate.
