import pytest
from agent.budget import BudgetTracker, BudgetExceededError, CAPS, compute_cost


def test_iteration_cap():
    tracker = BudgetTracker()
    assert tracker.check_caps(iteration=CAPS["iterations"], conversation_turns=0) == "max_iterations"


def test_dollar_cap():
    tracker = BudgetTracker()
    tracker.dollars_spent = CAPS["dollars"]
    assert tracker.check_caps(iteration=0, conversation_turns=0) == "budget_dollars"


def test_turn_cap():
    tracker = BudgetTracker()
    assert tracker.check_caps(iteration=0, conversation_turns=CAPS["conversation_turns"]) == "max_conversation_turns"


def test_remaining_budget_decrements():
    tracker = BudgetTracker(budget_dollars=1.00)
    tracker.record_llm_call("claude-sonnet-4-6", prompt_tokens=10_000, completion_tokens=1_000)
    assert tracker.remaining_dollars < 1.00
    assert tracker.snapshot()["remaining_budget_dollars"] == round(tracker.remaining_dollars, 6)


def test_is_exceeded_raises_on_preflight():
    tracker = BudgetTracker(budget_dollars=0.00)
    assert tracker.is_exceeded()


def test_per_step_usage_recorded():
    tracker = BudgetTracker()
    step = tracker.record_llm_call("claude-haiku-4-5-20251001",
                                   prompt_tokens=500, completion_tokens=200)
    assert step.model == "claude-haiku-4-5-20251001"
    assert step.total_tokens == 700
    assert step.cost > 0
    assert len(tracker.step_usages) == 1


def test_compute_cost_model_agnostic():
    sonnet_cost = compute_cost("claude-sonnet-4-6", 1_000_000, 0)
    haiku_cost  = compute_cost("claude-haiku-4-5-20251001", 1_000_000, 0)
    nano_cost   = compute_cost("gpt-5-nano", 1_000_000, 0)
    mini_cost   = compute_cost("gpt-4o-mini", 1_000_000, 0)
    assert sonnet_cost > haiku_cost        # Sonnet input > Haiku input
    assert nano_cost < haiku_cost          # gpt-5-nano is cheapest input
    assert mini_cost < haiku_cost          # gpt-4o-mini input < Haiku input
    assert mini_cost > nano_cost           # gpt-4o-mini more expensive than gpt-5-nano


def test_gpt5_nano_pricing():
    """gpt-5-nano rates: $0.05 input, $0.40 output per million tokens."""
    cost = compute_cost("gpt-5-nano", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    expected = 0.05 + 0.40
    assert abs(cost - expected) < 1e-9


def test_gpt4o_mini_pricing():
    """gpt-4o-mini rates: $0.15 input, $0.60 output per million tokens."""
    cost = compute_cost("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    expected = 0.15 + 0.60
    assert abs(cost - expected) < 1e-9


def test_gpt4o_mini_no_cache_tokens():
    """gpt-4o-mini has no prompt-cache creation cost — cache_creation rate is 0."""
    cost_with_cache    = compute_cost("gpt-4o-mini", 0, 0, cache_creation_tokens=1_000_000)
    cost_without_cache = compute_cost("gpt-4o-mini", 0, 0)
    assert cost_with_cache == cost_without_cache == 0.0


def test_reset_timer_resets_wall_time():
    import time
    tracker = BudgetTracker()
    time.sleep(0.05)
    before = tracker.wall_time_s
    tracker.reset_timer()
    after = tracker.wall_time_s
    assert after < before


def test_snapshot_includes_remaining_budget():
    tracker = BudgetTracker(budget_dollars=0.50)
    snap = tracker.snapshot()
    assert "remaining_budget_dollars" in snap
    assert snap["remaining_budget_dollars"] == 0.50


def test_multiple_step_usages_accumulate():
    tracker = BudgetTracker()
    tracker.record_llm_call("claude-sonnet-4-6", prompt_tokens=1000, completion_tokens=500)
    tracker.record_llm_call("claude-haiku-4-5-20251001", prompt_tokens=200, completion_tokens=100)
    assert len(tracker.step_usages) == 2
    assert tracker.tokens_used == 1800
    assert tracker.dollars_spent == pytest.approx(
        compute_cost("claude-sonnet-4-6", 1000, 500)
        + compute_cost("claude-haiku-4-5-20251001", 200, 100),
        rel=1e-6,
    )
