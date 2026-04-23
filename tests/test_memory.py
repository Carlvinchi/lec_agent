import pytest
from agent.state import initial_state


@pytest.mark.asyncio
async def test_session_summary_populated_after_query(graph_fixture):
    state = initial_state("What is EBITDA?", "mem_q1")
    config = {"configurable": {"thread_id": "test_memory_1"}}
    result = await graph_fixture.ainvoke(state, config=config)
    assert result["session_summary"] is not None
    assert len(result["session_summary"]) > 10


@pytest.mark.asyncio
async def test_observation_log_accumulates(graph_fixture):
    state = initial_state("What is the P/E ratio?", "mem_q2")
    config = {"configurable": {"thread_id": "test_memory_2"}}
    result = await graph_fixture.ainvoke(state, config=config)
    # observation_log is append-only and accumulates across turns
    assert len(result["observation_log"]) > 0


@pytest.mark.asyncio
async def test_planner_receives_summary_on_second_turn(graph_fixture):
    config = {"configurable": {"thread_id": "test_memory_3"}}

    # Turn 1: fetch MSFT revenue
    state1 = initial_state("What was Microsoft's revenue for FY2024?", "mem_t1")
    r1 = await graph_fixture.ainvoke(state1, config=config)
    assert r1["session_summary"], "Turn 1 must produce a session summary"

    # Turn 2: follow-up that should leverage Turn 1 context
    state2 = initial_state(
        "And what was their gross margin that year?",
        "mem_t2",
        conversation_turns=r1["conversation_turns"],
        session_summary=r1["session_summary"],
    )
    r2 = await graph_fixture.ainvoke(state2, config=config)
    assert r2["conversation_turns"] == 2
    # The planner sees prior_context from turn 1; answer should not be empty
    assert r2["final_answer"] and len(r2["final_answer"]) > 10
