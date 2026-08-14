# Agent evals

Unit tests check that a tool formats its output. These check whether the **agent
actually schedules correctly** — that it does not double-book, respects the
buffer, and stays inside the schedulable day.

## Why the unit tests were not enough

`tests/test_tools.py` uses `MagicMock`, which returns whatever it was told to
regardless of the query and never stores anything. That cannot catch a
double-booking, because there is no calendar state to conflict with.

`FakeCalendar` fixes both halves:

- `insert()` **persists** the event, so the final calendar can be checked for
  overlaps.
- `list()` **honours `timeMin`/`timeMax`** the way Google does.

The second is what gives the harness teeth. The timezone bug — querying a UTC day
for a US Eastern user — is reproducible here:

```
timeMin=2026-04-01T00:00:00+00:00  timeMax=2026-04-01T23:59:59+00:00
  -> an 8:30pm Eastern event is withheld, exactly as Google withheld it
  -> the agent believes 20:00-22:00 is free and books over it
  -> check_all() reports: double_booking: 'Dinner' overlaps 'Study'
```

## Layout

| File | Role |
| --- | --- |
| `fake_calendar.py` | Stateful, window-filtering stand-in for the Calendar API |
| `invariants.py` | Pure property checks: overlaps, buffer, day bounds, duration |
| `cases.py` | Scenarios, each with a note on the failure mode it targets |
| `runner.py` | Runs cases against the real agent and scores the result |

## Running

The harness machinery is covered by `tests/test_evals.py`, which runs in CI for
free. That matters: if the overlap checker were wrong, every eval result would be
worthless in either direction.

The live evals call a real model, so they **cost money** and are not part of the
test suite:

```sh
.venv/bin/python -m evals.runner
.venv/bin/python -m evals.runner --case evening_conflict --repeat 5
```

**Use `--repeat`.** The agent is non-deterministic, so a single pass proves very
little — a case that passes once and fails once is not a passing case. The report
gives a pass rate per case, and the exit code is non-zero if any case is less than
perfect across its runs.

## Scoring

On the calendar's **final state**, never on what the model said. An agent will
happily produce a confident summary describing a conflict-free schedule while
having inserted an overlapping event. Only the calendar knows.

Day bounds and duration are checked against events the agent *created*; overlap
and buffer against *all* events. A user's own 7am standup is not the agent's
fault, and flagging it would make the harness unusable against real calendars.

## Adding a case

Append to `CASES` in `cases.py`. Every case carries a `why` explaining the failure
mode it targets — a suite where everything passes on the first run is measuring
nothing, so prefer cases you expect to be able to fail.
