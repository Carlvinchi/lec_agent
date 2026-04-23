from __future__ import annotations
import re
import httpx
from datetime import datetime
from urllib.parse import urlparse


_SUFFIX_MULTIPLIERS = {
    "trillion": 1e12, "t": 1e12,
    "billion":  1e9,  "b": 1e9,
    "million":  1e6,  "m": 1e6,
    "thousand": 1e3,  "k": 1e3,
}


def _extract_best_number(text: str) -> float | None:
    """
    Extract the best candidate number from text, expanding magnitude suffixes.
    Prefers the largest plausible number so "60.9 billion" beats bare "2024".
    """
    pattern = re.compile(
        r"\$?([\d,]+\.?\d*)\s*(trillion|billion|million|thousand|[tTbBmMkK])\b",
        re.IGNORECASE,
    )
    candidates = []
    for m in pattern.finditer(text):
        raw = float(m.group(1).replace(",", ""))
        suffix = m.group(2).lower().rstrip("s")
        mult = _SUFFIX_MULTIPLIERS.get(suffix, 1)
        candidates.append(raw * mult)

    if candidates:
        return max(candidates)

    plain = re.findall(r"\$?([\d,]+\.?\d*)", text)
    non_year = [float(n.replace(",", "")) for n in plain
                if not re.fullmatch(r"(?:19|20)\d{2}", n.replace(",", ""))]
    return max(non_year) if non_year else None


def _extract_small_number(text: str, ground_truth: float) -> float | None:
    """For small ground truths (ratios, %, CAGR), prefer numbers close in magnitude."""
    plain = re.findall(r"-?[\d]+\.?\d*", text.replace(",", ""))
    candidates = [
        float(n) for n in plain
        if not re.fullmatch(r"(?:19|20)\d{2}", n.lstrip("-"))
        and abs(float(n)) < 1000
    ]
    if not candidates:
        return _extract_best_number(text)
    return min(candidates, key=lambda x: abs(x - ground_truth))


def _extract_near(text: str, keyword: str) -> float | None:
    """Extract first number within 150 chars after a keyword."""
    idx = text.lower().find(keyword.lower())
    if idx < 0:
        return None
    snippet = text[idx: idx + 150]
    nums = re.findall(r"[\d]+\.?\d*", snippet.replace(",", ""))
    return float(nums[0]) if nums else None


# ---------------------------------------------------------------------------
# Tool-coverage helper
# ---------------------------------------------------------------------------

def unique_tools_from_messages(messages: list) -> set[str]:
    """
    Walk a LangGraph message list and return the set of unique tool names
    invoked during the run.  Handles both ToolMessage (name attr) and
    AIMessage.tool_calls (list of dicts with 'name' key).
    """
    from langchain_core.messages import ToolMessage, AIMessage
    names: set[str] = set()
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name:
            names.add(msg.name)
        elif isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if isinstance(tc, dict) and tc.get("name"):
                    names.add(tc["name"])
    return names


# ---------------------------------------------------------------------------
# Individual graders
# ---------------------------------------------------------------------------

def numeric_grader(answer: str, query_cfg: dict) -> dict:
    raw_gt = query_cfg.get("ground_truth")
    if raw_gt is None:
        return {"pass": False, "reason": "No ground_truth configured"}
    try:
        gt = float(raw_gt)
    except (TypeError, ValueError):
        return {"pass": False, "reason": f"ground_truth not a number: {raw_gt!r}"}
    if gt == 0:
        return {"pass": False, "reason": "ground_truth is zero — cannot compute tolerance"}

    val = _extract_small_number(answer, gt) if gt < 200 else _extract_best_number(answer)
    if val is None:
        return {"pass": False, "reason": "No number found in answer"}

    tol = query_cfg.get("tolerance_pct", query_cfg.get("tolerance_pp", 1.0)) / 100.0
    passed = abs(val - gt) / abs(gt) <= tol
    return {"pass": passed, "reason": f"Got {val:.2f}, expected {gt:.2f} ±{tol*100:.1f}%"}


def tool_coverage_grader(tools_used: set[str], query_cfg: dict) -> dict:
    required_tools = set(query_cfg.get("required_tools", []))
    if not required_tools:
        return {"pass": False, "reason": "No required tools configured"}

    missing_tools = required_tools - tools_used
    if missing_tools:
        return {"pass": False, "reason": f"Missing tools: {missing_tools}"}

    return {"pass": True, "reason": "All required tools used"}


def category_plus_numeric_grader(answer: str, query_cfg: dict) -> dict:
    gt_cat = query_cfg["ground_truth_category"]
    aliases = query_cfg.get("ground_truth_category_aliases", [gt_cat])
    answer_lower = answer.lower()
    cat_pass = any(alias.lower() in answer_lower for alias in aliases)

    tol = query_cfg.get("tolerance_pp", 0.5)
    nums = {k: _extract_near(answer, k) for k in query_cfg["ground_truth_values"]}
    num_pass = all(
        abs(nums[k] - v) <= tol
        for k, v in query_cfg["ground_truth_values"].items()
        if nums[k] is not None
    )
    return {
        "pass": cat_pass and num_pass,
        "reason": f"Category match: {cat_pass}, Numerics match: {num_pass}",
    }



def definition_plus_numeric_grader(answer: str, query_cfg: dict) -> dict:
    keywords = query_cfg.get("definition_keywords", [])
    definition_pass = sum(kw.lower() in answer.lower() for kw in keywords) >= 2
    num_result = numeric_grader(answer, query_cfg)
    passed = definition_pass and num_result["pass"]
    return {
        "pass": passed,
        "reason": f"Definition keywords found: {definition_pass}, {num_result['reason']}",
    }

 
def two_numerics_direction_grader(answer: str, query_cfg: dict) -> dict:
    """
    Checks two things:
    1. Numeric: extracted value is within tolerance of ground_truth.
    2. Directional: the entity named in ground_truth_direction appears in the answer
       as the higher/worse value (e.g. GM has higher D/E than Ford).
    Both must pass.
    """
    num_result = numeric_grader(answer, query_cfg)

    direction_entity = query_cfg.get("ground_truth_direction", "")
    dir_pass = direction_entity.lower() in answer.lower() if direction_entity else True

    passed = num_result["pass"] and dir_pass
    return {
        "pass": passed,
        "reason": (
            f"{num_result['reason']} | "
            f"Direction entity '{direction_entity}' present: {dir_pass}"
        ),
    }


def boolean_plus_numerics_grader(answer: str, query_cfg: dict) -> dict:
    """
    Checks three things:
    1. Primary numeric: extracted value is within tolerance of ground_truth.
    2. Boolean: answer contains an affirmative/negative signal matching ground_truth_bool.
    3. Values array (optional): each value in ground_truth_values appears near its
       position context in the answer within tolerance_pct.
    All must pass.
    """
    num_result = numeric_grader(answer, query_cfg)

    gt_bool = query_cfg.get("ground_truth_bool")
    if gt_bool is not None:
        affirmative_signals = ["yes", "true", "did improve", "improved each", "monoton", "all three"]
        negative_signals    = ["no", "false", "did not", "did not improve", "declined"]
        signals = affirmative_signals if gt_bool else negative_signals
        bool_pass = any(s in answer.lower() for s in signals)
    else:
        bool_pass = True

    gt_vals = query_cfg.get("ground_truth_values", [])
    tol_pct = query_cfg.get("tolerance_pct", 20.0) / 100.0
    if gt_vals:
        found = [_extract_small_number(answer, v) for v in gt_vals]
        vals_pass = all(
            f is not None and abs(f - v) / abs(v) <= tol_pct
            for f, v in zip(found, gt_vals)
            if v != 0
        )
    else:
        vals_pass = True

    passed = num_result["pass"] and bool_pass and vals_pass
    return {
        "pass": passed,
        "reason": (
            f"{num_result['reason']} | "
            f"Boolean match: {bool_pass} | "
            f"Values array match: {vals_pass}"
        ),
    }


def llm_judge_dynamic_grader(answer: str, query_cfg: dict, llm_fn=None) -> dict:
    if query_cfg.get("expected_behaviour") == "refuse":
        refusal_signals = [
            "cannot", "can't", "unable", "don't know", "no data",
            "not possible", "speculative", "prediction", "probability",
        ]
        refused = any(s in answer.lower() for s in refusal_signals)
        return {"pass": refused, "reason": f"Refusal detected: {refused}"}

    source_allowlist = query_cfg.get("source_allowlist", [])
    recency_days = query_cfg.get("recency_days", 30)

    url_match = re.search(r"https?://\S+", answer)
    url = url_match.group(0).rstrip(".,)\"'") if url_match else ""
    domain = urlparse(url).netloc.lstrip("www.")
    source_ok = any(a in domain for a in source_allowlist) if source_allowlist else True

    date_match = re.search(r"\d{4}-\d{2}-\d{2}", answer)
    recency_ok = False
    if date_match:
        try:
            article_date = datetime.strptime(date_match.group(0), "%Y-%m-%d")
            recency_ok = (datetime.utcnow() - article_date).days <= recency_days
        except ValueError:
            recency_ok = False
    if recency_days == 0:
        recency_ok = True

    faithfulness_ok = True
    if llm_fn and url:
        try:
            content = httpx.get(url, timeout=10, follow_redirects=True).text[:3000]
            verdict = llm_fn(
                f"Does this summary contain claims not supported by the article?\n\n"
                f"Summary: {answer[:500]}\n\nArticle: {content}\n\nAnswer yes or no."
            )
            faithfulness_ok = "no" in verdict.lower()
        except Exception:
            faithfulness_ok = True

    passed = source_ok and recency_ok and faithfulness_ok
    return {
        "pass": passed,
        "reason": f"source={source_ok} recency={recency_ok} faithful={faithfulness_ok}",
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GRADERS = {
    "numeric":                 numeric_grader,
    "category_plus_numeric":   category_plus_numeric_grader,
    "numeric_plus_citation":   numeric_grader,
    "two_numerics_direction":  two_numerics_direction_grader,
    "definition_plus_numeric": definition_plus_numeric_grader,
    "boolean_plus_numerics":   boolean_plus_numerics_grader,
    "llm_judge_dynamic":       llm_judge_dynamic_grader,
    "tool_coverage":           tool_coverage_grader,
}

# Maps each grader key to its reporting category for the breakdown table
GRADER_CATEGORY = {
    "numeric":                 "numeric_accuracy",
    "numeric_plus_citation":   "numeric_accuracy",
    "definition_plus_numeric": "definition_plus_numeric",
    "category_plus_numeric":   "category_plus_numeric",
    "two_numerics_direction":  "directional_boolean",
    "boolean_plus_numerics":   "directional_boolean",
    "llm_judge_dynamic":       "refusal_accuracy",
    "tool_coverage":          "tool_coverage",
}
