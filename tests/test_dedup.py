import time
import pytest
from tools.cache import TTLCache


def test_ttl_expiry():
    c = TTLCache(ttl_seconds=1)
    c.set("k", "v")
    assert c.get("k") == "v"
    time.sleep(1.1)
    assert c.get("k") is None


def test_permanent_cache():
    c = TTLCache(ttl_seconds=None)
    c.set("k", "v")
    assert c.get("k") == "v"


def test_make_key_canonical():
    c = TTLCache()
    k1 = c.make_key(ticker="MSFT", year=2024)
    k2 = c.make_key(year=2024, ticker="MSFT")
    assert k1 == k2   # sort_keys=True ensures order independence


def test_cache_miss_returns_none():
    c = TTLCache()
    assert c.get("nonexistent") is None


def test_stats_track_hits_and_misses():
    c = TTLCache()
    c.set("x", 42)
    c.get("x")        # hit
    c.get("missing")  # miss
    stats = c.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_overwrite_resets_ttl():
    c = TTLCache(ttl_seconds=1)
    c.set("k", "v1")
    time.sleep(0.6)
    c.set("k", "v2")   # reset TTL
    time.sleep(0.6)
    assert c.get("k") == "v2"   # should still be alive (total ~1.2s but TTL reset at 0.6s)


def test_reset_stats():
    c = TTLCache()
    c.set("k", "v")
    c.get("k")
    c.reset_stats()
    assert c.stats() == {"hits": 0, "misses": 0}
