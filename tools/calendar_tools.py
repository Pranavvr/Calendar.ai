import re
import uuid
from datetime import datetime

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from auth.google_auth import get_calendar_service_for_user
from config import BUFFER_MINUTES, DAY_END_HOUR, DAY_START_HOUR


def make_calendar_tools(service):
    """
    Build the three calendar tools with `service` closed over.

    `service` is a Google Calendar API client (googleapiclient.discovery.Resource).
    Use `make_calendar_tools_for_user(user_id, db)` for the per-user wiring;
    use this directly when you have a mock service (tests).
    """

    @tool
    def get_calendar_events(date: str) -> str:
        """
        Get all calendar events for a given date.
        Always call this to see what is already booked on a given date.

        Args:
            date: "today" or a date in YYYY-MM-DD format e.g. "2026-03-31"
        """
        try:
            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            datetime.strptime(date, "%Y-%m-%d")

            result = service.events().list(
                calendarId="primary",
                timeMin=f"{date}T00:00:00Z",
                timeMax=f"{date}T23:59:59Z",
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = result.get("items", [])

            if not events:
                return f"No events on {date}. Full day is free."

            summary = f"Events on {date}:\n"
            for e in events:
                start_time = e["start"].get("dateTime", "all-day")
                end_time   = e["end"].get("dateTime", "")
                title      = e.get("summary", "Untitled")
                if start_time != "all-day":
                    start_time = start_time[11:16]
                    end_time   = end_time[11:16]
                    summary += f"  - {title}: {start_time} to {end_time}\n"
                else:
                    summary += f"  - {title}: all day\n"

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
            if date == "today":
                date = datetime.now().strftime("%Y-%m-%d")

            datetime.strptime(date, "%Y-%m-%d")

            result = service.events().list(
                calendarId="primary",
                timeMin=f"{date}T00:00:00Z",
                timeMax=f"{date}T23:59:59Z",
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = result.get("items", [])

            DAY_START = DAY_START_HOUR * 60
            DAY_END   = DAY_END_HOUR   * 60
            BUFFER    = BUFFER_MINUTES

            busy = []
            for e in events:
                start_str = e["start"].get("dateTime")
                end_str   = e["end"].get("dateTime")
                if not start_str:
                    continue
                s  = int(start_str[11:13]) * 60 + int(start_str[14:16])
                en = int(end_str[11:13])   * 60 + int(end_str[14:16])
                busy.append((s, en))

            busy.sort()

            free_slots = []
            current = DAY_START

            for event_start, event_end in busy:
                if current < event_start:
                    free_slots.append((current, event_start))
                current = max(current, event_end + BUFFER)

            if current < DAY_END:
                free_slots.append((current, DAY_END))

            if not free_slots:
                return f"No free slots on {date}. Day is fully booked."

            def to_time(m):
                return f"{m // 60:02d}:{m % 60:02d}"

            output = f"Free slots on {date}:\n"
            for s, e in free_slots:
                duration = e - s
                output += f"  - {to_time(s)} to {to_time(e)} ({duration} min available)\n"

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

            event = {
                "summary": title,
                "start": {
                    "dateTime": f"{date}T{start_time}:00",
                    "timeZone": "America/New_York",
                },
                "end": {
                    "dateTime": f"{date}T{end_time}:00",
                    "timeZone": "America/New_York",
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


async def make_calendar_tools_for_user(user_id: uuid.UUID, db: AsyncSession):
    service = await get_calendar_service_for_user(user_id, db)
    return make_calendar_tools(service)
