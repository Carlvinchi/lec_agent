from __future__ import annotations
import json
import numpy as np
from langchain_core.messages import ToolMessage, AIMessage, HumanMessage
from sentence_transformers import SentenceTransformer
from agent.state import AgentState
from agent.budget import NO_PROGRESS_THRESHOLD

from agent.prompt_loader import PromptLoader

MAX_ITERATIONS = 5

_embedder = SentenceTransformer("all-MiniLM-L6-v2")
_loader = PromptLoader()


def _cosine(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _current_tool_messages(messages: list) -> list[ToolMessage]:
    """Collect ToolMessages from the most recent tool-call batch only."""
    results = []
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            results.append(msg)
        elif isinstance(msg, AIMessage) and msg.tool_calls:
            break
    return list(reversed(results))


def _all_tool_messages(messages: list) -> list[ToolMessage]:
    """Collect all ToolMessages across every iteration."""
    return [m for m in messages if isinstance(m, ToolMessage)]


def _normalize_python_literals(text: str) -> str:
    """Replace Python-style True/False/None with JSON equivalents."""
    import re
    text = re.sub(r'\bTrue\b', 'true', text)
    text = re.sub(r'\bFalse\b', 'false', text)
    text = re.sub(r'\bNone\b', 'null', text)
    return text


def _extract_json_object(text: str) -> dict:
    if not isinstance(text, str):
        return {}
    text = text.strip()

    # Remove markdown fences if the model wrapped the JSON in code blocks.
    if text.startswith("```") and text.rstrip().endswith("```"):
        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]

    text = _normalize_python_literals(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first balanced JSON object in the text.
    start = text.find("{")
    while start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return {}


async def reflector_node(
    state: AgentState,
    llm_reflector,
    version: str = "v1",
    tracker=None,
) -> dict:
    # Pass the full accumulated evidence so the reflector can assess completeness
    # across all loop iterations, not just the most recent batch.
    all_tool_msgs = _all_tool_messages(state["messages"])
    current_tool_msgs = _current_tool_messages(state["messages"])

    # Show all evidence gathered so far; mark current-iteration results clearly.
    current_ids = {m.tool_call_id for m in current_tool_msgs}
    obs_lines = []
    for msg in all_tool_msgs:
        tag = "[NEW]" if msg.tool_call_id in current_ids else "[PRIOR]"
        obs_lines.append(f"{tag} [{msg.name or 'tool'}] {str(msg.content)}")
    obs_summary = "\n".join(obs_lines)

    prompt = _loader.load("reflector", version=version).render(
        query=state["query"],
        observations=obs_summary,
        remaining_budget=f"${state['remaining_budget_dollars']:.4f}",
    )
    response = await llm_reflector.ainvoke([HumanMessage(content=prompt)])

    if tracker is not None:
        usage = response.usage_metadata or {}
        model_id = (response.response_metadata or {}).get("model_name", "gpt-4o-mini")
        tracker.record_llm_call(
            model_id=model_id,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
        )

    parsed = _extract_json_object(response.content)
    print(f"Reflector raw response:\n{response.content}\n")
    print(f"Reflector response:\nParsed:\n parsed={parsed}\n")
 
    is_complete = parsed.get("is_complete", False)
    gap = parsed.get("gap")
    next_step = parsed.get("next_step")
    reasoning = parsed.get("reasoning", "")


    new_iteration = state["iteration"] + 1

    prev_gap = state.get("gap_identified")
    termination_reason = None
    if gap and prev_gap:
        sim = _cosine(_embedder.encode(gap), _embedder.encode(prev_gap))
        if sim >= NO_PROGRESS_THRESHOLD:
            termination_reason = "no_progress"

    if new_iteration >= MAX_ITERATIONS:
        is_complete = True
        termination_reason = termination_reason or "max_iterations_reached"

    return {
        "is_complete": is_complete,
        "gap_identified": next_step or gap,
        "reflection_notes": state["reflection_notes"] + [reasoning] + ([gap] if gap else []) + ([next_step] if next_step else []),
        "iteration": new_iteration,
        "terminated": termination_reason is not None,
        "termination_reason": termination_reason,
        "tokens_used": tracker.snapshot()["tokens_used"],
        "dollars_spent": tracker.snapshot()['dollars_spent']
    }


def route_after_reflector(state: AgentState) -> str:
    if state["terminated"]:  return "terminate"
    if state["is_complete"]: return "terminate"
    return "planner"
