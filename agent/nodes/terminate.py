from __future__ import annotations
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from agent.state import AgentState
from agent.prompt_loader import PromptLoader

_loader = PromptLoader()


def _all_tool_messages(messages: list) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage)]


async def terminate_node(
    state: AgentState,
    llm_terminate,
    version: str = "v1",
    tracker=None,
    tool_list_str: str = ""
) -> dict:
    tool_msgs = _all_tool_messages(state["messages"])
    final_answer = state["messages"][-1].content
    summary = final_answer

    if state["terminated"]:
        final_answer = f"Request terminated due to: {state['termination_reason']}."

    if tool_msgs:
        summary = await _summarise_turn(state, tool_msgs, llm_terminate, final_answer, version, tracker)

    # Append new ToolMessages to full_tool_log, deduplicating by tool_call_id.
    logged_ids = {
        entry.get("tool_call_id")
        for entry in state["full_tool_log"]
        if isinstance(entry, dict)
    }
    new_log_entries = [
        {
            "tool_call_id": msg.tool_call_id,
            "tool": msg.name,
            "content": str(msg.content)[:500],
        }
        for msg in tool_msgs
        if msg.tool_call_id not in logged_ids
    ]

    return {
        "final_answer": final_answer,
        "session_summary": summary,
        "observation_log": state["observation_log"] + [
            {"tool": msg.name, "result": str(msg.content)[:500]}
            for msg in tool_msgs
        ],
        "full_tool_log": state["full_tool_log"] + new_log_entries,
        "conversation_turns": state["conversation_turns"], 
        "tokens_used": tracker.snapshot()["tokens_used"],
        "dollars_spent": tracker.snapshot()['dollars_spent']
    }


async def _synthesise_answer(
    state: AgentState, tool_msgs: list[ToolMessage], llm, version: str, tool_list_str: str,
    tracker=None,
) -> str:
    obs_text = "\n".join(
        f"[{msg.name or 'tool'}] {msg.content}" for msg in tool_msgs
    )
    prior = state.get("session_summary") or ""
    prior_section = (
        f"Prior session context (use this for cross-turn references):\n{prior}\n\n"
        if prior else ""
    )

    query = f"Query: {state['query']}\n\nNew findings:\n{obs_text}\n\n"
    prompt = _loader.load("reporter", version=version).render(
        prior_section=prior_section,
        query=query,
        remaining_budget=f"${state['remaining_budget_dollars']:.4f}",
    ) 
   
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    if tracker is not None:
        usage = response.usage_metadata or {}
        model_id = (response.response_metadata or {}).get("model_name", "gpt-5-nano")
        tracker.record_llm_call(
            model_id=model_id,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
        )
    return response.content


async def _summarise_turn(
    state: AgentState,
    tool_msgs: list[ToolMessage],
    llm,
    final_answer: str,
    version: str,
    tracker=None,
) -> str:
    tool_names = list({msg.name for msg in tool_msgs if msg.name})
    key_obs = "; ".join(str(msg.content)[:200] for msg in tool_msgs)[:1000]
    prior = state.get("session_summary") or ""

    prompt = _loader.load("summariser", version=version).render(
        query=state["query"],
        final_answer=final_answer,
        tool_names_used=", ".join(tool_names),
        key_observations=key_obs,
    )
    if prior:
        prompt = f"Prior session context:\n{prior}\n\n---\n\n{prompt}"
    prompt += "\n\nIMPORTANT: Respond in plain prose (not JSON, not markdown fences)."

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    if tracker is not None:
        usage = response.usage_metadata or {}
        model_id = (response.response_metadata or {}).get("model_name", "gpt-5-nano")
        tracker.record_llm_call(
            model_id=model_id,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
        )
    return response.content
