from unittest.mock import MagicMock

from tools.calendar_tools import make_calendar_tools


def get_tool(name, service):
    tools = make_calendar_tools(service)
    return next(t for t in tools if t.name == name)


def _mock_service_with_events(items):
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": items}
    return service


def test_free_slots_empty_calendar():
    service = _mock_service_with_events([])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    assert "08:00" in result
    assert "22:00" in result


def test_free_slots_respects_buffer():
    service = _mock_service_with_events([{
        "start":   {"dateTime": "2026-04-01T09:00:00Z"},
        "end":     {"dateTime": "2026-04-01T10:00:00Z"},
        "summary": "Meeting",
    }])
    result = get_tool("get_free_slots", service).invoke({"date": "2026-04-01"})
    assert "10:15" in result


def test_free_slots_invalid_date():
    result = get_tool("get_free_slots", MagicMock()).invoke({"date": "April 1st"})
    assert "Error" in result


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


def test_get_events_empty_calendar():
    service = _mock_service_with_events([])
    result = get_tool("get_calendar_events", service).invoke({"date": "2026-04-01"})
    assert "free" in result.lower()


def test_get_events_invalid_date():
    result = get_tool("get_calendar_events", MagicMock()).invoke({"date": "tomorrow"})
    assert "Error" in result
