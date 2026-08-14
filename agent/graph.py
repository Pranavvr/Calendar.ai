import logging
import uuid
from typing import Annotated

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from agent.prompts import get_system_prompt
from config import MODEL_NAME
from tools.calendar_tools import make_calendar_tools_for_user, resolve_user_timezone

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


class RunUsage(TypedDict):
    """Token accounting for a single agent run."""
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int


def new_run_usage() -> RunUsage:
    return {"llm_calls": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0}


async def make_agent(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[object, RunUsage]:
    """
    Build a LangGraph agent that operates on the given user's calendar.

    The tools are pre-bound to a Google Calendar client built from the user's
    refresh_token, so the LLM doesn't see (or need) the user identity.

    Returns the compiled graph plus a usage dict that the graph mutates as it
    runs. The caller reads it after the run to log tokens and estimated cost —
    the only way to notice an agent looping expensively.
    """
    # Resolved once and shared, so the tools and the prompt cannot disagree
    # about what "today" means.
    timezone_name = await resolve_user_timezone(user_id, db)

    tools = await make_calendar_tools_for_user(user_id, db, timezone_name)
    llm = ChatOpenAI(model=MODEL_NAME).bind_tools(tools)

    usage = new_run_usage()

    def agent_node(state: AgentState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=get_system_prompt(timezone_name))] + messages
        response = llm.invoke(messages)

        usage["llm_calls"] += 1
        # usage_metadata is populated by langchain-openai; absent if a provider
        # or a stubbed model does not report it, so tolerate its absence rather
        # than failing a scheduling request over accounting.
        metadata = getattr(response, "usage_metadata", None) or {}
        usage["input_tokens"] += metadata.get("input_tokens", 0) or 0
        usage["output_tokens"] += metadata.get("output_tokens", 0) or 0

        requested = getattr(response, "tool_calls", None) or []
        usage["tool_calls"] += len(requested)
        if requested:
            logger.info(
                "agent.tool_calls_requested",
                extra={"tools": [t.get("name") for t in requested]},
            )

        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("agent", should_continue)

    logger.info("agent.built", extra={"timezone": timezone_name, "tools": len(tools)})

    return graph.compile(), usage
