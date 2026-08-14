"""
Tests for the eval harness itself.

The live evals call a real model, so they cannot run in CI. What runs here is the
machinery they depend on: if the overlap checker or the fake calendar is wrong,
the eval results are worthless in either direction — silently passing a broken
agent, or failing a correct one.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from evals.fake_calendar import FakeCalendarError, FakeCalendar
from evals.invariants import (
    check_all,
    find_buffer_violations,
    find_double_bookings,
    find_out_of_bounds,
    find_zero_or_negative_duration,
)
from tools.calendar_tools import make_calendar_tools

NY = "America/New_York"


def ev(summary, start, end, tz=NY):
    z = ZoneInfo(tz)
    return {
        "summary": summary,
        "start": datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=z),
        "end": datetime.strptime(end, "%Y-%m-%d %H:%M").replace(tzinfo=z),
    }


# --- double booking ---------------------------------------------------------


def test_detects_overlap():
    events = [
        ev("A", "2026-04-01 09:00", "2026-04-01 10:00"),
        ev("B", "2026-04-01 09:30", "2026-04-01 10:30"),
    ]
    assert len(find_double_bookings(events)) == 1


def test_touching_events_are_not_an_overlap():
    events = [
        ev("A", "2026-04-01 09:00", "2026-04-01 10:00"),
        ev("B", "2026-04-01 10:00", "2026-04-01 11:00"),
    ]
    assert find_double_bookings(events) == []


def test_fully_contained_event_is_an_overlap():
    events = [
        ev("Outer", "2026-04-01 09:00", "2026-04-01 12:00"),
        ev("Inner", "2026-04-01 10:00", "2026-04-01 11:00"),
    ]
    assert len(find_double_bookings(events)) == 1


def test_detects_overlap_across_timezones():
    """Same instant, different offsets: still a conflict."""
    events = [
        ev("NY 9am", "2026-04-01 09:00", "2026-04-01 10:00", NY),
        ev("Berlin 3pm", "2026-04-01 15:00", "2026-04-01 16:00", "Europe/Berlin"),
    ]
    assert len(find_double_bookings(events)) == 1


def test_three_way_overlap_reports_each_pair():
    events = [
        ev("A", "2026-04-01 09:00", "2026-04-01 11:00"),
        ev("B", "2026-04-01 09:30", "2026-04-01 11:30"),
        ev("C", "2026-04-01 10:00", "2026-04-01 12:00"),
    ]
    assert len(find_double_bookings(events)) == 3


def test_no_false_positive_on_a_clean_day():
    events = [
        ev("A", "2026-04-01 09:00", "2026-04-01 10:00"),
        ev("B", "2026-04-01 11:00", "2026-04-01 12:00"),
        ev("C", "2026-04-01 14:00", "2026-04-01 15:00"),
    ]
    assert find_double_bookings(events) == []


# --- buffer -----------------------------------------------------------------


def test_detects_insufficient_buffer():
    events = [
        ev("A", "2026-04-01 09:00", "2026-04-01 10:00"),
        ev("B", "2026-04-01 10:05", "2026-04-01 11:00"),
    ]
    assert len(find_buffer_violations(events, 15)) == 1


def test_exact_buffer_is_acceptable():
    events = [
        ev("A", "2026-04-01 09:00", "2026-04-01 10:00"),
        ev("B", "2026-04-01 10:15", "2026-04-01 11:00"),
    ]
    assert find_buffer_violations(events, 15) == []


def test_overlap_is_not_double_reported_as_buffer():
    """An overlap is a double-booking; reporting it twice inflates the failure."""
    events = [
        ev("A", "2026-04-01 09:00", "2026-04-01 10:00"),
        ev("B", "2026-04-01 09:30", "2026-04-01 10:30"),
    ]
    assert find_buffer_violations(events, 15) == []


# --- day bounds -------------------------------------------------------------


def test_detects_event_before_day_start():
    events = [ev("Early", "2026-04-01 06:00", "2026-04-01 07:00")]
    assert len(find_out_of_bounds(events, NY, 8, 22)) == 1


def test_detects_event_after_day_end():
    events = [ev("Late", "2026-04-01 22:30", "2026-04-01 23:30")]
    assert len(find_out_of_bounds(events, NY, 8, 22)) == 1


def test_event_inside_bounds_is_clean():
    events = [ev("Fine", "2026-04-01 09:00", "2026-04-01 10:00")]
    assert find_out_of_bounds(events, NY, 8, 22) == []


def test_bounds_are_evaluated_in_the_users_zone():
    """
    A Berlin event at 09:00 local is 03:00 in New York. Judged against Berlin it
    is in bounds; against New York it is not. The user's zone is what counts.
    """
    events = [ev("Berlin morning", "2026-04-01 09:00", "2026-04-01 10:00", "Europe/Berlin")]
    assert find_out_of_bounds(events, "Europe/Berlin", 8, 22) == []
    assert find_out_of_bounds(events, NY, 8, 22) != []


def test_event_ending_exactly_at_day_end_is_clean():
    events = [ev("Ends on time", "2026-04-01 21:00", "2026-04-01 22:00")]
    assert find_out_of_bounds(events, NY, 8, 22) == []


# --- duration ---------------------------------------------------------------


def test_detects_zero_duration():
    events = [ev("Instant", "2026-04-01 09:00", "2026-04-01 09:00")]
    assert len(find_zero_or_negative_duration(events)) == 1


def test_detects_inverted_duration():
    events = [ev("Backwards", "2026-04-01 10:00", "2026-04-01 09:00")]
    assert len(find_zero_or_negative_duration(events)) == 1


# --- check_all scoping ------------------------------------------------------


def test_pre_existing_out_of_bounds_event_is_not_the_agents_fault():
    """
    A user's own 7am standup must not fail the eval, or the harness is unusable
    against real calendars.
    """
    existing = ev("User's 7am standup", "2026-04-01 07:00", "2026-04-01 07:30")
    created = ev("Agent's block", "2026-04-01 09:00", "2026-04-01 10:00")
    violations = check_all(
        all_events=[existing, created],
        created_events=[created],
        timezone_name=NY,
        day_start_hour=8,
        day_end_hour=22,
        buffer_minutes=15,
    )
    assert violations == []


def test_agent_colliding_with_a_pre_existing_event_is_caught():
    existing = ev("Dinner", "2026-04-01 20:30", "2026-04-01 21:30")
    created = ev("Study", "2026-04-01 21:00", "2026-04-01 22:00")
    violations = check_all(
        all_events=[existing, created],
        created_events=[created],
        timezone_name=NY,
        day_start_hour=8,
        day_end_hour=22,
        buffer_minutes=15,
    )
    assert any(v.kind == "double_booking" for v in violations)


# --- fake calendar ----------------------------------------------------------


def test_insert_then_list_returns_the_event():
    """The whole point: unlike MagicMock, state persists."""
    cal = FakeCalendar()
    tools = {t.name: t for t in make_calendar_tools(cal, NY)}
    tools["create_calendar_event"].invoke({
        "title": "Gym", "date": "2026-04-01",
        "start_time": "09:00", "end_time": "10:00",
    })
    result = tools["get_calendar_events"].invoke({"date": "2026-04-01"})
    assert "Gym" in result
    assert "09:00 to 10:00" in result


def test_created_event_blocks_the_slot_afterwards():
    cal = FakeCalendar()
    tools = {t.name: t for t in make_calendar_tools(cal, NY)}
    tools["create_calendar_event"].invoke({
        "title": "Gym", "date": "2026-04-01",
        "start_time": "09:00", "end_time": "10:00",
    })
    slots = tools["get_free_slots"].invoke({"date": "2026-04-01"})
    assert "08:00 to 09:00" in slots
    assert "10:15" in slots  # 10:00 plus the buffer


def test_list_filters_by_the_requested_window():
    """
    This is what gives the harness teeth. If the tool asks for the wrong window,
    the fake withholds events exactly as Google did — which is how the timezone
    bug produced double-bookings.
    """
    cal = FakeCalendar()
    cal.add_timed_event("Evening", "2026-04-01 20:30", "2026-04-01 21:30")
    cal.add_timed_event("Next day", "2026-04-02 09:00", "2026-04-02 10:00")

    tools = {t.name: t for t in make_calendar_tools(cal, NY)}
    result = tools["get_calendar_events"].invoke({"date": "2026-04-01"})
    assert "Evening" in result
    assert "Next day" not in result


def test_naive_window_is_rejected():
    """Google rejects naive RFC3339; so must the fake, or it would accept the bug."""
    cal = FakeCalendar()
    with pytest.raises(FakeCalendarError):
        cal.events().list(
            calendarId="primary",
            timeMin="2026-04-01T00:00:00",
            timeMax="2026-04-02T00:00:00",
        ).execute()


def test_insert_without_timezone_is_rejected():
    """A naive dateTime with no timeZone is ambiguous and a real bug source."""
    cal = FakeCalendar()
    with pytest.raises(FakeCalendarError):
        cal.events().insert(
            calendarId="primary",
            body={
                "summary": "Ambiguous",
                "start": {"dateTime": "2026-04-01T09:00:00"},
                "end": {"dateTime": "2026-04-01T10:00:00"},
            },
        ).execute()


def test_all_day_event_does_not_occupy_time():
    cal = FakeCalendar()
    cal.add_all_day_event("Holiday", "2026-04-01")
    assert cal.timed_events == []

    tools = {t.name: t for t in make_calendar_tools(cal, NY)}
    slots = tools["get_free_slots"].invoke({"date": "2026-04-01"})
    assert "08:00 to 22:00" in slots


def test_created_events_excludes_seeded_ones():
    cal = FakeCalendar()
    cal.add_timed_event("Pre-existing", "2026-04-01 09:00", "2026-04-01 10:00")
    tools = {t.name: t for t in make_calendar_tools(cal, NY)}
    tools["create_calendar_event"].invoke({
        "title": "Agent added", "date": "2026-04-01",
        "start_time": "11:00", "end_time": "12:00",
    })
    assert [e["summary"] for e in cal.created_events] == ["Agent added"]
    assert len(cal.timed_events) == 2


def test_fake_calendar_reports_its_timezone():
    cal = FakeCalendar(timezone_name="Asia/Kolkata")
    assert cal.calendars().get(calendarId="primary").execute()["timeZone"] == "Asia/Kolkata"


def test_end_to_end_double_booking_is_detectable():
    """
    Force the failure the harness exists to catch: insert two overlapping events
    and confirm check_all reports it. Without this, a silent checker would make
    every eval pass.
    """
    cal = FakeCalendar()
    tools = {t.name: t for t in make_calendar_tools(cal, NY)}
    for start, end in (("09:00", "10:00"), ("09:30", "10:30")):
        tools["create_calendar_event"].invoke({
            "title": f"Event {start}", "date": "2026-04-01",
            "start_time": start, "end_time": end,
        })

    violations = check_all(
        all_events=cal.timed_events,
        created_events=cal.created_events,
        timezone_name=NY,
        day_start_hour=8,
        day_end_hour=22,
        buffer_minutes=15,
    )
    assert any(v.kind == "double_booking" for v in violations)
