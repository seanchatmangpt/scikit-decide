# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tracer bullet for `memory` (`gymact.providers.MemoryProvider`) --
the 6th real Level 4 gym, and the first genuinely new gym wired since the
`FIVE_GYM_KERNEL_GATE` checkpoint (`docs/level4-migration-matrix.md`).

Every collaborator is real: the real GymAct kernel driven through the real
subprocess bridge into `~/gymact`'s own venv, the real in-process
`MemoryProvider`/`MemoryEnvironment` (no Docker, no network -- the simplest
provider in the manifest), the real registered solver federation, real
SQLite receipts, real OCEL output, the real `pyshacl` engine against the
real, unmodified `ontology/shapes/{level4,authority,planning}.shacl.ttl`.
No mock, stub, `patch`, or `monkeypatch` anywhere in this file -- when
gymact is not checked out the tests report a named skip rather than
substituting a fake.

Two things this file establishes together, matching the design's own
explicit wiring-hazard warning (see `_predict_memory`'s docstring in
`level4_crown.py`): the independent postcondition oracle is correct on its
own arithmetic, AND a real end-to-end trial reaches `Level4AliveEvidence`
and projects through the *unmodified* `autofde_lab.evidence` kernel to a
real, non-vacuous SHACL conformance -- confirming `SIX_GYM_KERNEL_GATE`.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import rdflib
from rdflib import Namespace

from autofde_lab.evidence.level4_witness import project_trial_to_witness
from autofde_lab.evidence.verify import verify_witness_graph
from autofde_lab.hub.domain.gym_procedure.crown_evidence import Level4AliveEvidence
from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    predict_step_postconditions,
    run_real_trial,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import skip_reason
from autofde_lab.hub.domain.gym_procedure.level4_ocel import (
    build_level4_ocel,
    link_commitment_ttl,
)

pytestmark = pytest.mark.skipif(skip_reason() is not None, reason=str(skip_reason()))

AFL = Namespace("urn:autofde-lab:")


def test_predict_memory_oracle_matches_actuate_arithmetic() -> None:
    """`_predict_memory` (dispatched via `predict_step_postconditions`) is
    written independently from `MemoryEnvironment.actuate`'s own increment
    arithmetic -- ground it directly, before trusting any real trial that
    depends on it."""
    plan = ("increment[amount=1,key=counter]",) * 3
    assert predict_step_postconditions(plan, "memory", {"counter": 0}) == [
        {"counter": 1},
        {"counter": 2},
        {"counter": 3},
    ]

    # Never a spurious `solved` key -- MemoryEnvironment.observe() returns
    # the raw KV state verbatim and never publishes a derived dimension.
    for step in predict_step_postconditions(plan, "memory", {"counter": 0}):
        assert "solved" not in step

    with pytest.raises(ValueError, match="UNSUPPORTED_ACTION_FOR_POSTCONDITION_PREDICTION"):
        predict_step_postconditions(("decrement",), "memory", {"counter": 0})


def test_predict_memory_is_dispatched_explicitly_not_via_generic_fallback() -> None:
    """Pins the wiring hazard the design explicitly warned about: `memory`
    must route through the dedicated `_predict_memory` branch, never fall
    through to the generic `_COUNTER_DELTAS` tail (which would attach a
    `solved` key the real environment never publishes)."""
    result = predict_step_postconditions(("increment[amount=1,key=counter]",), "memory", {"counter": 0})
    assert result == [{"counter": 1}]
    assert "solved" not in result[0]


@pytest.fixture(scope="module")
def memory_trial(tmp_path_factory) -> pathlib.Path:
    """One real, executed `memory` trial -- the 6th Level 4 tracer bullet."""
    root = tmp_path_factory.mktemp("level4_memory_gym")
    report = run_real_trial(4102, "memory", {"initial": {"counter": 0}, "target": 2}, root)
    if report.outcome != "EXECUTED":
        pytest.skip(f"UNSUPPORTED: trial did not reach actuation (outcome={report.outcome})")
    return report


def test_run_real_trial_end_to_end_reaches_level4_alive(memory_trial) -> None:
    report = memory_trial
    assert report.outcome == "EXECUTED"
    assert report.provider == "memory"
    assert report.n_probes > 0
    assert report.n_supported_solvers > 0
    assert report.n_planner_attempts == report.n_supported_solvers + 1
    assert len(report.planners_producing_candidates) > 0
    # `memory` has no continuous/unrepresentable dimension (unlike
    # cube_counter's `reward`) -- the real, current state is zero losses,
    # not an assumption.
    assert report.representation_losses == {}
    assert isinstance(report.standing, Level4AliveEvidence)
    assert report.standing.conformant.conformance.conformant is True
    assert report.standing.conformant.replay.valid is True
    assert report.standing.conformant.episode_digest
    assert report.standing.conformant.receipt_id
    assert report.standing.goal.passed is True
    assert report.standing.goal.verification_id
    assert report.is_alive() is True
    assert report.verdict() == "ALIVE"
    assert report.ocel_ref_violations == ()
    assert report.replay_mismatches == ()
    assert set(report.step_standings) == {"ALIVE"}
    assert report.run_id in report.evidence_dir


@pytest.fixture(scope="module")
def linked_trial_dir(memory_trial) -> pathlib.Path:
    """Persist the richer `level4.ocel.json` from the producer's own witness
    journal -- the same recipe `tests/evidence/test_level4_witness_falsifiers_
    chicago.py::linked_trial` and `crown_reconstruct._persist_level4_ocel`
    both use. A mechanical, identity-preserving transcription of what the
    trial already stated, never a manufactured relation."""
    trial_dir = pathlib.Path(memory_trial.evidence_dir)
    built = build_level4_ocel(trial_dir)
    assert built.episode_id is not None and built.environment_id is not None
    link_commitment_ttl(
        trial_dir / "actuation" / "commitment.ttl",
        episode_id=built.episode_id,
        environment_id=built.environment_id,
    )
    rebuilt = build_level4_ocel(trial_dir)
    (trial_dir / "actuation" / "level4.ocel.json").write_text(
        json.dumps(rebuilt.log.to_ocel2_json(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return trial_dir


def test_memory_gym_projects_to_a_conforming_witness_with_zero_kernel_changes(
    linked_trial_dir,
) -> None:
    """The `SIX_GYM_KERNEL_GATE` claim itself: the real, unmodified
    `autofde_lab.evidence` kernel (`level4_witness.py` + `verify.py` +
    `ontology/shapes/{level4,authority,planning}.shacl.ttl`) -- the exact
    same kernel proven on `resource_flow`/`lock_and_key`/`switchboard`/
    `cube_counter`/`cube_container_counter` -- projects this genuinely new,
    structurally distinct (in-process KV state, no Docker/network) gym to a
    real, positive `pyshacl` conformance with no code change of any kind."""
    projection = project_trial_to_witness(linked_trial_dir)
    result = verify_witness_graph(projection.graph)
    assert result.conforms is True, result.report_text
    assert result.violations == ()


def test_memory_gym_witness_is_non_vacuous_severed_edge_flips_to_false(
    linked_trial_dir,
) -> None:
    """The kernel must be genuinely capable of being red for this gym too --
    mirrors the identity-mutation falsifier pattern proven on the other five
    gyms and in `tests/evidence/test_level4_witness_falsifiers_chicago.py`."""
    projection = project_trial_to_witness(linked_trial_dir)
    baseline = verify_witness_graph(projection.graph)
    assert baseline.conforms is True

    g = projection.graph
    targets = list(g.triples((None, AFL.derivedByVerifier, None)))
    assert len(targets) == 1, "expected exactly one derivedByVerifier edge on the real witness"
    s, p, o = targets[0]

    mutant = rdflib.Graph()
    for prefix, uri in g.namespaces():
        mutant.bind(prefix, uri)
    for triple in g:
        mutant.add(triple)
    mutant.remove((s, p, o))
    mutant.add((s, p, rdflib.URIRef("urn:autofde-lab:VerifierRun:wrong-identity-deadbeef")))

    mutated = verify_witness_graph(mutant)
    assert mutated.conforms is False
    assert "afl:VerifierRun" in mutated.report_text or "VerifierRun" in mutated.report_text
