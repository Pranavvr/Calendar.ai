from unittest.mock import MagicMock

from tools.calendar_tools import make_calendar_tools

# Google returns offset-aware timestamps in the calendar's own zone, e.g.
# "2026-04-01T09:00:00-04:00" — not UTC. Fixtures mirror that faithfully;
# using a "Z" suffix here would test a response shape Google does not send.
NY = "America/New_York"  # UTC-4 on these April dates
BERLIN = "Europe/Berlin"


def get_tool(name, service, timezone_name=NY):
    tools = make_calendar_tools(service, timezone_name)
    return next(t for t in tools if t.name == name)


def _mock_service_with_events(items):
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": items}
    return service


def _event(start, end, summary="Meeting"):
    return {"start": {"dateTime": start}, "end": {"dateTime": end}, "summary": summary}


def _query_args(service):
    return service.events.return_value.list.call_args.kwargs


# --- query window -----------------------------------------------------------


def test_query_window_is_the_users_local_day_not_utc():
    """
    Regression: the window was previously "{date}T00:00:00Z".."23:59:59Z". For a
    US Eastern user that spans 8pm the previous evening to 8pm on the requested
    day, which hid real evening events and admitted the previous day's.
    """
    service = _mock_service_with_events([])
    get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})

    args = _query_args(service)
    assert args["timeMin"] == "2026-04-01T00:00:00-04:00"
    assert args["timeMax"] == "2026-04-02T00:00:00-04:00"


def test_query_window_follows_the_users_timezone():
    service = _mock_service_with_events([])
    get_tool("get_free_slots", service, BERLIN).invoke({"date": "2026-04-01"})

    args = _query_args(service)
    assert args["timeMin"] == "2026-04-01T00:00:00+02:00"
    assert args["timeMax"] == "2026-04-02T00:00:00+02:00"


# --- free slot computation --------------------------------------------------


def test_free_slots_empty_calendar():
    service = _mock_service_with_events([])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    assert "08:00" in result
    assert "22:00" in result


def test_free_slots_respects_buffer():
    service = _mock_service_with_events([
        _event("2026-04-01T09:00:00-04:00", "2026-04-01T10:00:00-04:00")
    ])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    assert "10:15" in result


def test_evening_event_blocks_its_slot():
    """
    Regression: an 8:30pm Eastern event is 00:30Z the *next* day, so the old UTC
    window never returned it and the agent would double-book over it.
    """
    service = _mock_service_with_events([
        _event("2026-04-01T20:30:00-04:00", "2026-04-01T21:30:00-04:00", "Dinner")
    ])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})

    assert "08:00 to 20:30" in result
    # 21:30 plus the 15 minute buffer.
    assert "21:45 to 22:00" in result


def test_previous_evening_event_does_not_block_this_day():
    """
    Regression: a 9pm event on Mar 31 is 01:00Z on Apr 1, so the old UTC window
    returned it and its local hour was read as 21:00 *on Apr 1*, blocking a slot
    that was actually free.
    """
    service = _mock_service_with_events([
        _event("2026-03-31T21:00:00-04:00", "2026-03-31T22:00:00-04:00", "Yesterday")
    ])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    assert "08:00 to 22:00" in result


def test_event_spanning_into_the_day_is_clamped():
    service = _mock_service_with_events([
        _event("2026-03-31T23:00:00-04:00", "2026-04-01T09:00:00-04:00", "Overnight")
    ])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    # Busy 00:00-09:00, plus buffer, so the day opens at 09:15 rather than 08:00.
    assert "09:15 to 22:00" in result


def test_event_spanning_out_of_the_day_is_clamped():
    service = _mock_service_with_events([
        _event("2026-04-01T21:00:00-04:00", "2026-04-02T02:00:00-04:00", "Late")
    ])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    assert "08:00 to 21:00" in result
    assert "22:00" not in result.split("08:00 to 21:00")[1]


def test_all_day_event_does_not_block_slots():
    service = _mock_service_with_events([
        {"start": {"date": "2026-04-01"}, "end": {"date": "2026-04-02"}, "summary": "Holiday"}
    ])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    assert "08:00 to 22:00" in result


def test_free_slots_invalid_date():
    result = get_tool("get_free_slots", MagicMock()).invoke({"date": "April 1st"})
    assert "Error" in result


# --- event listing ----------------------------------------------------------


def test_get_events_renders_times_in_the_users_zone():
    service = _mock_service_with_events([
        _event("2026-04-01T09:00:00-04:00", "2026-04-01T10:00:00-04:00", "Standup")
    ])
    result = get_tool("get_calendar_events", service).invoke({"date": "2026-04-01"})
    assert "09:00 to 10:00" in result


def test_get_events_converts_offsets_to_the_users_zone():
    """The same instant expressed in a different offset must render as local time."""
    service = _mock_service_with_events([
        _event("2026-04-01T13:00:00+00:00", "2026-04-01T14:00:00+00:00", "Standup")
    ])
    result = get_tool("get_calendar_events", service).invoke({"date": "2026-04-01"})
    assert "09:00 to 10:00" in result


def test_get_events_empty_calendar():
    service = _mock_service_with_events([])
    result = get_tool("get_calendar_events", service).invoke({"date": "2026-04-01"})
    assert "free" in result.lower()


def test_get_events_invalid_date():
    result = get_tool("get_calendar_events", MagicMock()).invoke({"date": "tomorrow"})
    assert "Error" in result


# --- event creation ---------------------------------------------------------


def test_create_event_uses_the_users_timezone():
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {}
    get_tool("create_calendar_event", service, BERLIN).invoke({
        "title": "Gym",
        "date": "2026-04-01",
        "start_time": "09:00",
        "end_time": "10:00",
    })

    body = service.events.return_value.insert.call_args.kwargs["body"]
    assert body["start"]["timeZone"] == BERLIN
    assert body["end"]["timeZone"] == BERLIN


def test_create_event_success():
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {}
    result = get_tool("create_calendar_event", service).invoke({
        "title": "Gym",
        "date": "2026-04-01",
        "start_time": "09:00",
        "end_time": "10:00",
    })
    assert "Created" in result
    assert "Gym" in result


def test_create_event_invalid_time_format():
    result = get_tool("create_calendar_event", MagicMock()).invoke({
        "title": "Gym",
        "date": "2026-04-01",
        "start_time": "9am",
        "end_time": "10am",
    })
    assert "Error" in result


def test_create_event_end_before_start():
    result = get_tool("create_calendar_event", MagicMock()).invoke({
        "title": "Gym",
        "date": "2026-04-01",
        "start_time": "10:00",
        "end_time": "09:00",
    })
    assert "Error" in result


def test_create_event_invalid_date():
    result = get_tool("create_calendar_event", MagicMock()).invoke({
        "title": "Gym",
        "date": "April 1st",
        "start_time": "09:00",
        "end_time": "10:00",
    })
    assert "Error" in result
