"""
Properties a correct schedule must satisfy.

These are the promises the README makes — "working around existing events",
"respecting buffer time", "never double-book" — expressed as checks against the
calendar's final state rather than against what the model said it did.

Checking final state matters: an agent can produce a confident summary claiming
it avoided a conflict while having inserted an overlapping event. Only the
calendar knows.

Pure functions over event dicts, so they are unit-testable without an LLM. The
harness is only trustworthy if the checker itself is tested.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Violation:
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.detail}"


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def find_double_bookings(events: list[dict]) -> list[Violation]:
    """
    Any pair of events occupying the same instant.

    Touching events (one ends exactly when the next begins) are not overlaps.
    """
    out = []
    ordered = sorted(events, key=lambda e: e["start"])
    for i in range(len(ordered) - 1):
        for j in range(i + 1, len(ordered)):
            a, b = ordered[i], ordered[j]
            if b["start"] >= a["end"]:
                break  # sorted, so nothing later can overlap a
            out.append(Violation(
                "double_booking",
                f"'{a['summary']}' ({_fmt(a['start'])}-{_fmt(a['end'])}) overlaps "
                f"'{b['summary']}' ({_fmt(b['start'])}-{_fmt(b['end'])})",
            ))
    return out


def find_buffer_violations(events: list[dict], buffer_minutes: int) -> list[Violation]:
    """
    Consecutive events closer together than the configured buffer.

    Only gaps are checked; an actual overlap is reported by find_double_bookings
    rather than double-counted here.
    """
    out = []
    ordered = sorted(events, key=lambda e: e["start"])
    for a, b in zip(ordered, ordered[1:]):
        if b["start"] < a["end"]:
            continue  # overlap, not a buffer problem
        gap = (b["start"] - a["end"]).total_seconds() / 60
        if gap < buffer_minutes:
            out.append(Violation(
                "buffer",
                f"only {gap:.0f} min between '{a['summary']}' and '{b['summary']}' "
                f"(need {buffer_minutes})",
            ))
    return out


def find_out_of_bounds(
    events: list[dict],
    timezone_name: str,
    day_start_hour: int,
    day_end_hour: int,
) -> list[Violation]:
    """Events falling outside the schedulable window, in the user's own zone."""
    tz = ZoneInfo(timezone_name)
    out = []
    for e in events:
        start = e["start"].astimezone(tz)
        end = e["end"].astimezone(tz)

        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        # An event ending exactly at midnight reads as 00:00; treat as end of day.
        if end_minutes == 0 and end.date() > start.date():
            end_minutes = 24 * 60

        if start_minutes < day_start_hour * 60:
            out.append(Violation(
                "before_day_start",
                f"'{e['summary']}' starts {_fmt(start)}, before {day_start_hour:02d}:00",
            ))
        if end_minutes > day_end_hour * 60:
            out.append(Violation(
                "after_day_end",
                f"'{e['summary']}' ends {_fmt(end)}, after {day_end_hour:02d}:00",
            ))
    return out


def find_zero_or_negative_duration(events: list[dict]) -> list[Violation]:
    out = []
    for e in events:
        if e["end"] <= e["start"]:
            out.append(Violation(
                "bad_duration",
                f"'{e['summary']}' ends at or before it starts "
                f"({_fmt(e['start'])} to {_fmt(e['end'])})",
            ))
    return out


def check_all(
    all_events: list[dict],
    created_events: list[dict],
    timezone_name: str,
    day_start_hour: int,
    day_end_hour: int,
    buffer_minutes: int,
) -> list[Violation]:
    """
    Every invariant, in one pass.

    Overlap and buffer are checked against *all* events, since the point is that
    new events must not collide with pre-existing ones. Bounds and duration are
    checked only against created events: a user's own 7am standup is not the
    agent's fault, and flagging it would make the eval unusable on real calendars.
    """
    return [
        *find_double_bookings(all_events),
        *find_buffer_violations(all_events, buffer_minutes),
        *find_out_of_bounds(created_events, timezone_name, day_start_hour, day_end_hour),
        *find_zero_or_negative_duration(created_events),
    ]
