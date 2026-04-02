from dotenv import load_dotenv

load_dotenv()

from agent.graph import agent
from config import RECURSION_LIMIT


def run(user_input: str):
    print(f"\nScheduling: '{user_input}'\n")
    
    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        stream_mode="values",
        config={"recursion_limit": RECURSION_LIMIT}
    ):
        last_msg = chunk["messages"][-1]
        msg_type = type(last_msg).__name__

        if msg_type == "AIMessage" and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                print(f"🤖 calling: {tc['name']}({tc['args']})")

        elif msg_type == "ToolMessage":
            print(f"🔧 result:  {last_msg.content}")

        elif msg_type == "AIMessage" and last_msg.content:
            print(f"\n✅ {last_msg.content}")


if __name__ == "__main__":
    run("Gym, study 2 hours, groceries")