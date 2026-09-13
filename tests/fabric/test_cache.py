from __future__ import annotations

from autofde_lab.fabric.cache import SQLiteERRCCache


def test_cache_records_hits_misses_and_namespaces() -> None:
    with SQLiteERRCCache(":memory:") as cache:
        assert cache.get("missing") is None
        cache.put("a", "solve", {"value": 1})
        assert cache.get("a") == {"value": 1}

        stats = cache.stats()

    assert stats["entries"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["writes"] == 1
    assert stats["namespaces"] == {"solve": 1}


def test_hotset_measures_top_twenty_percent() -> None:
    with SQLiteERRCCache(":memory:") as cache:
        for index in range(10):
            cache.put(str(index), "solve", {"index": index})
        for _ in range(80):
            cache.get("0")
        for index in range(1, 10):
            cache.get(str(index))

        report = cache.hotset()

    assert report["active_entries"] == 10
    assert report["top_20_percent_count"] == 2
    assert report["top_20_percent_hit_share"] > 0.8
    assert report["pareto_target_reached_within_20_percent"] is True
