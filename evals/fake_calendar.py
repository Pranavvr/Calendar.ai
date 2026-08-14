"""
A stateful stand-in for the Google Calendar API.

The unit tests use MagicMock, which returns whatever it was told to return
regardless of the query. That is fine for checking a tool formats its output, but
it cannot catch the failures that matter for scheduling, because the mock never
*stores* anything and never *filters* by the requested window.

This double does both:

  - insert() actually persists the event, so the calendar's final state can be
    checked for double-bookings.
  - list() honours timeMin/timeMax the way Google does, returning only events
    that overlap the requested window.

That second property is what gives the harness teeth. The timezone bug — where
the tools queried a UTC day for a US Eastern user — would have been caught here:
the tool would have asked for the wrong window, this fake would have withheld the
8pm event exactly as Google did, and the overlap check would have flagged the
resulting double-booking.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class FakeCalendarError(Exception):
    pass


class FakeCalendar:
    """
    Mimics the slice of googleapiclient's Resource that the tools actually use:
    service.events().list(...).execute(), service.events().insert(...).execute(),
    and service.calendars().get(...).execute().
    """

    def __init__(self, timezone_name: str = "America/New_York", events=None):
        self.timezone_name = timezone_name
        self.tz = ZoneInfo(timezone_name)
        self._events: list[dict] = []
        self.list_calls: list[dict] = []
        self.insert_calls: list[dict] = []

        for e in events or []:
            self._store(e)

    # --- seeding -----------------------------------------------------------

    def add_timed_event(self, summary: str, start: str, end: str) -> None:
        """`start`/`end` are local wall-clock 'YYYY-MM-DD HH:MM' in this calendar's zone."""
        self._store({
            "summary": summary,
            "start": {"dateTime": self._to_iso(start)},
            "end": {"dateTime": self._to_iso(end)},
        })

    def add_all_day_event(self, summary: str, date: str) -> None:
        self._store({
            "summary": summary,
            "start": {"date": date},
            "end": {"date": date},
        })

    def _to_iso(self, wall_clock: str) -> str:
        naive = datetime.strptime(wall_clock, "%Y-%m-%d %H:%M")
        return naive.replace(tzinfo=self.tz).isoformat()

    def _store(self, event: dict) -> None:
        self._events.append(event)

    # --- inspection --------------------------------------------------------

    @property
    def timed_events(self) -> list[dict]:
        """Stored events that occupy a time range, sorted by start."""
        out = []
        for e in self._events:
            start = e.get("start", {}).get("dateTime")
            end = e.get("end", {}).get("dateTime")
            if not start or not end:
                continue
            out.append({
                "summary": e.get("summary", "Untitled"),
                "start": datetime.fromisoformat(start).astimezone(self.tz),
                "end": datetime.fromisoformat(end).astimezone(self.tz),
            })
        return sorted(out, key=lambda e: e["start"])

    @property
    def created_events(self) -> list[dict]:
        """Only the events the agent inserted, not the seeded ones."""
        created = []
        for call in self.insert_calls:
            body = call["body"]
            start = body["start"]["dateTime"]
            end = body["end"]["dateTime"]
            tz = ZoneInfo(body["start"].get("timeZone", self.timezone_name))
            created.append({
                "summary": body.get("summary", "Untitled"),
                # The app sends naive local time plus an explicit timeZone, which
                # is what Google resolves; mirror that resolution here.
                "start": datetime.fromisoformat(start).replace(tzinfo=tz),
                "end": datetime.fromisoformat(end).replace(tzinfo=tz),
            })
        return sorted(created, key=lambda e: e["start"])

    # --- google api surface ------------------------------------------------

    def events(self):
        return _EventsResource(self)

    def calendars(self):
        return _CalendarsResource(self)


class _Executable:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class _EventsResource:
    def __init__(self, cal: FakeCalendar):
        self._cal = cal

    def list(self, **kwargs):
        self._cal.list_calls.append(kwargs)

        def run():
            time_min = kwargs.get("timeMin")
            time_max = kwargs.get("timeMax")
            if not time_min or not time_max:
                raise FakeCalendarError("list() requires timeMin and timeMax")

            lo = datetime.fromisoformat(time_min)
            hi = datetime.fromisoformat(time_max)
            if lo.tzinfo is None or hi.tzinfo is None:
                # Google rejects naive RFC3339; so should the fake, otherwise the
                # harness would silently accept a bug it exists to catch.
                raise FakeCalendarError("timeMin/timeMax must be offset-aware")

            items = []
            for e in self._cal._events:
                start = e.get("start", {}).get("dateTime")
                end = e.get("end", {}).get("dateTime")

                if not start or not end:
                    # All-day event: Google returns it if its date falls in range.
                    day = e.get("start", {}).get("date")
                    if day:
                        as_dt = datetime.fromisoformat(day).replace(tzinfo=self._cal.tz)
                        if lo <= as_dt < hi:
                            items.append(e)
                    continue

                s = datetime.fromisoformat(start)
                t = datetime.fromisoformat(end)
                # Overlap, not containment — matching Google's behaviour, which is
                # why events spanning the day boundary reach the caller.
                if t > lo and s < hi:
                    items.append(e)

            if kwargs.get("orderBy") == "startTime":
                items = sorted(
                    items,
                    key=lambda e: e.get("start", {}).get("dateTime")
                    or e.get("start", {}).get("date", ""),
                )
            return {"items": items}

        return _Executable(run)

    def insert(self, **kwargs):
        self._cal.insert_calls.append(kwargs)

        def run():
            body = kwargs.get("body")
            if not body:
                raise FakeCalendarError("insert() requires a body")
            for side in ("start", "end"):
                if "dateTime" not in body.get(side, {}):
                    raise FakeCalendarError(f"insert() body.{side} needs dateTime")
                if "timeZone" not in body.get(side, {}):
                    # Without a timeZone, a naive dateTime is ambiguous and Google
                    # falls back to the calendar default — a real bug source.
                    raise FakeCalendarError(f"insert() body.{side} needs timeZone")

            tz = ZoneInfo(body["start"]["timeZone"])
            stored = {
                "summary": body.get("summary", "Untitled"),
                "start": {
                    "dateTime": datetime.fromisoformat(
                        body["start"]["dateTime"]
                    ).replace(tzinfo=tz).isoformat()
                },
                "end": {
                    "dateTime": datetime.fromisoformat(
                        body["end"]["dateTime"]
                    ).replace(tzinfo=tz).isoformat()
                },
            }
            self._cal._store(stored)
            return stored

        return _Executable(run)


class _CalendarsResource:
    def __init__(self, cal: FakeCalendar):
        self._cal = cal

    def get(self, **kwargs):
        return _Executable(lambda: {
            "id": kwargs.get("calendarId", "primary"),
            "timeZone": self._cal.timezone_name,
        })


def minutes(td: timedelta) -> float:
    return td.total_seconds() / 60
