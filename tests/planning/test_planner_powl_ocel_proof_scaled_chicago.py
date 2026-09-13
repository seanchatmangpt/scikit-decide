# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Scaled, multi-domain / multi-solver extension of
`test_planner_powl_ocel_proof_chicago.py`'s single-plan correctness proof.

The existing proof chains planner -> POWL -> OCEL -> conformance for exactly
one real plan (one domain, `Astar` only, via a hand-rolled rollout). That is
a degenerate case for anything shaped like "precision" or "generalization":
one linear trace against a net mined from itself trivially fits, and there is
nothing to generalize *from* or *away* from. This module scales the same real
pipeline to real multiple domains x real multiple solvers, using the actual
`autofde_lab.reasoning.planner_federation.federate` function (not a
hand-rolled rollout loop) so more than one real case can land in one real
multi-trace OCEL log before discovery/conformance ever runs.

What is proven here
--------------------
1. `federate()` produces at least two real, distinct, independently
   `validate_model`-accepted `PartialOrder` results across two real domains
   (`fortune5-k8s-state-space`, `blocks6`) and up to two real solvers
   (`Astar`, `FF`) each -- exactly which domain x solver combos actually
   solve is discovered by running the real pipeline, not assumed in advance
   (see `planner_federation`'s own module docstring for why `AOstar`/
   `BFWS`/`IW`/`LazyAstar` are excluded from `SOLVER_NAMES` already).
2. Each real case's `PartialOrder` is compatible with
   `autofde_lab.ocel.powl_replay.replay_structural_fires` -- driven directly,
   the same real executor the single-plan proof already uses -- and the
   resulting OCEL log self-conforms under `check_ocel_conformance` with zero
   divergence, for every case, not just one.
3. One real multi-trace wasm4pm-compat JSON document (one trace per real
   case) is built, matching `_write_event_log_json`'s exact shape from
   `tests/ocel/test_wasm4pm_bridge.py`, and run through the real `wpm`
   binary's `discover_petri_net` + `check_conformance` (skipped, never
   faked, when that binary is not built on this machine).
4. Precision/generalization are read and bounds-checked (0.0-1.0, finite)
   only -- never asserted to a "good" threshold. This is not a benchmark
   claim; a handful of real short plans across two small domains is not a
   corpus large enough to earn a quality verdict, only a real, finite number
   to report honestly.

What this does NOT claim
-------------------------
- Not a benchmark against any other planner or tool.
- Not a claim that precision/generalization here are "good" -- only that
  they are real, bounded, finite numbers computed by a real external miner
  over more than one real trace, which the single-plan proof could not
  produce.
- The real case count is whatever the real solvers actually produce this
  run (>= 2, not a fixed exact number) -- `AOstar`-style silent hangs or a
  solver failing on one domain are real, expected, and reported, not
  papered over.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from autofde_lab.ocel.powl_replay import replay_structural_fires
from autofde_lab.ocel.wasm4pm_bridge import (
    Wasm4pmUnavailable,
    _string_attr,
    check_conformance,
    discover_petri_net,
    resolve_wpm_binary,
)
from autofde_lab.powl.algebra import PartialOrder
from autofde_lab.powl.conformance import check_ocel_conformance, observed_labels_from_events
from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.planner_federation import federate

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.join(_HERE, "..", "..")

DOMAINS: dict[str, tuple[str, str]] = {
    "fortune5-k8s-state-space": (
        os.path.join(_REPO_ROOT, "docs", "planning", "fortune5-k8s-state-space", "domain.pddl"),
        os.path.join(_REPO_ROOT, "docs", "planning", "fortune5-k8s-state-space", "problem.pddl"),
    ),
    "blocks6": (
        os.path.join(
            _REPO_ROOT, "tests", "domains", "python", "pddl_domains", "blocks", "domain.pddl"
        ),
        os.path.join(_REPO_ROOT, "tests", "reasoning", "fixtures", "blocks6-problem.pddl"),
    ),
}


@dataclass(frozen=True)
class FederationCase:
    domain_name: str
    solver_name: str
    partial_order: PartialOrder


@pytest.fixture(scope="module")
def federation_results() -> list[FederationCase]:
    """One real `federate()` call per domain (2 calls total, not 4) -- each
    call already runs every solver in `SOLVER_NAMES` internally. Every
    non-`None`, already-`validate_model`-validated `PartialOrder` result
    (validation happens inside `federate()` itself) becomes one real case."""
    cases: list[FederationCase] = []
    for domain_name, (domain_path, problem_path) in DOMAINS.items():
        results = federate(domain_path=domain_path, problem_path=problem_path, timeout_s=60.0)
        for solver_name, partial_order in results.items():
            if partial_order is None:
                print(f"[federation] {domain_name} x {solver_name}: did not solve")
                continue
            # Real, independent second validation at this call site too --
            # `federate()` already validated internally; re-checking here
            # costs nothing and means this test's own claim ("every case is
            # a validated PartialOrder") doesn't just trust the callee.
            validate_model(partial_order)
            print(
                f"[federation] {domain_name} x {solver_name}: solved, "
                f"{len(partial_order.children)} steps"
            )
            cases.append(
                FederationCase(
                    domain_name=domain_name,
                    solver_name=solver_name,
                    partial_order=partial_order,
                )
            )
    assert len(cases) >= 2, (
        f"expected at least 2 real domain x solver cases to solve, got "
        f"{len(cases)}: {[(c.domain_name, c.solver_name) for c in cases]}"
    )
    return cases


def test_at_least_two_real_domain_solver_combinations_solved(
    federation_results: list[FederationCase],
) -> None:
    assert len(federation_results) >= 2
    for case in federation_results:
        assert isinstance(case.partial_order, PartialOrder)
        assert len(case.partial_order.children) >= 2


# ── Per-case: replay + self-conformance, for every real case ───────────────


def test_every_case_replays_and_self_conforms(federation_results: list[FederationCase]) -> None:
    """Each case's real `PartialOrder` (as returned by `planner_federation`)
    is driven directly through `replay_structural_fires` -- the same real
    executor path the single-plan proof already trusts -- and the resulting
    OCEL log must self-conform with zero divergence. Proves compatibility
    between `planner_federation`'s `PartialOrder` shape and
    `replay_structural_fires`/`check_ocel_conformance` by actually running
    it, not by inspection."""
    for case in federation_results:
        log = replay_structural_fires(case.partial_order)
        log.validate()

        result = check_ocel_conformance(case.partial_order, log.events)
        assert result.conforms is True, (
            f"{case.domain_name} x {case.solver_name}: self-replay diverged at "
            f"index={result.divergence_index} label={result.divergence_label}"
        )
        assert result.final is True
        assert result.divergence_index is None
        assert result.fired_count == result.observed_count == len(case.partial_order.children)


# ── Multi-trace wasm4pm-compat log + real external discovery/conformance ──


def _require_wpm() -> str:
    try:
        return resolve_wpm_binary()
    except Wasm4pmUnavailable as exc:
        pytest.skip(str(exc))


def test_real_external_discovery_and_quality_dimensions_over_multiple_traces(
    federation_results: list[FederationCase], tmp_path: Path
) -> None:
    """One real multi-trace wasm4pm-compat JSON log -- one trace per real
    federation case -- run through the real `wpm` binary's discover +
    conformance commands. Matches `_write_event_log_json`'s exact document
    shape from `tests/ocel/test_wasm4pm_bridge.py` (top-level
    attributes/traces/extensions/classifiers/global_*_attrs keys; each
    trace an attributes+events dict; each event a single `concept:name`
    string attribute)."""
    binary = _require_wpm()

    traces = []
    for case in federation_results:
        # Replay each case's own tree independently (not reusing the log
        # from the self-conformance test above) so this stage stands alone
        # and reflects exactly what `observed_labels_from_events` reads off
        # a fresh, real replay.
        log = replay_structural_fires(case.partial_order)
        labels = observed_labels_from_events(log.events)
        assert labels, f"{case.domain_name} x {case.solver_name}: no fired labels to trace"

        case_name = f"{case.domain_name}::{case.solver_name}"
        traces.append(
            {
                "attributes": [_string_attr("concept:name", case_name)],
                "events": [
                    {"attributes": [_string_attr("concept:name", label)]} for label in labels
                ],
            }
        )

    doc = {
        "attributes": [],
        "traces": traces,
        "extensions": None,
        "classifiers": None,
        "global_trace_attrs": None,
        "global_event_attrs": None,
    }
    log_path = tmp_path / "scaled_plan_log.json"
    log_path.write_text(json.dumps(doc))
    model_path = tmp_path / "scaled_plan_model.pnml"

    discovery = asyncio.run(
        discover_petri_net(log_path, output_path=model_path, wpm_binary=binary, timeout_s=60)
    )
    assert discovery.places > 0
    assert discovery.transitions > 0
    assert 0.0 <= discovery.simplicity <= 1.0
    print(
        f"[discovery] places={discovery.places} transitions={discovery.transitions} "
        f"arcs={discovery.arcs} simplicity={discovery.simplicity} "
        f"self_fitness={discovery.self_fitness}"
    )

    conformance = asyncio.run(
        check_conformance(log_path, model_path, wpm_binary=binary, timeout_s=60)
    )
    assert conformance.total_cases == len(traces) == len(federation_results)
    assert 0.0 <= conformance.avg_fitness <= 1.0
    print(
        f"[conformance] total_cases={conformance.total_cases} "
        f"conforming_cases={conformance.conforming_cases} "
        f"avg_fitness={conformance.avg_fitness}"
    )

    # Real, bounds-only checks -- never a "good" threshold. With >=2 real,
    # distinct cases this is no longer the single-linear-plan degenerate
    # case the original proof explicitly declined to claim precision on;
    # here the numbers are printed and range-checked, still not graded.
    if conformance.precision is not None:
        assert 0.0 <= conformance.precision <= 1.0
        assert conformance.precision == conformance.precision  # not NaN
        print(f"[conformance] precision={conformance.precision}")
    else:
        print("[conformance] precision: absent (older wpm build)")

    if conformance.generalization is not None:
        assert 0.0 <= conformance.generalization <= 1.0
        assert conformance.generalization == conformance.generalization  # not NaN
        print(f"[conformance] generalization={conformance.generalization}")
    else:
        print("[conformance] generalization: absent (older wpm build)")
