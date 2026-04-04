from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing import Annotated
from typing_extensions import TypedDict

from tools.calendar_tools import get_calendar_events, get_free_slots, create_calendar_event
from agent.prompts import get_system_prompt
from config import MODEL_NAME


# 1. State
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# 2. Tools
tools = [get_free_slots, get_calendar_events, create_calendar_event]
llm   = ChatOpenAI(model=MODEL_NAME).bind_tools(tools)


# 3. Nodes
def agent_node(state: AgentState):
    messages = state["messages"]
    
    # inject system prompt if not already there
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=get_system_prompt())] + messages
    
    response = llm.invoke(messages)
    return {"messages": [response]}


def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# 4. Build the graph
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "agent")
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("agent", should_continue)

    return graph.compile()


agent = build_graph()