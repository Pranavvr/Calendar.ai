from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI # noqa: E402
from pydantic import BaseModel # noqa: E402
from agent.graph import agent # noqa: E402
from config import RECURSION_LIMIT # noqa: E402

app = FastAPI(title="cal.ai", description="AI calendar scheduling agent")


class ScheduleRequest(BaseModel):
    message: str


class ScheduleResponse(BaseModel):
    result: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/schedule", response_model=ScheduleResponse)
def schedule(request: ScheduleRequest):
    result = ""

    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": request.message}]},
        stream_mode="values",
        config={"recursion_limit": RECURSION_LIMIT}
    ):
        last_msg = chunk["messages"][-1]
        if type(last_msg).__name__ == "AIMessage" and last_msg.content:
            result = last_msg.content

    return ScheduleResponse(result=result)