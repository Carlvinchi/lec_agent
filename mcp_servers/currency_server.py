import asyncio
import json
import time

import httpx
from mcp.server.fastmcp import FastMCP

BASE = "https://api.frankfurter.dev/v1"

# Inline minimal TTL cache — avoids importing the tools package (and its heavy deps)
# into this subprocess.
class _TTLCache:
    def __init__(self, ttl=None):
        self._store: dict = {}
        self._ttl = ttl

    def get(self, key: str):
        if key not in self._store:
            return None
        v, ts = self._store[key]
        if self._ttl and (time.time() - ts) > self._ttl:
            del self._store[key]
            return None
        return v

    def set(self, key: str, value) -> None:
        self._store[key] = (value, time.time())

    def make_key(self, **kwargs) -> str:
        return json.dumps(kwargs, sort_keys=True)


_current_cache = _TTLCache(ttl=3600)
_historical_cache = _TTLCache(ttl=None)

app = FastMCP("currency_fx")


@app.tool()
def get_rate(from_ccy: str, to_ccy: str) -> str:
    """Get the current FX exchange rate between two currencies (e.g. USD to EUR)."""
    key = _current_cache.make_key(from_ccy=from_ccy, to_ccy=to_ccy)
    if hit := _current_cache.get(key):
        return str(hit)
    r = httpx.get(
        f"{BASE}/latest",
        params={"from": from_ccy, "to": to_ccy},
        timeout=10.0,
        follow_redirects=True,
    )
    r.raise_for_status()
    rate = r.json()["rates"][to_ccy]
    _current_cache.set(key, rate)
    return str(rate)


@app.tool()
def historical_rate(from_ccy: str, to_ccy: str, date: str) -> str:
    """Get the FX exchange rate on a specific past date (YYYY-MM-DD)."""
    key = _historical_cache.make_key(from_ccy=from_ccy, to_ccy=to_ccy, date=date)
    if hit := _historical_cache.get(key):
        return str(hit)
    r = httpx.get(
        f"{BASE}/{date}",
        params={"from": from_ccy, "to": to_ccy},
        timeout=10.0,
        follow_redirects=True,
    )
    r.raise_for_status()
    rate = r.json()["rates"][to_ccy]
    _historical_cache.set(key, rate)
    return str(rate)


@app.tool()
def convert(amount: float, from_ccy: str, to_ccy: str, date: str = "latest") -> str:
    """Convert an amount between currencies, optionally on a past date (YYYY-MM-DD)."""
    r = httpx.get(
        f"{BASE}/{date}",
        params={"from": from_ccy, "to": to_ccy, "amount": amount},
        timeout=10.0,
        follow_redirects=True,
    )
    r.raise_for_status()
    result = r.json()["rates"][to_ccy]
    return str(result)


if __name__ == "__main__":
    asyncio.run(app.run_stdio_async())
