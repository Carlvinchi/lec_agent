#!/usr/bin/env python
"""
Compare two eval run summaries side-by-side and print an ablation table.

Usage:
  python scripts/compare_runs.py <run_id_A> <run_id_B>

Example:
  python scripts/compare_runs.py abc12345 def67890
"""
from __future__ import annotations
import json
import sys
from pathlib import Path


def load_summary(run_id: str) -> dict:
    path = Path(f"eval/results/{run_id}/summary.json")
    if not path.exists():
        raise FileNotFoundError(f"No summary found for run '{run_id}' at {path}")
    return json.loads(path.read_text())


def _pct(val: float) -> str:
    return f"{val:.1f}%"


def _cost(val: float) -> str:
    return f"${val:.4f}"


def _delta_str(delta: float, fmt: str = ".2f") -> str:
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:{fmt}}"


def print_summary_table(a: dict, b: dict) -> None:
    label_a = f"{a.get('strategy', a.get('prompt_version', '?'))} ({a['run_id']})"
    label_b = f"{b.get('strategy', b.get('prompt_version', '?'))} ({b['run_id']})"
    col_w = max(len(label_a), len(label_b), 24)

    header = f"{'Metric':<35} {label_a:>{col_w}} {label_b:>{col_w}} {'Delta (A-B)':>12}"
    sep = "-" * len(header)

    print(f"\n{sep}")
    print(header)
    print(sep)

    budget_a = a["final_budget"]
    budget_b = b["final_budget"]
    total_a  = a["total"] or 1
    total_b  = b["total"] or 1

    rows = [
        ("Benchmark pass rate",
         _pct(a.get("benchmark_pass_rate", a.get("success_rate", 0.0))),
         _pct(b.get("benchmark_pass_rate", b.get("success_rate", 0.0))),
         _delta_str(
             a.get("benchmark_pass_rate", a.get("success_rate", 0.0)) -
             b.get("benchmark_pass_rate", b.get("success_rate", 0.0)), ".1f") + "pp"),

        ("Tool coverage rate",
         _pct(a.get("tool_coverage_rate", 0.0)),
         _pct(b.get("tool_coverage_rate", 0.0)),
         _delta_str(a.get("tool_coverage_rate", 0.0) - b.get("tool_coverage_rate", 0.0), ".1f") + "pp"),

        ("Refusal rate",
         _pct(a.get("refusal_rate", 0.0)),
         _pct(b.get("refusal_rate", 0.0)),
         _delta_str(a.get("refusal_rate", 0.0) - b.get("refusal_rate", 0.0), ".1f") + "pp"),

        ("Tier",
         a.get("tier", "n/a"),
         b.get("tier", "n/a"),
         "—"),

        ("Passed / total",
         f"{a['passed']}/{a['total']}",
         f"{b['passed']}/{b['total']}",
         _delta_str(a["passed"] - b["passed"], "d")),

        ("Shortcut passes",
         str(a.get("shortcut_passes", "n/a")),
         str(b.get("shortcut_passes", "n/a")),
         _delta_str(a.get("shortcut_passes", 0) - b.get("shortcut_passes", 0), "d")),

        ("Total tokens used",
         f"{budget_a['tokens_used']:,}",
         f"{budget_b['tokens_used']:,}",
         _delta_str(budget_a["tokens_used"] - budget_b["tokens_used"], ",d")),

        ("Avg tokens / query",
         f"{budget_a['tokens_used'] / total_a:,.0f}",
         f"{budget_b['tokens_used'] / total_b:,.0f}",
         _delta_str(budget_a["tokens_used"] / total_a - budget_b["tokens_used"] / total_b, ",.0f")),

        ("Total cost",
         _cost(budget_a["dollars_spent"]),
         _cost(budget_b["dollars_spent"]),
         _delta_str(budget_a["dollars_spent"] - budget_b["dollars_spent"], ".4f")),

        ("Avg cost / query",
         _cost(budget_a["dollars_spent"] / total_a),
         _cost(budget_b["dollars_spent"] / total_b),
         _delta_str(budget_a["dollars_spent"] / total_a - budget_b["dollars_spent"] / total_b, ".4f")),

        ("Cache read tokens",
         f"{budget_a['cache_read_tokens']:,}",
         f"{budget_b['cache_read_tokens']:,}",
         _delta_str(budget_a["cache_read_tokens"] - budget_b["cache_read_tokens"], ",d")),

        ("Wall time (s)",
         f"{budget_a['wall_time_s']:.1f}",
         f"{budget_b['wall_time_s']:.1f}",
         _delta_str(budget_a["wall_time_s"] - budget_b["wall_time_s"], ".1f")),
    ]

    for label, va, vb, delta in rows:
        print(f"{label:<35} {va:>{col_w}} {vb:>{col_w}} {delta:>12}")

    print(sep)


def print_grader_breakdown(a: dict, b: dict) -> None:
    cats = sorted(
        set(a.get("grader_breakdown", {}).keys()) |
        set(b.get("grader_breakdown", {}).keys())
    )
    if not cats:
        return

    print("\nGrader breakdown:")
    print(f"  {'Category':<30} {'A pass/total':>14} {'B pass/total':>14} {'Delta':>8}")
    print(f"  {'-'*70}")

    for cat in cats:
        ca = a.get("grader_breakdown", {}).get(cat, {"passed": 0, "total": 0})
        cb = b.get("grader_breakdown", {}).get(cat, {"passed": 0, "total": 0})
        ra = f"{ca['passed']}/{ca['total']}"
        rb = f"{cb['passed']}/{cb['total']}"
        delta = ca["passed"] - cb["passed"]
        sign = "+" if delta >= 0 else ""
        print(f"  {cat:<30} {ra:>14} {rb:>14} {sign+str(delta):>8}")


def print_per_query_diff(a: dict, b: dict) -> None:
    results_a = {r["query_id"]: r for r in a.get("results", [])}
    results_b = {r["query_id"]: r for r in b.get("results", [])}
    all_ids = sorted(set(results_a) | set(results_b),
                     key=lambda x: int(x.lstrip("q")))

    changed = [
        qid for qid in all_ids
        if results_a.get(qid, {}).get("success") != results_b.get(qid, {}).get("success")
    ]

    if not changed:
        print("\nPer-query diff: no changes between runs.")
        return

    print(f"\nPer-query diff ({len(changed)} queries changed):")
    print(f"  {'Query':<8} {'A':>6} {'B':>6}  Grader")
    print(f"  {'-'*45}")
    for qid in all_ids:
        ra = results_a.get(qid)
        rb = results_b.get(qid)
        if ra is None or rb is None:
            continue
        if ra["success"] == rb["success"]:
            continue
        sa = "PASS" if ra["success"] else "FAIL"
        sb = "PASS" if rb["success"] else "FAIL"
        grader = ra.get("grader_type", "?")
        print(f"  {qid:<8} {sa:>6} {sb:>6}  {grader}")


def compare(run_id_a: str, run_id_b: str) -> None:
    a = load_summary(run_id_a)
    b = load_summary(run_id_b)

    print_summary_table(a, b)
    print_grader_breakdown(a, b)
    print_per_query_diff(a, b)
    print()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
