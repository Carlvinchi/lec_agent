from __future__ import annotations
import time
from dataclasses import dataclass, field

# Per-million-token rates (USD). Add new models here — no other file changes needed.
# NOTE: gpt-5-nano rates are placeholders — verify at platform.openai.com before use.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {
        "input":           3.00,
        "output":         15.00,
        "cache_creation":  3.75,
        "cache_read":      0.30,
    },
    "claude-haiku-4-5-20251001": {
        "input":           0.80,
        "output":          4.00,
        "cache_creation":  1.00,
        "cache_read":      0.08,
    },
    "gpt-5-nano": {
    "input":           0.05,
    "output":          0.40,
    "cache_creation":  0.00,
    "cache_read":      0.005
   },
     "gpt-4o-mini": {
        "input":           0.15,
        "output":          0.60,
        "cache_creation":  0.00,
        "cache_read":      0.075,
    },
}

CAPS = {
    "dollars":          0.5,
    "wall_time_s":    300.0,   # per-query; reset_timer() called between queries in eval
    "iterations":       10,
    "tool_calls":     30,   # total across all queries in a run; 15/query × 12 queries + headroom
    "tokens":      200_000,
    "conversation_turns": 20,
}

NO_PROGRESS_THRESHOLD = 0.92   # cosine similarity for gap paraphrase detection


class BudgetExceededError(Exception):
    def __init__(self, reason: str, snapshot: dict):
        super().__init__(f"Budget exceeded: {reason}")
        self.reason = reason
        self.snapshot = snapshot


@dataclass
class StepUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    timestamp: float = field(default_factory=time.time)


def compute_cost(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    pricing = MODEL_PRICING.get(model_id, MODEL_PRICING["claude-sonnet-4-6"])
    return (
        prompt_tokens           / 1_000_000 * pricing["input"]
        + completion_tokens     / 1_000_000 * pricing["output"]
        + cache_creation_tokens / 1_000_000 * pricing["cache_creation"]
        + cache_read_tokens     / 1_000_000 * pricing["cache_read"]
    )


class BudgetTracker:
    def __init__(self, budget_dollars: float = CAPS["dollars"]):
        self._start = time.time()
        self._budget_dollars = budget_dollars
        self.tokens_used = 0
        self.dollars_spent = 0.0
        self.tool_call_count = 0
        self.cache_creation_tokens = 0
        self.cache_read_tokens = 0
        self.step_usages: list[StepUsage] = []

    def record_llm_call(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> StepUsage:
        cost = compute_cost(model_id, prompt_tokens, completion_tokens,
                            cache_creation_tokens, cache_read_tokens)
        self.tokens_used += prompt_tokens + completion_tokens
        self.dollars_spent += cost
        self.cache_creation_tokens += cache_creation_tokens
        self.cache_read_tokens += cache_read_tokens
        step = StepUsage(
            model=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=cost,
        )
        self.step_usages.append(step)
        return step

    def reset_timer(self) -> None:
        """Reset the wall-clock start. Call between queries in eval so each query gets a fresh 90s window."""
        self._start = time.time()

    def record_tool_call(self) -> None:
        self.tool_call_count += 1

    @property
    def wall_time_s(self) -> float:
        return time.time() - self._start

    @property
    def remaining_dollars(self) -> float:
        return max(0.0, self._budget_dollars - self.dollars_spent)

    def is_exceeded(self) -> bool:
        return self.dollars_spent >= self._budget_dollars

    def check_caps(self, iteration: int, conversation_turns: int) -> str | None:
        if self.dollars_spent       >= CAPS["dollars"]:            return "estimated cost budget has been exceeded"
        if self.wall_time_s         >= CAPS["wall_time_s"]:        return "estimated wall time budget has been exceeded"
        if iteration                >= CAPS["iterations"]:         return "estimated maximum iterations have been exceeded"
        if self.tool_call_count     >= CAPS["tool_calls"]:         return "estimated maximum tool calls have been exceeded"
        if self.tokens_used         >= CAPS["tokens"]:             return "estimated maximum tokens have been exceeded"
        if conversation_turns       >= CAPS["conversation_turns"]: return "estimated maximum conversation turns have been exceeded"
        return None

    def snapshot(self) -> dict:
        return {
            "tokens_used": self.tokens_used,
            "dollars_spent": round(self.dollars_spent, 6),
            "remaining_budget_dollars": round(self.remaining_dollars, 6),
            "wall_time_s": round(self.wall_time_s, 2),
            "tool_call_count": self.tool_call_count,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
        }
