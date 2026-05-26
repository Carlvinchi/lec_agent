from __future__ import annotations
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from agent.state import AgentState
from agent.prompt_loader import PromptLoader

_loader = PromptLoader()

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

async def planner_node(
    state: AgentState,
    llm_planner,
    tracker,
    tool_list_str: str,
    strategy: str = "plan_then_execute",
    version: str = "v1",
) -> dict:
    existing_messages = list(state["messages"])
    new_messages: list = []

    # Inject the system prompt only when it is not already in the history.
    # This covers both fresh sessions (empty history) and resumed sessions
    # where a prior session's SystemMessage is already present.
    has_system = any(isinstance(m, SystemMessage) for m in existing_messages)
    if not has_system:
        prior = state["session_summary"] or "None."
        template = _loader.load(strategy, version=version)
        system_content = template.render(
            prior_context=prior,
            tool_list=tool_list_str,
            remaining_budget=f"${state['remaining_budget_dollars']:.4f}",
        )
        new_messages.append(
            SystemMessage(
                content=[{
                    "type": "text",
                    "text": system_content,
                    "cache_control": {"type": "ephemeral"},
                }]
            )
        )
    
    # Pass the full accumulated evidence so the reflector can assess completeness
    # across all loop iterations, not just the most recent batch.
    all_tool_msgs = _all_tool_messages(state["messages"])
    current_tool_msgs = _current_tool_messages(state["messages"])
 
    # Always append the current remaining budget so the planner sees an
    # accurate figure every iteration, even though the system prompt is cached.
    budget_note = f"[Budget remaining: ${state['remaining_budget_dollars']:.4f}]"

    # if state["reflection_notes"]:
    #     # Loop iteration: guide the model on the specific gap to fill.
    #     latest_gap = state["reflection_notes"][-1]
    #     new_messages.append(
    #         HumanMessage(
    #             content=(
    #                 f"{budget_note}\n"
    #                 "The previous research iteration was incomplete. "
    #                 f"Remarks: {latest_gap}\n\n"
    #             )
    #         )
    #     )

    if existing_messages:
        new_iteration = state["iteration"] + 1
        new_messages.append(
            HumanMessage(
                content=(
                    f"{budget_note}\n"
                    f"Current query: {state['query']}\n\n"
                    "Review the data gathered so far and if the information gathered is sufficient, generate a final answer. If not, identify specific gaps in the research and what to do next to fill those gaps.\n"
                )
            )
        )

    else:
        # Fresh or resumed session — always inject the current query so the
        # conversation ends with a user message regardless of checkpoint state.
        new_messages.append(HumanMessage(content=f"{budget_note}\n{state['query']}"))

    invoke_messages = list(existing_messages) + new_messages
    response = await llm_planner.ainvoke(invoke_messages)

    # Record token usage in the shared budget tracker.
    usage = response.usage_metadata or {}
    meta = (response.response_metadata or {}).get("usage", {})
    model_id = (response.response_metadata or {}).get("model", "claude-sonnet-4-6")
    tracker.record_llm_call(
        model_id=model_id,
        prompt_tokens=usage.get("input_tokens", 0),
        completion_tokens=usage.get("output_tokens", 0),
        cache_creation_tokens=meta.get("cache_creation_input_tokens", 0),
        cache_read_tokens=meta.get("cache_read_input_tokens", 0),
    )

    new_messages.append(response)
    return {"messages": new_messages, "iteration": new_iteration if existing_messages else 0}
 