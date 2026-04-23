from __future__ import annotations
from datetime import date
from langchain_core.tools import tool
import yfinance as yf
from tools.cache import TTLCache

_intraday_cache = TTLCache(ttl_seconds=4 * 3600)    # 4 hours
_historical_cache = TTLCache(ttl_seconds=None)       # permanent for past date ranges

@tool("get_market_fundamentals")
def get_company_fundamentals(ticker: str) -> dict:
    """Retrieve current key fundamental metrics for a stock, including market cap, P/E ratio, gross/operating margins, return on equity, and debt-to-equity ratio.

    Args:
        ticker: Stock ticker symbol to look up (e.g., "AAPL" for Apple, "MSFT" for Microsoft).
    """
    key = _intraday_cache.make_key(fn="fundamentals", ticker=ticker)
    if hit := _intraday_cache.get(key):
        return hit
    info = yf.Ticker(ticker).info
    data = {k: info.get(k) for k in (
        "marketCap", "trailingPE", "forwardPE", "priceToBook",
        "grossMargins", "operatingMargins", "returnOnEquity",
        "totalRevenue", "debtToEquity", "currentRatio",
    )}
    _intraday_cache.set(key, data)
    return data

@tool("get_market_history")
def get_company_price_history(ticker: str, start: date, end: date) -> list[dict]:
    """Retrieve daily closing price and trading volume for a stock over a specified date range.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL" for Apple, "MSFT" for Microsoft).
        start: Start date for the historical data in ISO format (e.g., "2024-01-01").
        end: End date for the historical data in ISO format (e.g., "2024-12-31").
    """
    is_historical = end < date.today()
    cache = _historical_cache if is_historical else _intraday_cache
    key = cache.make_key(fn="price_history", ticker=ticker,
                         start=str(start), end=str(end))
    if hit := cache.get(key):
        return hit

    df = yf.Ticker(ticker).history(start=start, end=end)
    data = df.reset_index()[["Date", "Close", "Volume"]].to_dict("records")
    cache.set(key, data)
    return data

@tool("get_market_financials")
def get_company_financials(ticker: str, statement: str, period: str = "annual") -> list[dict]:
    """Retrieve income statement, balance sheet, or cash flow statement data for a company from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL" for Apple, "MSFT" for Microsoft).
        statement: Financial statement type — "income" for income statement, "balance" for balance
            sheet, "cashflow" for cash flow statement.
        period: Reporting period — "annual" for yearly data or "quarterly" for quarterly data.
    """
    key = _intraday_cache.make_key(fn="financials", ticker=ticker,
                                   statement=statement, period=period)
    if hit := _intraday_cache.get(key):
        return hit

    t = yf.Ticker(ticker)
    mapping = {"income": t.financials, "balance": t.balance_sheet,
               "cashflow": t.cashflow}
    df = mapping.get(statement, t.financials)
    data = df.T.reset_index().to_dict("records") if df is not None else []
    _intraday_cache.set(key, data)
    return data


def cache_stats() -> dict:
    return {
        "intraday": _intraday_cache.stats(),
        "historical": _historical_cache.stats(),
    }
