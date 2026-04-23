from __future__ import annotations
from agent.state import AgentState
from agent.budget import BudgetTracker


def budget_check_node(state: AgentState, tracker: BudgetTracker) -> dict:
    reason = tracker.check_caps(
        iteration=state["iteration"],
        conversation_turns=state["conversation_turns"],
    )
    if reason:
        return {"terminated": True, 
                "termination_reason": reason,
                **tracker.snapshot()
                }
    
    return {**tracker.snapshot()}


def route_after_budget(state: AgentState) -> str:
    return "terminate"  if state["terminated"] else "tools"
