from __future__ import annotations
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    # identity
    query: str
    query_id: str

    # reflection
    is_complete: bool
    gap_identified: str | None
    reflection_notes: list[str]
    iteration: int

    # control
    terminated: bool
    termination_reason: str | None

    # budget — updated each iteration via tracker.snapshot()
    tokens_used: int
    dollars_spent: float
    remaining_budget_dollars: float
    wall_time_s: float
    tool_call_count: int
    cache_creation_tokens: int
    cache_read_tokens: int

    # output
    final_answer: str | None

    # memory — persisted by SqliteSaver across turns
    session_summary: str | None
    conversation_turns: int

    # append-only audit logs — never sent to LLM
    observation_log: list
    full_tool_log: list


def initial_state(
    query: str,
    query_id: str,
    conversation_turns: int = 0,
    session_summary: str | None = None,
) -> dict:
    return {
        "messages": [],
        "query": query,
        "query_id": query_id,
        "is_complete": False,
        "gap_identified": None,
        "reflection_notes": [],
        "iteration": 0,
        "terminated": False,
        "termination_reason": None,
        "tokens_used": 0,
        "dollars_spent": 0.0,
        "remaining_budget_dollars": 0.50,
        "wall_time_s": 0.0,
        "tool_call_count": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "final_answer": None,
        "session_summary": session_summary,
        "conversation_turns": conversation_turns,
        "observation_log": [],
        "full_tool_log": [],
    }
