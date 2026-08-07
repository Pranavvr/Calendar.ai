import re
import uuid
from datetime import date as _Date
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from auth.google_auth import get_calendar_service_for_user
from config import BUFFER_MINUTES, DAY_END_HOUR, DAY_START_HOUR, TIMEZONE
from db.models import User

MINUTES_PER_DAY = 24 * 60


def _resolve_date(date: str, tz: ZoneInfo) -> _Date:
    """"today" or YYYY-MM-DD -> a calendar date in the user's zone."""
    if date == "today":
        return datetime.now(tz).date()
    return datetime.strptime(date, "%Y-%m-%d").date()


def _day_window(target: _Date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """
    Midnight-to-midnight in the user's zone, as offset-aware datetimes.

    Google is queried with these rather than a UTC day, because a UTC day is a
    different span of real time: for a US Eastern user, 00:00Z-23:59Z runs from
    8pm the previous evening to 8pm on the requested day. That both hid real
    evening events and let the previous day's events leak in.

    Adding timedelta(days=1) does wall-clock arithmetic, so this stays
    midnight-to-midnight across DST transitions.
    """
    start = datetime.combine(target, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def _list_events(service, target: _Date, tz: ZoneInfo) -> list[dict]:
    start, end = _day_window(target, tz)
    result = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def _busy_intervals(events: list[dict], target: _Date, tz: ZoneInfo) -> list[tuple[int, int]]:
    """
    Timed events as (start, end) wall-clock minutes past midnight on `target`.

    Google returns offset-aware timestamps (e.g. "...T09:00:00-04:00"), so they
    are parsed and converted rather than string-sliced. Events overlapping the
    window from an adjacent day are clamped to this day's bounds.
    """
    day_start, day_end = _day_window(target, tz)
    busy: list[tuple[int, int]] = []

    for e in events:
        start_str = e.get("start", {}).get("dateTime")
        end_str = e.get("end", {}).get("dateTime")
        if not start_str or not end_str:
            continue  # all-day event: no timed span to block out

        start_local = datetime.fromisoformat(start_str).astimezone(tz)
        end_local = datetime.fromisoformat(end_str).astimezone(tz)

        # Ignore anything that does not actually overlap this day. Compared as
        # instants, not dates: an event wholly on the previous evening shares no
        # time with this day and must not block it.
        if end_local <= day_start or start_local >= day_end:
            continue

        clamped_start = max(start_local, day_start)
        clamped_end = min(end_local, day_end)

        s = 0 if clamped_start <= day_start else clamped_start.hour * 60 + clamped_start.minute
        # Midnight-next-day reads as 00:00, so express it as the end of this day.
        e_min = (
            MINUTES_PER_DAY
            if clamped_end >= day_end
            else clamped_end.hour * 60 + clamped_end.minute
        )

        if e_min <= s:
            continue

        busy.append((s, e_min))

    busy.sort()
    return busy


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def make_calendar_tools(service, timezone_name: str = TIMEZONE):
    """
    Build the three calendar tools with `service` and the user's timezone closed over.

    `service` is a Google Calendar API client (googleapiclient.discovery.Resource).
    `timezone_name` is an IANA name; it comes from the user's primary calendar and
    falls back to config.TIMEZONE.

    Use `make_calendar_tools_for_user(user_id, db)` for the per-user wiring;
    use this directly when you have a mock service (tests).
    """
    tz = ZoneInfo(timezone_name)

    @tool
    def get_calendar_events(date: str) -> str:
        """
        Get all calendar events for a given date.
        Always call this to see what is already booked on a given date.

        Args:
            date: "today" or a date in YYYY-MM-DD format e.g. "2026-03-31"
        """
        try:
            target = _resolve_date(date, tz)
            events = _list_events(service, target, tz)

            if not events:
                return f"No events on {target}. Full day is free."

            summary = f"Events on {target}:\n"
            for e in events:
                title = e.get("summary", "Untitled")
                start_str = e.get("start", {}).get("dateTime")
                end_str = e.get("end", {}).get("dateTime")

                if not start_str or not end_str:
                    summary += f"  - {title}: all day\n"
                    continue

                start_local = datetime.fromisoformat(start_str).astimezone(tz)
                end_local = datetime.fromisoformat(end_str).astimezone(tz)
                summary += (
                    f"  - {title}: {start_local:%H:%M} to {end_local:%H:%M}\n"
                )

            return summary

        except ValueError:
            return f"Error: invalid date format '{date}'. Use YYYY-MM-DD."
        except Exception as e:
            return f"Error accessing calendar: {str(e)}"

    @tool
    def get_free_slots(date: str) -> str:
        """
        Get all free time slots for a given date accounting for existing events
        and buffer time between events.
        ALWAYS call this first before scheduling anything.
        Use the returned free slots to decide when to create events.

        Args:
            date: "today" or a date in YYYY-MM-DD format e.g. "2026-03-31"
        """
        try:
            target = _resolve_date(date, tz)
            busy = _busy_intervals(_list_events(service, target, tz), target, tz)

            day_start = DAY_START_HOUR * 60
            day_end = DAY_END_HOUR * 60

            free_slots = []
            current = day_start

            for event_start, event_end in busy:
                if current < event_start:
                    free_slots.append((current, min(event_start, day_end)))
                current = max(current, event_end + BUFFER_MINUTES)

            if current < day_end:
                free_slots.append((current, day_end))

            # Clamp to the schedulable window and drop anything inverted or empty.
            free_slots = [
                (max(s, day_start), min(e, day_end))
                for s, e in free_slots
                if min(e, day_end) > max(s, day_start)
            ]

            if not free_slots:
                return f"No free slots on {target}. Day is fully booked."

            output = f"Free slots on {target}:\n"
            for s, e in free_slots:
                output += f"  - {_hhmm(s)} to {_hhmm(e)} ({e - s} min available)\n"

            return output

        except ValueError:
            return f"Error: invalid date format '{date}'. Use YYYY-MM-DD."
        except Exception as e:
            return f"Error getting free slots: {str(e)}"

    @tool
    def create_calendar_event(
        title: str,
        date: str,
        start_time: str,
        end_time: str,
    ) -> str:
        """
        Create a calendar event in Google Calendar.
        Only call this after checking get_free_slots to confirm the slot is free.
        Never double-book an existing event.

        Args:
            title:      Name of the event e.g. "Gym", "Study session"
            date:       Date in YYYY-MM-DD format e.g. "2026-03-31"
            start_time: Start in HH:MM 24hr format e.g. "09:00"
            end_time:   End in HH:MM 24hr format e.g. "10:00"
        """
        try:
            datetime.strptime(date, "%Y-%m-%d")

            time_pattern = re.compile(r"^\d{2}:\d{2}$")
            if not time_pattern.match(start_time):
                return f"Error: start_time '{start_time}' is invalid. Use HH:MM format e.g. 09:00"
            if not time_pattern.match(end_time):
                return f"Error: end_time '{end_time}' is invalid. Use HH:MM format e.g. 10:00"

            start_dt = datetime.strptime(f"{date}T{start_time}", "%Y-%m-%dT%H:%M")
            end_dt   = datetime.strptime(f"{date}T{end_time}",   "%Y-%m-%dT%H:%M")
            if start_dt >= end_dt:
                return f"Error: start_time {start_time} must be before end_time {end_time}."

            # Naive local time plus an explicit timeZone: Google resolves the
            # offset, which keeps this correct across DST.
            event = {
                "summary": title,
                "start": {
                    "dateTime": f"{date}T{start_time}:00",
                    "timeZone": timezone_name,
                },
                "end": {
                    "dateTime": f"{date}T{end_time}:00",
                    "timeZone": timezone_name,
                },
            }

            service.events().insert(
                calendarId="primary",
                body=event,
            ).execute()

            return f"Created '{title}' on {date} from {start_time} to {end_time}."

        except ValueError as e:
            return f"Error: invalid date or time format. {str(e)}"
        except Exception as e:
            return f"Error creating event: {str(e)}"

    return [get_calendar_events, get_free_slots, create_calendar_event]


async def resolve_user_timezone(user_id: uuid.UUID, db: AsyncSession) -> str:
    """The user's stored IANA timezone, falling back to config.TIMEZONE."""
    user = await db.get(User, user_id)
    if user is not None and user.timezone:
        return user.timezone
    return TIMEZONE


async def make_calendar_tools_for_user(
    user_id: uuid.UUID,
    db: AsyncSession,
    timezone_name: str | None = None,
):
    service = await get_calendar_service_for_user(user_id, db)
    if timezone_name is None:
        timezone_name = await resolve_user_timezone(user_id, db)
    return make_calendar_tools(service, timezone_name)
