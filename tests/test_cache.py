import time
from agent.budget import compute_cost, BudgetTracker


def test_compute_cost_all_four_tokens():
    cost = compute_cost(
        "claude-sonnet-4-6",
        prompt_tokens=1000,
        completion_tokens=500,
        cache_creation_tokens=800,
        cache_read_tokens=800,
    )
    expected = (
        1000 / 1e6 * 3.00
        + 500 / 1e6 * 15.00
        + 800 / 1e6 * 3.75
        + 800 / 1e6 * 0.30
    )
    assert abs(cost - expected) < 1e-9


def test_cache_tokens_recorded_by_budget_tracker():
    """BudgetTracker must accumulate cache_creation and cache_read tokens correctly."""
    tracker = BudgetTracker()
    tracker.record_llm_call(
        model_id="claude-sonnet-4-6",
        prompt_tokens=100,
        completion_tokens=5,
        cache_creation_tokens=80,
        cache_read_tokens=20,
    )
    assert tracker.cache_creation_tokens == 80
    assert tracker.cache_read_tokens == 20
    # prompt + completion only — cache tokens are not double-counted in tokens_used
    assert tracker.tokens_used == 105


def test_cache_tokens_accumulate_across_calls():
    """Multiple calls should sum cache tokens correctly."""
    tracker = BudgetTracker()
    tracker.record_llm_call("claude-sonnet-4-6", 100, 10,
                            cache_creation_tokens=50, cache_read_tokens=0)
    tracker.record_llm_call("claude-sonnet-4-6", 50, 5,
                            cache_creation_tokens=0, cache_read_tokens=50)
    assert tracker.cache_creation_tokens == 50
    assert tracker.cache_read_tokens == 50


def test_cache_read_cheaper_than_cache_creation():
    """Cache read rate must be cheaper than cache creation — validates pricing table."""
    creation_cost = compute_cost("claude-sonnet-4-6", 0, 0,
                                 cache_creation_tokens=1_000_000, cache_read_tokens=0)
    read_cost = compute_cost("claude-sonnet-4-6", 0, 0,
                             cache_creation_tokens=0, cache_read_tokens=1_000_000)
    assert read_cost < creation_cost


def test_edgar_cache_permanent():
    from tools.cache import TTLCache
    c = TTLCache(ttl_seconds=None)
    c.set("key", "value")
    time.sleep(0.1)
    assert c.get("key") == "value"


def test_market_cache_hit():
    from tools.market import get_company_fundamentals, cache_stats
    get_company_fundamentals.invoke({"ticker": "AAPL"})
    get_company_fundamentals.invoke({"ticker": "AAPL"})   # second call hits cache
    stats = cache_stats()
    assert stats["intraday"]["hits"] >= 1
