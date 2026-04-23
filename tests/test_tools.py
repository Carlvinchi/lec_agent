from tools.web_search import web_search
from tools.calculator import calculator
from tools.market import get_company_fundamentals, cache_stats
from tools.kb import lookup_knowledge_base


def test_web_search_returns_results():
    results = web_search.invoke({"query": "Apple revenue 2024", "max_results": 2})
    assert len(results) >= 1
    assert "url" in results[0]


def test_calculator_basic_arithmetic():
    assert calculator.invoke({"operation": "add",      "a": 10, "b": 5})["result"] == 15
    assert calculator.invoke({"operation": "subtract", "a": 10, "b": 5})["result"] == 5
    assert calculator.invoke({"operation": "multiply", "a": 4,  "b": 3})["result"] == 12
    assert calculator.invoke({"operation": "divide",   "a": 10, "b": 4})["result"] == 2.5
    assert calculator.invoke({"operation": "power",    "a": 2,  "b": 8})["result"] == 256


def test_calculator_financial_operations():
    r = calculator.invoke({"operation": "percentage_change", "a": 100, "b": 125})
    assert r["success"] and r["result"] == 25.0

    r = calculator.invoke({"operation": "ratio", "a": 200, "b": 10})
    assert r["success"] and r["result"] == 20.0

    r = calculator.invoke({"operation": "cagr", "a": 1000, "b": 1610.51, "n": 10})
    assert r["success"] and round(r["result"], 1) == 4.9


def test_calculator_single_operand():
    assert calculator.invoke({"operation": "sqrt", "a": 144})["result"] == 12.0
    assert calculator.invoke({"operation": "abs",  "a": -42})["result"] == 42
    assert calculator.invoke({"operation": "round", "a": 3.14159, "decimals": 2})["result"] == 3.14


def test_calculator_error_cases():
    assert not calculator.invoke({"operation": "divide",           "a": 10,   "b": 0})["success"]
    assert not calculator.invoke({"operation": "sqrt",             "a": -1})["success"]
    assert not calculator.invoke({"operation": "percentage_change","a": 0,    "b": 50})["success"]
    assert not calculator.invoke({"operation": "cagr",             "a": 1000, "b": 2000, "n": 0})["success"]
    assert not calculator.invoke({"operation": "unknown_op",       "a": 1,    "b": 2})["success"]


def test_get_market_fundamentals_cached():
    get_company_fundamentals.invoke({"ticker": "MSFT"})
    get_company_fundamentals.invoke({"ticker": "MSFT"})   # second call hits cache
    stats = cache_stats()
    assert stats["intraday"]["hits"] >= 1


def test_kb_lookup_knowledge_base():
    results = lookup_knowledge_base.invoke({"term": "deferred revenue"})
    assert len(results) >= 1
    assert "definition" in results[0]
