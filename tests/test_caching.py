from __future__ import annotations

import dataclasses
import json
import pickle
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from autofde_lab.caching import (
    CacheAdmissionError,
    CacheConfig,
    CacheDisposition,
    CacheFabric,
    CacheKey,
    CacheMode,
    CachePolicy,
    CacheRecord,
    CanonicalKeyEncoder,
    Digestor,
    MemoryCacheStore,
    MethodPolicy,
    PickleCodec,
    SQLiteCacheStore,
    TieredCacheStore,
    UnhashableCacheKeyError,
    UnsafeCacheMethodError,
    cache_domain,
    cache_domain_factory,
    make_cache_key,
)


class FakeClock:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass(frozen=True)
class Point:
    x: int
    y: int


class CustomKey:
    def __init__(self, identity: str, noise: object) -> None:
        self.identity = identity
        self.noise = noise

    def __cache_key__(self):
        return self.identity


class Unsupported:
    pass


def make_record(
    digest: str,
    *,
    namespace: str = "domain:v1",
    method: str = "solve",
    payload: bytes = b"value",
    created_at: float = 1000.0,
    expires_at: float | None = None,
    stale_until: float | None = None,
    tags: tuple[str, ...] = (),
) -> CacheRecord:
    key = CacheKey(
        digest=digest,
        algorithm="blake2b",
        namespace=namespace,
        method=method,
        version="1",
        canonical_size=12,
    )
    return CacheRecord(
        key=key,
        value_digest=f"value-{digest}",
        payload=payload,
        codec="test",
        compressed=False,
        created_at=created_at,
        expires_at=expires_at,
        stale_until=stale_until,
        size_bytes=len(payload),
        raw_size_bytes=len(payload),
        tags=tags,
    )


def make_fabric(
    *,
    clock=None,
    persistent_path: Path | None = None,
    memory_entries: int = 64,
) -> CacheFabric:
    active_clock = clock or time.time
    config = CacheConfig(
        memory_max_entries=memory_entries,
        memory_max_bytes=1024 * 1024,
        persistent_path=persistent_path,
        persistent_max_bytes=16 * 1024 * 1024,
        compression_threshold_bytes=1,
    )
    memory = MemoryCacheStore(
        max_entries=memory_entries,
        max_bytes=1024 * 1024,
        clock=active_clock,
    )
    persistent = (
        SQLiteCacheStore(
            persistent_path,
            max_bytes=16 * 1024 * 1024,
            clock=active_clock,
            touch_interval_seconds=0,
        )
        if persistent_path is not None
        else None
    )
    store = TieredCacheStore(memory, persistent)
    digestor = Digestor(config.digest_algorithm)
    codec = PickleCodec(
        digestor=digestor,
        compression_threshold_bytes=config.compression_threshold_bytes,
    )
    return CacheFabric(
        config,
        store=store,
        codec=codec,
        clock=active_clock,
    )


def test_canonical_key_is_order_independent_for_mappings_and_sets():
    encoder = CanonicalKeyEncoder()
    left = {"b": {3, 2, 1}, "a": [Point(1, 2)]}
    right = {"a": [Point(1, 2)], "b": {1, 3, 2}}
    assert encoder.encode(left) == encoder.encode(right)


def test_canonical_key_preserves_type_boundaries():
    encoder = CanonicalKeyEncoder()
    assert encoder.encode(1) != encoder.encode(True)
    assert encoder.encode([1, 2]) != encoder.encode((1, 2))
    assert encoder.encode("1") != encoder.encode(1)


def test_canonical_key_supports_numpy_and_custom_projection():
    encoder = CanonicalKeyEncoder()
    assert encoder.encode(np.array([1, 2], dtype=np.int16)) == encoder.encode(
        np.array([1, 2], dtype=np.int16)
    )
    assert encoder.encode(CustomKey("same", object())) == encoder.encode(
        CustomKey("same", object())
    )


def test_canonical_key_refuses_identity_objects_and_cycles():
    encoder = CanonicalKeyEncoder()
    with pytest.raises(UnhashableCacheKeyError):
        encoder.encode(Unsupported())
    recursive = []
    recursive.append(recursive)
    with pytest.raises(UnhashableCacheKeyError):
        encoder.encode(recursive)


def test_make_cache_key_binds_namespace_method_version_and_inputs():
    encoder = CanonicalKeyEncoder()
    digestor = Digestor("sha256")
    baseline = make_cache_key(
        namespace="n",
        method="m",
        version="1",
        args=(1,),
        kwargs={"x": 2},
        encoder=encoder,
        digestor=digestor,
    )
    changed = make_cache_key(
        namespace="n",
        method="m",
        version="2",
        args=(1,),
        kwargs={"x": 2},
        encoder=encoder,
        digestor=digestor,
    )
    assert baseline.algorithm == "sha256"
    assert baseline.digest != changed.digest


def test_pickle_codec_compresses_verifies_and_isolates_mutation():
    codec = PickleCodec(digestor=Digestor("blake2b"), compression_threshold_bytes=1)
    value = {"items": [1, 2, 3]}
    encoded = codec.encode(value)
    assert encoded.compressed
    first = codec.decode(
        encoded.payload,
        value_digest=encoded.value_digest,
        compressed=encoded.compressed,
    )
    first["items"].append(4)
    second = codec.decode(
        encoded.payload,
        value_digest=encoded.value_digest,
        compressed=encoded.compressed,
    )
    assert second == value


def test_memory_store_promotes_hot_entries_and_evicts_scan_victims():
    store = MemoryCacheStore(max_entries=2, max_bytes=100)
    one = make_record("one")
    two = make_record("two")
    three = make_record("three")
    assert store.put(one)
    assert store.put(two)
    assert store.get(one.key) is not None
    assert store.get(one.key) is not None
    assert store.put(three)
    assert store.get(one.key) is not None
    assert store.info().currsize == 2


def test_memory_store_honors_fresh_stale_and_expired_boundaries():
    clock = FakeClock()
    store = MemoryCacheStore(max_entries=4, max_bytes=100, clock=clock)
    record = make_record("ttl", expires_at=clock() + 5, stale_until=clock() + 10)
    store.put(record)
    assert store.get(record.key).stale is False
    clock.advance(6)
    assert store.get(record.key).stale is True
    clock.advance(5)
    assert store.get(record.key) is None


def test_memory_store_invalidates_by_namespace_method_and_tag():
    store = MemoryCacheStore(max_entries=8, max_bytes=1000)
    a = make_record("a", namespace="n1", method="m1", tags=("task:1",))
    b = make_record("b", namespace="n1", method="m2", tags=("task:2",))
    c = make_record("c", namespace="n2", method="m1", tags=("task:1",))
    for item in (a, b, c):
        store.put(item)
    assert store.invalidate(namespace="n1", method="m1") == 1
    assert store.invalidate(tags=("task:1",)) == 1
    assert store.info().currsize == 1


def test_sqlite_store_persists_across_instances_and_deduplicates_values(tmp_path):
    path = tmp_path / "cache.sqlite3"
    first = SQLiteCacheStore(path, max_bytes=1024 * 1024)
    record_a = make_record("a", payload=b"same")
    record_b = dataclasses.replace(
        make_record("b", payload=b"same"), value_digest=record_a.value_digest
    )
    first.put(record_a)
    first.put(record_b)
    first.close()

    second = SQLiteCacheStore(path, max_bytes=1024 * 1024)
    assert second.get(record_a.key) is not None
    assert second.get(record_b.key) is not None
    connection = sqlite3.connect(path)
    assert connection.execute("SELECT COUNT(*) FROM cache_blobs").fetchone()[0] == 1
    second.close()


def test_sqlite_store_tag_invalidation_cleans_unreferenced_blobs(tmp_path):
    path = tmp_path / "cache.sqlite3"
    store = SQLiteCacheStore(path)
    record = make_record("a", tags=("scenario:alpha",))
    store.put(record)
    assert store.invalidate(tags=("scenario:alpha",)) == 1
    connection = sqlite3.connect(path)
    assert connection.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM cache_blobs").fetchone()[0] == 0


def test_sqlite_leases_coordinate_store_instances(tmp_path):
    path = tmp_path / "cache.sqlite3"
    first = SQLiteCacheStore(path)
    second = SQLiteCacheStore(path)
    assert first.acquire_lease("key", "owner-a", 60)
    assert not second.acquire_lease("key", "owner-b", 60)
    first.release_lease("key", "owner-a")
    assert second.acquire_lease("key", "owner-b", 60)


def test_tiered_store_promotes_l2_hit_into_l1(tmp_path):
    path = tmp_path / "cache.sqlite3"
    l1 = MemoryCacheStore(max_entries=8, max_bytes=1000)
    l2 = SQLiteCacheStore(path)
    record = make_record("promote")
    l2.put(record)
    store = TieredCacheStore(l1, l2)
    assert store.get(record.key).tier == "sqlite"
    assert store.get(record.key).tier == "memory"
    assert store.info().promotions == 1


def test_fabric_caches_once_and_returns_mutation_isolated_hits():
    fabric = make_fabric()
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"values": [1, 2]}

    first = fabric.execute(
        namespace="model:v1", method="query", args=(1,), compute=compute
    )
    first["values"].append(3)
    second = fabric.execute(
        namespace="model:v1", method="query", args=(1,), compute=compute
    )
    assert calls == 1
    assert second == {"values": [1, 2]}
    assert fabric.last_receipt.disposition == CacheDisposition.HIT_L1


def test_fabric_persists_across_process_equivalent_instances(tmp_path):
    path = tmp_path / "cache.sqlite3"
    first = make_fabric(persistent_path=path)
    assert (
        first.execute(
            namespace="model:v1", method="query", args=(1,), compute=lambda: 42
        )
        == 42
    )
    first.close()
    second = make_fabric(persistent_path=path)
    called = False

    def fail_compute():
        nonlocal called
        called = True
        return 99

    assert (
        second.execute(
            namespace="model:v1", method="query", args=(1,), compute=fail_compute
        )
        == 42
    )
    assert not called
    assert second.last_receipt.disposition == CacheDisposition.HIT_L2


def test_fabric_thread_singleflight_computes_once():
    fabric = make_fabric()
    calls = 0
    lock = threading.Lock()

    def compute():
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return "done"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: fabric.execute(
                    namespace="model:v1",
                    method="slow",
                    args=(1,),
                    compute=compute,
                ),
                range(8),
            )
        )
    assert results == ["done"] * 8
    assert calls == 1
    assert fabric.info().waits >= 7


def test_fabric_stale_if_error_is_explicit_and_receipted():
    clock = FakeClock()
    fabric = make_fabric(clock=clock)
    policy = MethodPolicy(ttl_seconds=5, stale_if_error_seconds=10)
    assert (
        fabric.execute(
            namespace="model:v1",
            method="query",
            compute=lambda: "stable",
            policy=policy,
        )
        == "stable"
    )
    clock.advance(6)

    def explode():
        raise RuntimeError("upstream unavailable")

    assert (
        fabric.execute(
            namespace="model:v1", method="query", compute=explode, policy=policy
        )
        == "stable"
    )
    assert fabric.last_receipt.disposition == CacheDisposition.STALE_IF_ERROR
    assert fabric.last_receipt.error_type == "RuntimeError"


def test_fabric_refresh_replaces_a_fresh_value():
    fabric = make_fabric()
    assert fabric.execute(namespace="model:v1", method="query", compute=lambda: 1) == 1
    assert (
        fabric.execute(
            namespace="model:v1",
            method="query",
            compute=lambda: 2,
            mode=CacheMode.REFRESH,
        )
        == 2
    )
    assert fabric.execute(namespace="model:v1", method="query", compute=lambda: 3) == 2


def test_fabric_verify_detects_drift_and_replaces_value():
    fabric = make_fabric()
    assert fabric.execute(namespace="model:v1", method="query", compute=lambda: 1) == 1
    assert (
        fabric.execute(
            namespace="model:v1",
            method="query",
            compute=lambda: 2,
            mode=CacheMode.VERIFY,
        )
        == 2
    )
    assert fabric.execute(namespace="model:v1", method="query", compute=lambda: 3) == 2


def test_fabric_verify_emits_verified_hit_when_value_matches():
    fabric = make_fabric()
    fabric.execute(namespace="model:v1", method="query", compute=lambda: 1)
    result = fabric.execute_with_receipt(
        namespace="model:v1",
        method="query",
        compute=lambda: 1,
        mode=CacheMode.VERIFY,
    )
    assert result.receipt.disposition == CacheDisposition.VERIFIED_HIT
    assert result.receipt.verified


def test_fabric_read_only_miss_never_executes_compute():
    fabric = make_fabric()
    called = False

    def compute():
        nonlocal called
        called = True
        return 1

    with pytest.raises(KeyError):
        fabric.execute(
            namespace="model:v1",
            method="query",
            compute=compute,
            mode=CacheMode.READ_ONLY,
        )
    assert not called


def test_fabric_unhashable_can_bypass_or_refuse():
    fabric = make_fabric()
    value = fabric.execute(
        namespace="model:v1",
        method="query",
        args=(Unsupported(),),
        compute=lambda: 7,
        policy=MethodPolicy(on_unhashable="bypass"),
    )
    assert value == 7
    assert fabric.last_receipt.disposition == CacheDisposition.BYPASS
    with pytest.raises(UnhashableCacheKeyError):
        fabric.execute(
            namespace="model:v1",
            method="query",
            args=(Unsupported(),),
            compute=lambda: 7,
            policy=MethodPolicy(on_unhashable="raise"),
        )


def test_fabric_refuses_private_and_sampling_operations():
    fabric = make_fabric()
    for method in ("_private", "sample_task_duration"):
        with pytest.raises(CacheAdmissionError):
            fabric.execute(namespace="n", method=method, compute=lambda: 1)


def test_fabric_replay_and_receipt_export(tmp_path):
    fabric = make_fabric()
    result = fabric.execute_with_receipt(
        namespace="model:v1", method="query", args=(1,), compute=lambda: {"x": 1}
    )
    replay = fabric.replay(result.receipt.key_digest)
    assert replay.value == {"x": 1}
    path = fabric.export_receipts(tmp_path / "receipts.jsonl")
    lines = path.read_text().splitlines()
    assert len(lines) >= 2
    assert json.loads(lines[-1])["key_digest"] == result.receipt.key_digest


def test_fabric_tag_invalidation_removes_related_scenarios():
    fabric = make_fabric()
    for scenario in ("a", "b"):
        fabric.execute(
            namespace="self-play:v1",
            method="rollout",
            args=(scenario,),
            compute=lambda scenario=scenario: scenario,
            tags=(f"scenario:{scenario}", "corpus:training"),
        )
    assert fabric.invalidate(tags=("corpus:training",)) == 2


def test_policy_rejects_unsafe_methods_and_supports_method_overrides():
    with pytest.raises(UnsafeCacheMethodError):
        CachePolicy.custom("step")
    policy = CachePolicy.model().with_method_policy(
        "is_terminal", MethodPolicy(version="terminal-v2", ttl_seconds=10)
    )
    assert policy.policy_for("is_terminal").version == "terminal-v2"
    assert policy.policy_for("get_applicable_actions").requires_explicit_arguments == {
        "memory"
    }


class Domain:
    def __init__(self) -> None:
        self.calls = 0
        self._memory = 1
        self.steps = 0

    def get_next_state(self, state, action):
        self.calls += 1
        return state + action

    def get_applicable_actions(self, memory=None):
        self.calls += 1
        active = self._memory if memory is None else memory
        return [active]

    def step(self, action):
        self.steps += 1
        self._memory += action
        return self._memory


class CapabilityDomain(Domain):
    pass


def test_cached_domain_preserves_class_identity_and_caches_admitted_methods():
    domain = CapabilityDomain()
    cached = cache_domain(
        domain,
        policy=CachePolicy.custom("get_next_state"),
        namespace="domain:v1",
    )
    assert isinstance(cached, CapabilityDomain)
    assert cached.get_next_state(1, 2) == 3
    assert cached.get_next_state(1, 2) == 3
    assert domain.calls == 1


def test_cached_domain_bypasses_implicit_memory_but_caches_explicit_memory():
    domain = Domain()
    cached = cache_domain(
        domain,
        policy=CachePolicy.custom("get_applicable_actions"),
        namespace="domain:v1",
    )
    assert cached.get_applicable_actions() == [1]
    domain._memory = 2
    assert cached.get_applicable_actions() == [2]
    assert cached.get_applicable_actions(memory=5) == [5]
    assert cached.get_applicable_actions(memory=5) == [5]
    assert domain.calls == 3


def test_cached_domain_never_intercepts_actuation():
    domain = Domain()
    cached = cache_domain(
        domain,
        policy=CachePolicy.custom("get_next_state"),
        namespace="domain:v1",
    )
    assert cached.step(1) == 2
    assert cached.step(1) == 3
    assert domain.steps == 2


def test_cached_domain_method_invalidation_is_scoped():
    domain = Domain()
    cached = cache_domain(
        domain,
        policy=CachePolicy.custom("get_next_state"),
        namespace="domain:v1",
    )
    cached.get_next_state(1, 2)
    cached.get_next_state(1, 2)
    assert domain.calls == 1
    assert cached.invalidate_cache("get_next_state") == 1
    cached.get_next_state(1, 2)
    assert domain.calls == 2


def test_cached_domain_is_pickle_safe_and_rebuilds_process_local_l1(tmp_path):
    path = tmp_path / "cache.sqlite3"
    cached = cache_domain(
        Domain(),
        policy=CachePolicy.custom("get_next_state"),
        namespace="domain:v1",
        config=CacheConfig(persistent_path=path),
    )
    cached.get_next_state(1, 2)
    restored = pickle.loads(pickle.dumps(cached))
    assert restored.get_next_state(1, 2) == 3
    assert restored.__wrapped__.calls == 1
    assert restored.cache_fabric.last_receipt.disposition == CacheDisposition.HIT_L2


def create_domain():
    return Domain()


def test_cached_domain_factory_shares_cache_across_solver_domain_instances():
    factory = cache_domain_factory(
        create_domain,
        policy=CachePolicy.custom("get_next_state"),
        namespace="planner-model:v1",
    )
    first = factory()
    second = factory()
    assert first.get_next_state(1, 2) == 3
    assert second.get_next_state(1, 2) == 3
    assert first.__wrapped__.calls == 1
    assert second.__wrapped__.calls == 0


def test_cached_domain_factory_requires_explicit_equivalence_namespace():
    with pytest.raises(ValueError):
        cache_domain_factory(
            create_domain,
            policy=CachePolicy.custom("get_next_state"),
            namespace="",
        )


def test_cached_domain_factory_is_pickle_safe(tmp_path):
    factory = cache_domain_factory(
        create_domain,
        policy=CachePolicy.custom("get_next_state"),
        namespace="planner-model:v1",
        config=CacheConfig(persistent_path=tmp_path / "cache.sqlite3"),
    )
    restored = pickle.loads(pickle.dumps(factory))
    assert restored().get_next_state(1, 2) == 3


def test_context_mode_bypass_is_scoped():
    fabric = make_fabric()
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return calls

    assert fabric.execute(namespace="n", method="m", compute=compute) == 1
    with fabric.mode(CacheMode.BYPASS):
        assert fabric.execute(namespace="n", method="m", compute=compute) == 2
    assert fabric.execute(namespace="n", method="m", compute=compute) == 1


def test_custom_key_function_can_project_large_or_unsupported_inputs():
    fabric = make_fabric()
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return calls

    policy = MethodPolicy(key_fn=lambda args, kwargs: args[0].identity)
    first = fabric.execute(
        namespace="n",
        method="m",
        args=(CustomKey("x", object()),),
        compute=compute,
        policy=policy,
    )
    second = fabric.execute(
        namespace="n",
        method="m",
        args=(CustomKey("x", object()),),
        compute=compute,
        policy=policy,
    )
    assert (first, second, calls) == (1, 1, 1)


def test_persistent_payload_corruption_is_detected(tmp_path):
    from autofde_lab.caching import CacheCorruptionError

    path = tmp_path / "cache.sqlite3"
    first = make_fabric(persistent_path=path)
    result = first.execute_with_receipt(
        namespace="model:v1", method="query", compute=lambda: {"safe": True}
    )
    first.close()

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE cache_blobs SET payload=? WHERE digest=?",
        (b"corrupted", result.receipt.value_digest),
    )
    connection.commit()
    connection.close()

    second = make_fabric(persistent_path=path)
    with pytest.raises(CacheCorruptionError):
        second.execute(
            namespace="model:v1",
            method="query",
            compute=lambda: {"safe": False},
        )


def test_self_play_reuses_repeated_scenario_topology():
    fabric = make_fabric(memory_entries=128)
    computations = 0
    scenarios = [index % 20 for index in range(1000)]

    def evaluate(scenario: int):
        nonlocal computations
        computations += 1
        return {"scenario": scenario, "score": scenario * scenario}

    outputs = [
        fabric.execute(
            namespace="self-play-corpus:v3",
            method="evaluate_scenario",
            args=(scenario,),
            compute=lambda scenario=scenario: evaluate(scenario),
            tags=(f"scenario:{scenario}", "self-play"),
        )
        for scenario in scenarios
    ]
    assert computations == 20
    assert len(outputs) == 1000
    assert fabric.info().hit_rate > 0.95


def test_cross_process_singleflight_manufactures_once(tmp_path):
    import os
    import subprocess
    import sys
    import textwrap

    cache_path = tmp_path / "cache.sqlite3"
    counter_path = tmp_path / "counter.sqlite3"
    connection = sqlite3.connect(counter_path)
    connection.execute("CREATE TABLE counter(value INTEGER NOT NULL)")
    connection.execute("INSERT INTO counter(value) VALUES(0)")
    connection.commit()
    connection.close()

    script = textwrap.dedent(
        """
        import sqlite3
        import sys
        import time
        from autofde_lab.caching import CacheConfig, CacheFabric, MethodPolicy

        cache_path, counter_path = sys.argv[1], sys.argv[2]
        fabric = CacheFabric(CacheConfig(persistent_path=cache_path))

        def compute():
            connection = sqlite3.connect(counter_path, timeout=10)
            connection.execute('BEGIN IMMEDIATE')
            value = connection.execute('SELECT value FROM counter').fetchone()[0] + 1
            connection.execute('UPDATE counter SET value=?', (value,))
            connection.commit()
            connection.close()
            time.sleep(0.25)
            return 77

        result = fabric.execute(
            namespace='shared-model:v1',
            method='expensive',
            args=(1,),
            compute=compute,
            policy=MethodPolicy(
                lease_seconds=5,
                lease_wait_seconds=10,
                lease_poll_seconds=0.01,
            ),
        )
        print(result)
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    commands = [
        [sys.executable, "-c", script, str(cache_path), str(counter_path)]
        for _ in range(2)
    ]
    processes = [
        subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for command in commands
    ]
    results = [process.communicate(timeout=20) for process in processes]
    assert [process.returncode for process in processes] == [0, 0], results
    assert [stdout.strip() for stdout, _ in results] == ["77", "77"]
    connection = sqlite3.connect(counter_path)
    assert connection.execute("SELECT value FROM counter").fetchone()[0] == 1
