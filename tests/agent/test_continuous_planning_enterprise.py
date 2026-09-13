# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Fortune-5 qualification falsifiers for continuous planning memory.

These tests exercise persistence, corruption refusal, concurrent writers,
restart recovery, tenant/workload isolation, bounded storage, large candidate
sets, and the invariant that retrieval never becomes admission. No test
actuates a world or grants execution authority.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pytest

from autofde_lab.agent.continuous_planning import (
    ContinuousPlanner,
    PlanApplicability,
    PlanArtifact,
    PlanDisposition,
    PlanningContext,
)
from autofde_lab.agent.persistent_plan_cache import (
    PersistentPlanCorruption,
    SQLitePlanCache,
)
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder


def _plan(index: int, *, required_facts: frozenset[str] = frozenset()) -> PlanArtifact:
    model = PartialOrder(
        (
            Atom("observe", action="urn:action:observe", bindings={"tenant": index}),
            Atom("repair", action="urn:action:repair", bindings={"tenant": index}),
            Atom("verify", action="urn:action:verify", bindings={"tenant": index}),
        ),
        frozenset({OrderEdge(0, 1), OrderEdge(1, 2)}),
    )
    return PlanArtifact(
        model=model,
        applicability=PlanApplicability(
            goal="restore-service",
            required_facts=required_facts,
            required_capabilities=frozenset({"kubectl"}),
            constraint_digest="policy-v1",
            semantic_revision="cloud-v1",
        ),
        planner="powl-enterprise",
        planner_parameters={"candidate": index, "beam": 16},
        dependency_keys={
            (0,): frozenset({"fact:control-plane"}),
            (1,): frozenset({"fact:target"}),
            (2,): frozenset({"fact:target"}),
        },
        downstream={(0,): frozenset({(1,)}), (1,): frozenset({(2,)})},
        family_id="restore-service",
        version=index + 1,
        required_authority_classes=("cloud-operator",),
    )


def _context(*, facts: frozenset[str] = frozenset()) -> PlanningContext:
    return PlanningContext(
        goal="restore-service",
        facts=facts,
        capabilities=frozenset({"kubectl"}),
        constraint_digest="policy-v1",
        semantic_revision="cloud-v1",
    )


def test_sqlite_cache_survives_restart_and_preserves_exact_identity(tmp_path) -> None:
    path = tmp_path / "plans.sqlite3"
    first = SQLitePlanCache(path)
    plan = _plan(7, required_facts=frozenset({"healthy"}))
    key = first.remember(plan)

    # New object, new SQLite connection lifecycle: this is a process-restart
    # analogue, not an in-memory object identity check.
    reopened = SQLitePlanCache(path)
    recovered = reopened.exact(key)

    assert recovered is not None
    assert recovered.exact_key == plan.exact_key
    assert recovered.model_sha256 == plan.model_sha256
    assert recovered.required_authority_classes == ("cloud-operator",)
    assert not hasattr(recovered, "execute")
    assert not hasattr(recovered, "authorize")


def test_durable_cache_refuses_memory_only_sqlite_mode() -> None:
    with pytest.raises(
        ValueError,
        match="UNSUPPORTED:PERSISTENT_PLAN_CACHE_REQUIRES_FILE",
    ):
        SQLitePlanCache(":memory:")


def test_persistent_cache_namespaces_do_not_enumerate_each_other(tmp_path) -> None:
    path = tmp_path / "plans.sqlite3"
    alpha = SQLitePlanCache(path, namespace="tenant-alpha")
    beta = SQLitePlanCache(path, namespace="tenant-beta")
    plan = _plan(8)
    key = alpha.remember(plan)

    assert alpha.exact(key) == plan
    assert alpha.retrieve_candidates(_context()) == (plan,)
    assert beta.exact(key) is None
    assert beta.retrieve_candidates(_context()) == ()
    assert beta.count() == 0

    # The same content identity may exist independently in another namespace
    # without making either namespace able to enumerate the other.
    assert beta.remember(plan) == key
    assert alpha.count() == 1
    assert beta.count() == 1


def test_persistent_cache_capacity_evicts_oldest_candidates_per_namespace(
    tmp_path,
) -> None:
    path = tmp_path / "plans.sqlite3"
    cache = SQLitePlanCache(path, namespace="bounded", max_entries=10)
    keys = [cache.remember(_plan(index)) for index in range(20)]

    assert cache.count() == 10
    assert all(cache.exact(key) is None for key in keys[:10])
    assert all(cache.exact(key) is not None for key in keys[10:])

    # A neighboring namespace gets its own independent capacity budget.
    neighbor = SQLitePlanCache(path, namespace="neighbor", max_entries=3)
    for index in range(3):
        neighbor.remember(_plan(100 + index))
    assert neighbor.count() == 3
    assert cache.count() == 10


def test_persistent_cache_file_is_owner_only_on_posix(tmp_path) -> None:
    path = tmp_path / "plans.sqlite3"
    SQLitePlanCache(path)
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_persistent_retrieval_still_requires_fresh_admission(tmp_path) -> None:
    cache = SQLitePlanCache(tmp_path / "plans.sqlite3")
    plan = _plan(1, required_facts=frozenset({"secret-fact"}))
    cache.remember(plan)
    context = _context()

    assert cache.retrieve_candidates(context) == (plan,)
    decision = ContinuousPlanner(cache=cache).decide(context)  # type: ignore[arg-type]
    assert decision.disposition is PlanDisposition.FRESH_PLAN
    assert decision.plan is None


def test_persistent_cache_refuses_tampered_payload_before_reuse(tmp_path) -> None:
    path = tmp_path / "plans.sqlite3"
    cache = SQLitePlanCache(path)
    plan = _plan(2)
    key = cache.remember(plan)

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE plan_artifacts SET artifact_json = ? WHERE exact_key = ?",
            ('{"schema":"tampered"}', key),
        )
        connection.commit()

    with pytest.raises(
        PersistentPlanCorruption,
        match="REFUSED:PERSISTED_PLAN_DIGEST_MISMATCH",
    ):
        cache.exact(key)


def test_concurrent_writers_are_atomic_and_lossless(tmp_path) -> None:
    cache = SQLitePlanCache(tmp_path / "plans.sqlite3")
    plans = tuple(_plan(index) for index in range(256))

    with ThreadPoolExecutor(max_workers=16) as pool:
        keys = tuple(pool.map(cache.remember, plans))

    assert len(set(keys)) == len(plans)
    assert cache.count() == len(plans)
    recovered = cache.retrieve_candidates(_context())
    assert {plan.exact_key for plan in recovered} == set(keys)


def test_ten_thousand_candidate_retrieval_is_deterministic_and_bounded(
    tmp_path,
) -> None:
    cache = SQLitePlanCache(tmp_path / "plans.sqlite3")
    plans = tuple(_plan(index) for index in range(10_000))
    for plan in plans:
        cache.remember(plan)

    started = perf_counter()
    first = cache.retrieve_candidates(_context())
    first_elapsed = perf_counter() - started
    second = cache.retrieve_candidates(_context())

    assert len(first) == 10_000
    assert tuple(plan.exact_key for plan in first) == tuple(
        sorted(plan.exact_key for plan in plans)
    )
    assert tuple(plan.exact_key for plan in second) == tuple(
        plan.exact_key for plan in first
    )
    # This is an anti-catastrophic-regression budget, deliberately loose for
    # shared CI hardware. Detailed throughput is recorded by the benchmark.
    assert first_elapsed < 30.0
