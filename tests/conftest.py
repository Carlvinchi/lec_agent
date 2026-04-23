import pytest
from dotenv import load_dotenv
load_dotenv()


@pytest.fixture(scope="module")
async def graph_fixture():
    from agent.budget import BudgetTracker
    from agent.graph import build_graph
    from tools import TOOLS
    from langgraph.checkpoint.memory import MemorySaver

    tracker = BudgetTracker(budget_dollars=2.00)
    graph = build_graph(
        tools=TOOLS,
        tracker=tracker,
        dedup_cache={},
        strategy="plan_then_execute",
        prompt_version="v1",
        checkpointer=MemorySaver(),
    )
    return graph
