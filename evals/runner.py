"""
Runs eval cases against the real agent and scores the results.

Requires an OpenAI key and costs money, so it is not part of the test suite.
Invoke explicitly:

    .venv/bin/python -m evals.runner
    .venv/bin/python -m evals.runner --case evening_conflict --repeat 5

Repeating matters. The agent is non-deterministic, so a single pass proves very
little: a case that passes once and fails once is not a passing case. The report
gives a pass rate per case, and the exit code is non-zero if any case is not
perfect across its runs.

Scoring is on the calendar's final state, not on what the model claimed. An agent
can describe a conflict-free schedule while having inserted an overlapping event.
"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agent.graph import AgentState
from agent.prompts import get_system_prompt
from config import (
    BUFFER_MINUTES,
    DAY_END_HOUR,
    DAY_START_HOUR,
    MODEL_NAME,
    RECURSION_LIMIT,
)
from evals.cases import CASES, EvalCase, case_by_name
from evals.fake_calendar import FakeCalendar
from evals.invariants import Violation, check_all
from tools.calendar_tools import make_calendar_tools


@dataclass
class RunResult:
    case: EvalCase
    violations: list[Violation]
    created_count: int
    error: str | None = None

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        if self.violations:
            return False
        if self.case.expect_created is not None:
            return self.created_count == self.case.expect_created
        return True


def _build_agent(calendar: FakeCalendar, timezone_name: str):
    """
    Mirror agent.graph.make_agent, but over the fake calendar.

    Deliberately not calling make_agent: that resolves credentials and a timezone
    from the database. The graph shape and prompt are the parts under test, so
    they are reproduced rather than mocked around.
    """
    tools = make_calendar_tools(calendar, timezone_name)
    llm = ChatOpenAI(model=MODEL_NAME).bind_tools(tools)

    def agent_node(state: AgentState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=get_system_prompt(timezone_name))] + messages
        return {"messages": [llm.invoke(messages)]}

    def should_continue(state: AgentState):
        return "tools" if state["messages"][-1].tool_calls else END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("agent", should_continue)
    return graph.compile()


async def run_case(case: EvalCase) -> RunResult:
    calendar = FakeCalendar(timezone_name=case.timezone_name)
    for summary, start, end in case.existing:
        calendar.add_timed_event(summary, start, end)
    for summary, date in case.all_day:
        calendar.add_all_day_event(summary, date)

    agent = _build_agent(calendar, case.timezone_name)

    try:
        await agent.ainvoke(
            {"messages": [{"role": "user", "content": case.request}]},
            config={"recursion_limit": RECURSION_LIMIT},
        )
    except Exception as e:
        return RunResult(case, [], 0, error=f"{type(e).__name__}: {e}")

    violations = check_all(
        all_events=calendar.timed_events,
        created_events=calendar.created_events,
        timezone_name=case.timezone_name,
        day_start_hour=DAY_START_HOUR,
        day_end_hour=DAY_END_HOUR,
        buffer_minutes=BUFFER_MINUTES,
    )
    return RunResult(case, violations, len(calendar.created_events))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run cal.ai agent evals.")
    parser.add_argument("--case", help="Run a single case by name.")
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Runs per case. The agent is non-deterministic; one pass proves little.",
    )
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. These evals call the real model.", file=sys.stderr)
        return 2

    cases = [case_by_name(args.case)] if args.case else CASES

    print(f"Running {len(cases)} case(s) x {args.repeat} against {MODEL_NAME}\n")

    failures = 0
    for case in cases:
        results = [await run_case(case) for _ in range(args.repeat)]
        passed = sum(1 for r in results if r.passed)
        mark = "PASS" if passed == len(results) else "FAIL"
        print(f"[{mark}] {case.name}  {passed}/{len(results)}")

        if passed != len(results):
            failures += 1
            print(f"       why it matters: {case.why}")
            for i, r in enumerate(results):
                if r.passed:
                    continue
                if r.error:
                    print(f"       run {i + 1}: errored - {r.error}")
                    continue
                if (
                    r.case.expect_created is not None
                    and r.created_count != r.case.expect_created
                ):
                    print(
                        f"       run {i + 1}: created {r.created_count}, "
                        f"expected {r.case.expect_created}"
                    )
                for v in r.violations:
                    print(f"       run {i + 1}: {v}")
            print()

    total = len(cases)
    print(f"\n{total - failures}/{total} cases fully passing")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
