from unittest.mock import patch
from tools.calendar_tools import get_free_slots, create_calendar_event, get_calendar_events


def test_free_slots_empty_calendar():
    with patch("tools.calendar_tools.get_calendar_service") as mock:
        mock.return_value.events.return_value.list.return_value.execute.return_value = {"items": []}
        result = get_free_slots.invoke({"date": "2026-04-01"})
        assert "08:00" in result
        assert "22:00" in result


def test_free_slots_respects_buffer():
    with patch("tools.calendar_tools.get_calendar_service") as mock:
        mock.return_value.events.return_value.list.return_value.execute.return_value = {
            "items": [{
                "start": {"dateTime": "2026-04-01T09:00:00Z"},
                "end":   {"dateTime": "2026-04-01T10:00:00Z"},
                "summary": "Meeting"
            }]
        }
        result = get_free_slots.invoke({"date": "2026-04-01"})
        assert "10:15" in result


def test_free_slots_invalid_date():
    result = get_free_slots.invoke({"date": "April 1st"})
    assert "Error" in result


def test_create_event_invalid_time_format():
    result = create_calendar_event.invoke({
        "title": "Gym",
        "date": "2026-04-01",
        "start_time": "9am",
        "end_time": "10am"
    })
    assert "Error" in result


def test_create_event_end_before_start():
    result = create_calendar_event.invoke({
        "title": "Gym",
        "date": "2026-04-01",
        "start_time": "10:00",
        "end_time": "09:00"
    })
    assert "Error" in result


def test_create_event_invalid_date():
    result = create_calendar_event.invoke({
        "title": "Gym",
        "date": "April 1st",
        "start_time": "09:00",
        "end_time": "10:00"
    })
    assert "Error" in result


def test_create_event_success():
    with patch("tools.calendar_tools.get_calendar_service") as mock:
        mock.return_value.events.return_value.insert.return_value.execute.return_value = {}
        result = create_calendar_event.invoke({
            "title": "Gym",
            "date": "2026-04-01",
            "start_time": "09:00",
            "end_time": "10:00"
        })
        assert "Created" in result
        assert "Gym" in result


def test_get_events_empty_calendar():
    with patch("tools.calendar_tools.get_calendar_service") as mock:
        mock.return_value.events.return_value.list.return_value.execute.return_value = {"items": []}
        result = get_calendar_events.invoke({"date": "2026-04-01"})
        assert "free" in result.lower()


def test_get_events_invalid_date():
    result = get_calendar_events.invoke({"date": "tomorrow"})
    assert "Error" in result