# cal.ai

An AI calendar scheduling agent that takes natural-language requests (e.g. *"Gym, study 2 hours, groceries"*) and books them onto your Google Calendar, working around existing events and respecting buffer time.

Built with [LangGraph](https://langchain-ai.github.io/langgraph/), the Google Calendar API, and a FastAPI HTTP wrapper.

## How it works

The agent is a LangGraph ReAct loop with three tools:

- `get_calendar_events(date)` — list everything already booked on a day
- `get_free_slots(date)` — compute open windows between events, accounting for a configurable buffer
- `create_calendar_event(title, date, start_time, end_time)` — book a new event

The model is instructed to always check free slots before scheduling, and never to double-book.

## Project layout

```
agent/    LangGraph graph + system prompt
api/      FastAPI app (POST /schedule, GET /health)
auth/     Google OAuth flow (token caching to token.json)
tools/    Calendar tools exposed to the agent
config.py Timezone, model, day window, buffer, recursion limit
main.py   CLI entrypoint
```

## Setup

1. **Google Calendar credentials.** Create an OAuth client (Desktop app) in Google Cloud Console and download it as `credentials.json` in the repo root. On first run the auth flow caches a token to `token.json`.

2. **Environment.** Copy `.env.example` to `.env` and set your model API key (`OPENAI_API_KEY` by default; switch the model via `MODEL_NAME` in [config.py](config.py)).

3. **Install.**
   ```sh
   pip install -r requirements.txt
   ```

## Run

CLI:
```sh
python main.py
```

HTTP API:
```sh
uvicorn api.main:app --reload
# POST http://localhost:8000/schedule {"message": "gym at 7am, study 2 hours"}
```

Docker:
```sh
docker build -t cal-ai .
docker run -p 8000:8000 --env-file .env cal-ai
```

## Configuration

Tunables live in [config.py](config.py):

| Setting | Default | Meaning |
| --- | --- | --- |
| `TIMEZONE` | `America/New_York` | Timezone for created events |
| `MODEL_NAME` | `gpt-4o-mini` | LLM driving the agent |
| `DAY_START_HOUR` / `DAY_END_HOUR` | `8` / `22` | Bounds of the schedulable day |
| `BUFFER_MINUTES` | `15` | Padding inserted between events |
| `RECURSION_LIMIT` | `10` | Max agent steps per request |

## Tests

```sh
pytest
```
