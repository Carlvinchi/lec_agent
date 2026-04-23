#!/usr/bin/env python
"""
Demonstrates multi-turn memory: each query builds on the previous session_summary.
Uses AsyncSqliteSaver for persistent storage across runs.

Run:
    python scripts/demo_multiturn.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from agent.state import initial_state
from agent.budget import BudgetTracker
from agent.graph import build_graph
from tools import TOOLS

_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RESET  = "\033[0m"


def _get_review_decision() -> dict:
    """Read a single approve/reject decision from stdin."""
    try:
        raw = input(f"{_GREEN}Your decision:{_RESET} ").strip()
    except EOFError:
        # Non-interactive context (piped stdin) — default to approve.
        raw = ""
    if not raw or raw.lower() == "approve":
        print(f"{_GREEN}✓ Approved — executing plan.{_RESET}\n")
        return {"action": "approve"}
    print(f"{_YELLOW}✗ Rejected — replanning with your feedback.{_RESET}\n")
    return {"action": "reject", "feedback": raw}

SESSION = "session_demo_002"

QUERIES = [
    "Compare 2023 Q3 revenue growth of Apple vs Microsoft, adjust for inflation, and summarize analyst sentiment."
]


async def main():
    tracker = BudgetTracker(budget_dollars=2.00)
    dedup: dict = {}

    async with AsyncSqliteSaver.from_conn_string("memory/conversations.db") as checkpointer:
        graph = build_graph(
            tools=TOOLS,
            tracker=tracker,
            dedup_cache=dedup,
            strategy="plan_then_execute",
            prompt_version="v1",
            checkpointer=checkpointer,
        )

        session_summary = None
        turns = 0

        for i, query in enumerate(QUERIES):
            print(f"\n{'='*60}")
            print(f"Turn {i + 1}: {query}")
            if session_summary:
                print(f"[Prior context: {session_summary[:80]}...]")

            state = initial_state(
                query,
                f"demo_{i + 1}",
                conversation_turns=turns,
                session_summary=session_summary,
            )
            config = {"configurable": {"thread_id": SESSION}}
            result = await graph.ainvoke(state, config=config)

            # Human-in-the-loop: handle one or more plan-review interrupts.
            while result.get("__interrupt__"):
                decision = _get_review_decision()
                result = await graph.ainvoke(
                    Command(resume=decision), config=config
                )

            session_summary = result["session_summary"]
            turns = result["conversation_turns"]

            print(f"Answer: {result['final_answer']}")
            print(f"Summary stored: {(session_summary or '')[:100]}...")
            print(f"Cost so far: ${tracker.snapshot()['dollars_spent']:.4f}")

    print(f"\nTotal cost: ${tracker.snapshot()['dollars_spent']:.4f}")
    print(f"Total tokens: {tracker.snapshot()['tokens_used']}")


if __name__ == "__main__":
    asyncio.run(main())
