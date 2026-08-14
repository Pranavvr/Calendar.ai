"""
Eval scenarios.

Each case is a starting calendar plus a request, and the properties the result
must satisfy. Cases are chosen for the failure modes that actually occurred or
are plausible, not for coverage of the happy path — an eval suite where
everything passes on the first run is measuring nothing.

Dates are in 2026 and fixed rather than relative, so a case cannot start failing
because it was run on a Sunday or across a month boundary.
"""

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    name: str
    why: str
    request: str
    timezone_name: str = "America/New_York"
    # (summary, 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD HH:MM') in the calendar's zone
    existing: list[tuple[str, str, str]] = field(default_factory=list)
    all_day: list[tuple[str, str]] = field(default_factory=list)
    # How many events the agent is expected to create; None means "do not check".
    expect_created: int | None = None


CASES: list[EvalCase] = [
    EvalCase(
        name="empty_day_single_task",
        why="Baseline. If this fails, nothing else is meaningful.",
        request="Schedule a 1 hour gym session on 2026-04-01.",
        expect_created=1,
    ),
    EvalCase(
        name="evening_conflict",
        why=(
            "The regression that motivated this harness. An 8:30pm event was "
            "invisible to a UTC day query, so the agent booked over it. "
            "DAY_END_HOUR is 22, so the 20:00-22:00 band is schedulable and this "
            "collision is reachable."
        ),
        request="Schedule a 1 hour study session on 2026-04-01, as late as possible.",
        existing=[("Dinner", "2026-04-01 20:30", "2026-04-01 21:30")],
        expect_created=1,
    ),
    EvalCase(
        name="previous_evening_is_not_a_conflict",
        why=(
            "The mirror image: yesterday's 9pm event leaked into today's UTC "
            "window and blocked a slot that was free. The agent should still be "
            "able to use 21:00 today."
        ),
        request="Schedule a 1 hour reading block on 2026-04-01 at 9pm.",
        existing=[("Yesterday call", "2026-03-31 21:00", "2026-03-31 22:00")],
        expect_created=1,
    ),
    EvalCase(
        name="packed_day_forces_buffer_choice",
        why=(
            "Back-to-back meetings leave gaps that are free but too small once "
            "the 15 minute buffer applies. Tests that the agent uses the buffer "
            "rather than filling every literal gap."
        ),
        request="Schedule a 45 minute errand run on 2026-04-01.",
        existing=[
            ("Standup", "2026-04-01 09:00", "2026-04-01 09:30"),
            ("Design review", "2026-04-01 10:00", "2026-04-01 11:00"),
            ("Lunch", "2026-04-01 12:00", "2026-04-01 13:00"),
            ("1:1", "2026-04-01 13:30", "2026-04-01 14:00"),
        ],
        expect_created=1,
    ),
    EvalCase(
        name="multiple_tasks_one_request",
        why=(
            "The README's headline example. Several items in one message must "
            "not collide with each other, which is a different failure from "
            "colliding with existing events."
        ),
        request=(
            "On 2026-04-02: gym, study for 2 hours, and groceries. "
            "Fit them all in."
        ),
        expect_created=3,
    ),
    EvalCase(
        name="day_nearly_full",
        why=(
            "Only one viable slot remains. The agent should either use it or say "
            "it cannot fit the request, but must not double-book."
        ),
        request="Schedule a 90 minute deep work block on 2026-04-03.",
        existing=[
            ("Morning block", "2026-04-03 08:00", "2026-04-03 12:00"),
            ("Afternoon block", "2026-04-03 12:30", "2026-04-03 18:00"),
            ("Evening block", "2026-04-03 20:00", "2026-04-03 22:00"),
        ],
    ),
    EvalCase(
        name="all_day_event_present",
        why=(
            "An all-day event has no time range and must not be treated as "
            "blocking the whole day, or the agent will refuse a free day."
        ),
        request="Schedule a 1 hour workout on 2026-04-06.",
        all_day=[("Company holiday", "2026-04-06")],
        expect_created=1,
    ),
    EvalCase(
        name="non_eastern_timezone",
        why=(
            "Timezone is per-user now. A Berlin user's day bounds are their own "
            "local 08:00-22:00, not New York's."
        ),
        request="Schedule a 1 hour German lesson on 2026-04-07.",
        timezone_name="Europe/Berlin",
        expect_created=1,
    ),
    EvalCase(
        name="impossible_request",
        why=(
            "The day is completely booked. The correct behaviour is to report "
            "that it cannot fit, not to invent a slot. Scheduling anything here "
            "is a double-booking."
        ),
        request="Schedule a 2 hour workshop on 2026-04-08.",
        existing=[("Conference", "2026-04-08 08:00", "2026-04-08 22:00")],
        expect_created=0,
    ),
]


def case_by_name(name: str) -> EvalCase:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(name)
