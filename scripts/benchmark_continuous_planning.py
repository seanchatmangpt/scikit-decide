#!/usr/bin/env python3
"""Deterministic continuous-planning qualification benchmark.

This is a regression court, not a marketing benchmark. Thresholds are
intentionally loose enough for shared CI runners while still catching
algorithmic or persistence collapses. Output is one JSON object suitable for
retention as a workflow artifact.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from time import perf_counter

from autofde_lab.agent.continuous_planning import (
    ObservationDelta,
    PlanApplicability,
    PlanArtifact,
    PlanCache,
    PlanningContext,
    affected_paths,
)
from autofde_lab.agent.persistent_plan_cache import SQLitePlanCache
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder

MODEL = PartialOrder(
    (
        Atom("observe", action="urn:bench:observe"),
        Atom("repair", action="urn:bench:repair"),
    ),
    frozenset({OrderEdge(0, 1)}),
)
APP = PlanApplicability(
    goal="restore-service",
    required_capabilities=frozenset({"kubectl"}),
    constraint_digest="policy-v1",
    semantic_revision="cloud-v1",
)
CONTEXT = PlanningContext(
    goal="restore-service",
    capabilities=frozenset({"kubectl"}),
    constraint_digest="policy-v1",
    semantic_revision="cloud-v1",
)


def plan(index: int) -> PlanArtifact:
    return PlanArtifact(
        model=MODEL,
        applicability=APP,
        planner="enterprise-bench",
        planner_parameters={"candidate": index},
        family_id="restore-service",
        version=index + 1,
    )


def rate(count: int, elapsed: float) -> float:
    return count / max(elapsed, 1e-9)


def main() -> int:
    memory_count = 20_000
    persistent_count = 2_000
    closure_count = 20_000

    memory = PlanCache()
    started = perf_counter()
    for index in range(memory_count):
        memory.remember(plan(index))
    memory_insert_s = perf_counter() - started

    started = perf_counter()
    candidates = memory.retrieve_candidates(CONTEXT)
    memory_retrieve_s = perf_counter() - started
    assert len(candidates) == memory_count

    with tempfile.TemporaryDirectory(prefix="autofde-plan-bench-") as directory:
        persistent = SQLitePlanCache(Path(directory) / "plans.sqlite3")
        started = perf_counter()
        for index in range(persistent_count):
            persistent.remember(plan(index))
        sqlite_insert_s = perf_counter() - started

        started = perf_counter()
        persisted = persistent.retrieve_candidates(CONTEXT)
        sqlite_retrieve_s = perf_counter() - started
        assert len(persisted) == persistent_count

    dependencies = {
        (index,): frozenset({"fact:root"}) if index == 0 else frozenset()
        for index in range(closure_count)
    }
    downstream = {
        (index,): frozenset({(index + 1,)}) for index in range(closure_count - 1)
    }
    closure_plan = PlanArtifact(
        model=MODEL,
        applicability=APP,
        planner="enterprise-bench",
        dependency_keys=dependencies,
        downstream=downstream,
    )
    started = perf_counter()
    affected = affected_paths(
        closure_plan,
        ObservationDelta(frozenset({"fact:root"})),
    )
    closure_s = perf_counter() - started
    assert len(affected) == closure_count

    metrics = {
        "schema": "urn:autofde-lab:continuous-planning-benchmark:1",
        "memory": {
            "count": memory_count,
            "insert_seconds": memory_insert_s,
            "insert_ops_per_second": rate(memory_count, memory_insert_s),
            "retrieve_seconds": memory_retrieve_s,
            "retrieve_candidates_per_second": rate(memory_count, memory_retrieve_s),
        },
        "sqlite": {
            "count": persistent_count,
            "insert_seconds": sqlite_insert_s,
            "insert_ops_per_second": rate(persistent_count, sqlite_insert_s),
            "retrieve_seconds": sqlite_retrieve_s,
            "retrieve_candidates_per_second": rate(persistent_count, sqlite_retrieve_s),
        },
        "delta_closure": {
            "nodes": closure_count,
            "seconds": closure_s,
            "nodes_per_second": rate(closure_count, closure_s),
        },
    }

    # Anti-collapse budgets, not aspirational SLOs. These are deliberately
    # conservative for shared hosted runners and should be tightened from
    # retained production-hardware baselines rather than guessed.
    failures: list[str] = []
    if metrics["memory"]["insert_ops_per_second"] < 500:
        failures.append("MEMORY_INSERT_THROUGHPUT")
    if metrics["memory"]["retrieve_candidates_per_second"] < 1_000:
        failures.append("MEMORY_RETRIEVAL_THROUGHPUT")
    if metrics["sqlite"]["insert_ops_per_second"] < 20:
        failures.append("SQLITE_INSERT_THROUGHPUT")
    if metrics["sqlite"]["retrieve_candidates_per_second"] < 100:
        failures.append("SQLITE_RETRIEVAL_THROUGHPUT")
    if metrics["delta_closure"]["nodes_per_second"] < 10_000:
        failures.append("DELTA_CLOSURE_THROUGHPUT")

    metrics["standing"] = "ALIVE" if not failures else "BUILD_BROKEN"
    metrics["failures"] = failures
    print(json.dumps(metrics, sort_keys=True, separators=(",", ":")))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
