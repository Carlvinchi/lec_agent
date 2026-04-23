from __future__ import annotations
import math

from langchain_core.tools import tool


_OPERATIONS = {
    "add", "subtract", "multiply", "divide", "power",
    "sqrt", "abs", "round",
    "percentage_change", "ratio", "cagr",
}


@tool
def calculator(
    operation: str,
    a: float,
    b: float | None = None,
    n: int | None = None,
    decimals: int = 2,
) -> dict:
    """Perform precise arithmetic and financial calculations — supports add, subtract, multiply, divide, power, sqrt, abs, round, percentage_change, ratio, and cagr.

    Args:
        operation: Calculation to perform. One of: add, subtract, multiply, divide, power,
            sqrt, abs, round, percentage_change, ratio, cagr.
        a: First operand or base value (start value for cagr and percentage_change).
        b: Second operand or end value. Required for all binary operations.
        n: Number of compounding periods. Required only for cagr.
        decimals: Decimal places for rounding. Used only with the 'round' operation. Default 2.
    """
    op = operation.lower().strip()
    if op not in _OPERATIONS:
        return {"success": False, "result": None,
                "error": f"Unknown operation '{operation}'. Valid: {sorted(_OPERATIONS)}"}

    try:
        if op == "add":
            result = a + b
        elif op == "subtract":
            result = a - b
        elif op == "multiply":
            result = a * b
        elif op == "divide":
            if b == 0:
                return {"success": False, "result": None, "error": "Division by zero"}
            result = a / b
        elif op == "power":
            result = a ** b
        elif op == "sqrt":
            if a < 0:
                return {"success": False, "result": None,
                        "error": "Cannot take square root of a negative number"}
            result = math.sqrt(a)
        elif op == "abs":
            result = abs(a)
        elif op == "round":
            result = round(a, decimals)
        elif op == "percentage_change":
            if a == 0:
                return {"success": False, "result": None,
                        "error": "Base value 'a' cannot be zero for percentage_change"}
            result = ((b - a) / a) * 100
        elif op == "ratio":
            if b == 0:
                return {"success": False, "result": None,
                        "error": "Denominator 'b' cannot be zero for ratio"}
            result = a / b
        elif op == "cagr":
            if n is None or n <= 0:
                return {"success": False, "result": None,
                        "error": "'n' must be a positive integer for cagr"}
            if a <= 0:
                return {"success": False, "result": None,
                        "error": "Start value 'a' must be positive for cagr"}
            result = ((b / a) ** (1 / n) - 1) * 100

        return {"success": True, "result": result, "error": ""}

    except TypeError:
        return {"success": False, "result": None,
                "error": f"Operation '{op}' requires a second operand 'b'"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
