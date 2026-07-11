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
from tools.calendar_tools import make_calendar_tools_for_user


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


async def make_agent(user_id: uuid.UUID, db: AsyncSession):
    """
    Build a LangGraph agent that operates on the given user's calendar.

    The tools are pre-bound to a Google Calendar client built from the user's
    refresh_token, so the LLM doesn't see (or need) the user identity.
    """
    tools = await make_calendar_tools_for_user(user_id, db)
    llm = ChatOpenAI(model=MODEL_NAME).bind_tools(tools)

    def agent_node(state: AgentState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=get_system_prompt())] + messages
        response = llm.invoke(messages)
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

    return graph.compile()
