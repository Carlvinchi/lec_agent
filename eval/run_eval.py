#!/usr/bin/env python
"""
Run the financial-agent evaluation suite.

Usage:
  python -m eval.run_eval
  python -m eval.run_eval --strategy plan_then_execute
  python -m eval.run_eval --ids q1 q2 q7        # run a subset
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time
import uuid
from collections import defaultdict
from pathlib import Path

import yaml
from dotenv import load_dotenv
load_dotenv()

from agent.state import initial_state
from agent.budget import BudgetTracker
from agent.graph import build_graph
from eval.graders import GRADERS, GRADER_CATEGORY, unique_tools_from_messages
from langgraph.checkpoint.memory import MemorySaver
from tools import TOOLS


# ---------------------------------------------------------------------------
# Per-query runner
# ---------------------------------------------------------------------------

async def run_single_query(
    query_cfg: dict,
    run_id: str,
    strategy: str,
) -> tuple[dict, BudgetTracker]:
    tracker = BudgetTracker()
    graph = build_graph(
        tools=TOOLS,
        tracker=tracker,
        dedup_cache={},
        strategy=strategy,
        prompt_version="v3",
        checkpointer=MemorySaver(),
    )

    thread_id = f"eval_{run_id}_{query_cfg['id']}"
    state = initial_state(
        query=query_cfg["text"],
        query_id=query_cfg["id"],
        conversation_turns=0,
    )
    config = {"configurable": {"thread_id": thread_id}}

    t0 = time.time()
    tools_used: set[str] = set()
    try: 
        result = await graph.ainvoke(state, config=config)
        elapsed = time.time() - t0
        answer = result.get("final_answer", "") or ""
        tools_used = unique_tools_from_messages(result.get("messages", []))
        grader_type = query_cfg.get("grader", "numeric")
        grader_fn = GRADERS.get(grader_type, GRADERS["numeric"]) 
        grader_result = grader_fn(answer, query_cfg)
    except Exception as e:
        elapsed = time.time() - t0
        answer = ""
        grader_result = {"pass": False, "reason": f"Exception: {e}"}

    minimum_tools = query_cfg.get("minimum_tools", 0)
    unique_tool_count = len(tools_used)
    coverage_pass = unique_tool_count >= minimum_tools

    return {
        "query_id":          query_cfg["id"],
        "strategy":          strategy,
        "success":           grader_result["pass"],
        "wall_time_s":       round(elapsed, 2),
        "final_answer":      answer,
        "grader_result":     grader_result,
        "grader_type":       query_cfg.get("grader", "numeric"),
        "tools_used":        sorted(tools_used),
        "unique_tool_count": unique_tool_count,
        "minimum_tools":     minimum_tools,
        "coverage_pass":     coverage_pass,
        "shortcut_pass":     grader_result["pass"] and not coverage_pass,
        "budget":            tracker.snapshot(),
    }, tracker


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _build_grader_breakdown(results: list[dict]) -> dict:
    cats: dict[str, dict] = defaultdict(lambda: {"passed": 0, "total": 0})
    for r in results:
        cat = GRADER_CATEGORY.get(r["grader_type"], "other")
        cats[cat]["total"] += 1
        if r["success"]:
            cats[cat]["passed"] += 1
    return dict(cats)


def _tier(pass_rate: float, coverage_rate: float, refusal_rate: float) -> str:
    if pass_rate >= 80 and coverage_rate >= 90 and refusal_rate == 100:
        return "stretch"
    if pass_rate >= 65 and coverage_rate >= 80 and refusal_rate == 100:
        return "target"
    if pass_rate >= 40 and refusal_rate == 100:
        return "baseline"
    return "below_baseline"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(strategy: str, ids: list[str] | None = None):
    run_id = uuid.uuid4().hex[:8]
    results_dir = Path(f"eval/results/{run_id}")
    results_dir.mkdir(parents=True)

    queries_data = yaml.safe_load(Path("eval/queries.yaml").read_text())
    benchmark_queries = queries_data["queries"]
    stretch_queries   = queries_data.get("stretch_queries", [])
    all_queries = benchmark_queries + stretch_queries

    if ids:
        all_queries = [q for q in all_queries if q["id"] in ids]

    stretch_ids = {q["id"] for q in stretch_queries}

    all_trackers: list[BudgetTracker] = []
    results: list[dict] = []
    for q in all_queries:
        print(f"Running {q['id']}: {q['text'][:70].strip()}...")
        r, tracker = await run_single_query(q, run_id, strategy)
        all_trackers.append(tracker)
        results.append(r)
        (results_dir / f"{q['id']}.json").write_text(json.dumps(r, indent=2))
        status = "PASS" if r["success"] else "FAIL"
        cov    = f"tools={r['unique_tool_count']}/{r['minimum_tools']}"
        short  = " [SHORTCUT]" if r["shortcut_pass"] else ""
        cost   = f"${tracker.snapshot()['dollars_spent']:.4f}"
        print(f"  {status} {cov}{short} [{cost}] — {r['grader_result']['reason'][:80]}")
        time.sleep(10)  # brief pause between queries to avoid overwhelming APIs; adjust as needed

    # Aggregate budget across all per-query trackers
    agg_tracker = BudgetTracker()
    total_wall_time = 0.0
    for t in all_trackers:
        snap = t.snapshot()
        agg_tracker.tokens_used           += snap["tokens_used"]
        agg_tracker.dollars_spent         += snap["dollars_spent"]
        agg_tracker.cache_creation_tokens += snap.get("cache_creation_tokens", 0)
        agg_tracker.cache_read_tokens     += snap.get("cache_read_tokens", 0)
        agg_tracker.tool_call_count       += snap.get("tool_call_count", 0)
        total_wall_time                   += snap["wall_time_s"]
    # Back-date _start so wall_time_s returns the summed per-query wall time
    agg_tracker._start = time.time() - total_wall_time

    # Split into benchmark vs stretch
    benchmark = [r for r in results if r["query_id"] not in stretch_ids]
    stretch   = [r for r in results if r["query_id"] in stretch_ids]

    total_bench = len(benchmark)
    passed_bench = sum(r["success"] for r in benchmark)
    benchmark_pass_rate = round(passed_bench / total_bench * 100, 1) if total_bench else 0.0

    # Tool coverage rate: proportion of benchmark queries where unique tools >= minimum
    coverage_eligible = [r for r in benchmark if r["minimum_tools"] > 0]
    tool_coverage_rate = (
        round(sum(r["coverage_pass"] for r in coverage_eligible) / len(coverage_eligible) * 100, 1)
        if coverage_eligible else 0.0
    )

    shortcut_passes = sum(r["shortcut_pass"] for r in benchmark)

    total_stretch = len(stretch)
    stretch_refusals = sum(r["success"] for r in stretch)
    refusal_rate = round(stretch_refusals / total_stretch * 100, 1) if total_stretch else 100.0

    grader_breakdown = _build_grader_breakdown(benchmark)
    tier = _tier(benchmark_pass_rate, tool_coverage_rate, refusal_rate)

    summary = {
        "run_id":               run_id,
        "strategy":             strategy,
        "benchmark_pass_rate":  benchmark_pass_rate,
        "tool_coverage_rate":   tool_coverage_rate,
        "refusal_rate":         refusal_rate,
        "tier":                 tier,
        "passed":               passed_bench,
        "total":                total_bench,
        "shortcut_passes":      shortcut_passes,
        "stretch_refusals":     stretch_refusals,
        "stretch_total":        total_stretch,
        "grader_breakdown":     grader_breakdown,
        "final_budget":         agg_tracker.snapshot(),
        "results":              results,
    }
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    # Console summary
    print(f"\n{'='*60}")
    print(f"Run {run_id} | strategy={strategy} | tier={tier.upper()}")
    print(f"  Benchmark pass rate : {benchmark_pass_rate:.1f}%  ({passed_bench}/{total_bench})")
    print(f"  Tool coverage rate  : {tool_coverage_rate:.1f}%")
    print(f"  Refusal rate        : {refusal_rate:.1f}%  ({stretch_refusals}/{total_stretch})")
    print(f"  Shortcut passes     : {shortcut_passes}")
    print(f"  Budget spent        : ${agg_tracker.snapshot()['dollars_spent']:.4f}")
    print(f"\nGrader breakdown:")
    for cat, counts in grader_breakdown.items():
        pct = round(counts["passed"] / counts["total"] * 100) if counts["total"] else 0
        print(f"  {cat:<28} {counts['passed']}/{counts['total']}  ({pct}%)")
    print(f"{'='*60}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="plan_then_execute")
    parser.add_argument("--ids", nargs="*", help="Run only specific query IDs, e.g. q1 q3 q7")
    args = parser.parse_args()
    asyncio.run(main(args.strategy, args.ids))
