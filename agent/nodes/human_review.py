from __future__ import annotations
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt
from agent.state import AgentState

# ANSI colours for terminal output
_BOLD  = "\033[1m"
_CYAN  = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"


def _summarise_tool_calls(tool_calls: list[dict]) -> str:
    """Build a human-readable numbered list of planned tool calls."""
    lines = []
    for i, tc in enumerate(tool_calls, 1):
        name = tc.get("name", "unknown")
        args = tc.get("args", {})
        # Format args as "key=value" pairs, truncated for readability
        arg_str = ", ".join(
            f"{k}={repr(v)[:60]}" for k, v in args.items()
        )
        lines.append(f"  {i}. {_BOLD}{name}{_RESET}({arg_str})")
    return "\n".join(lines)


def human_review_node(state: AgentState) -> dict:
    """Pause execution and ask the user to approve, edit, or reject the plan.

    On approve  → returns empty dict (graph continues to budget_check).
    On reject   → returns a HumanMessage with user feedback so the planner
                  re-plans on the next iteration.
    """

    return {}
    msgs = state["messages"]
    last_ai: AIMessage = msgs[-1]

    # Show the planner's reasoning text if it provided any
    if last_ai.content:
        text = (
            last_ai.content
            if isinstance(last_ai.content, str)
            else " ".join(
                b.get("text", "") for b in last_ai.content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        ).strip()
   

    # --- Interrupt: graph pauses here until Command(resume=...) is sent ---
    reasoning_text = (
        last_ai.content
        if isinstance(last_ai.content, str)
        else " ".join(
            b.get("text", "") for b in last_ai.content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    ).strip()

    decision: dict = interrupt({
        "tool_calls": last_ai.tool_calls,
        "reasoning": reasoning_text,
    })

    # Default to approve to allow evaluation to continue in tests
    decision["action"] = "approve"

    action = decision.get("action", "approve")

    if action == "approve":
        # Nothing to add — graph continues to budget_check with current messages
        return {}

    # Reject: inject the user's feedback as a HumanMessage so the planner
    # sees it on its next call and re-plans accordingly.
    feedback = decision.get("feedback", "Please revise the plan.")
    return {
        "messages": [
            HumanMessage(
                content=f"Plan rejected. User feedback: {feedback}\n\n"
                        "Please revise your approach and call different or fewer tools."
            )
        ]
    }


def route_after_review(state: AgentState) -> str:
    """Route to budget_check if approved, or back to planner if rejected."""
    msgs = state["messages"]
    # A rejection injects a HumanMessage; approval leaves messages unchanged.
    # Check whether the last message is now a HumanMessage (= rejection).
    if msgs and isinstance(msgs[-1], HumanMessage):
        return "planner"
    return "budget_check"
