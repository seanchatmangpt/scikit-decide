# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The producer emits every witness edge at the causal moment it becomes true.

Chicago style throughout: a real ``run_real_trial`` (real probing, real
planner federation, a real gymact actuation subprocess, a real sqlite receipt
ledger, a real replay), real files on disk, and the real
``standalone_verifier`` executed as a **fresh subprocess** over the persisted
evidence directory. No mock, no stub, no monkeypatch, and no in-process call
to the verifier -- an in-process call would have the producing runtime in
``sys.modules`` and could not establish independence.

What is under test is not "does an edge exist" but *where the edge came from*:

* Every required relation is written to ``witness.jsonl`` by the producer at
  its own transition -- goal admission, candidate selection, commitment,
  independent goal verification, replay -- and :func:`build_level4_ocel`
  emits the typed O2O edge ONLY from such a record.
* Delete the journal and the same executed episode reconstructs strictly
  fewer relations. That is the falsifier: if the chain survived the journal's
  removal, the edges were being inferred from something adjacent (ordering,
  digests, filenames) rather than stated, which is exactly the post-hoc join
  ``.claude/rules/no-dual-bookkeeping.md`` refuses.
* A pre-emitter artifact -- the same trial reduced to gymact's own
  ``episode.ocel.json`` -- must stay at zero reconstructed relations
  permanently.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import run_real_trial
from autofde_lab.hub.domain.gym_procedure.level4_ocel import (
    WITNESS_JOURNAL_NAME,
    WitnessJournal,
    build_level4_ocel,
    link_commitment_ttl,
)

_VERIFIER = (
    pathlib.Path(__file__).parents[2]
    / "src"
    / "autofde_lab"
    / "hub"
    / "domain"
    / "gym_procedure"
    / "standalone_verifier.py"
)


def _write_level4_ocel(trial: pathlib.Path) -> None:
    built = build_level4_ocel(trial)
    assert built.episode_id is not None and built.environment_id is not None
    link_commitment_ttl(
        trial / "actuation" / "commitment.ttl",
        episode_id=built.episode_id,
        environment_id=built.environment_id,
    )
    rebuilt = build_level4_ocel(trial)
    (trial / "actuation" / "level4.ocel.json").write_text(
        json.dumps(rebuilt.log.to_ocel2_json(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _verify(trial: pathlib.Path) -> subprocess.CompletedProcess:
    """The real verifier, in a real fresh process. Never imported here."""
    return subprocess.run(
        [sys.executable, str(_VERIFIER), str(trial)],
        capture_output=True,
        text=True,
        check=False,
    )


def _established(stdout: str) -> set[str]:
    return {
        line.strip()[3:].split(":", 1)[0].strip()
        for line in stdout.splitlines()
        if line.strip().startswith("OK ")
    }


@pytest.fixture(scope="module")
def executed_trial(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("producer_witness")
    report = run_real_trial(
        3979297810, "resource_flow", {"target": 3, "capacity": 4, "mine_rate": 1}, root
    )
    if report.outcome != "EXECUTED":
        pytest.skip(
            f"UNSUPPORTED: trial did not reach actuation (outcome={report.outcome}); "
            "this suite tests the emitted chain of an executed episode"
        )
    trial = pathlib.Path(report.evidence_dir)
    _write_level4_ocel(trial)
    return trial


# ── the journal is written during execution, not after it ────────────────


def test_the_journal_states_each_relation_with_both_endpoints(executed_trial) -> None:
    records = WitnessJournal.read(executed_trial)
    kinds = {r["kind"] for r in records}
    assert {
        "goal_admitted",
        "candidate_selected",
        "plan_committed",
        "goal_consequence_observed",
        "replay_completed",
    } <= kinds, f"producer did not state every relation: {sorted(kinds)}"

    goal = next(r for r in records if r["kind"] == "goal_admitted")
    selected = next(r for r in records if r["kind"] == "candidate_selected")
    committed = next(r for r in records if r["kind"] == "plan_committed")
    consequence = next(r for r in records if r["kind"] == "goal_consequence_observed")

    # Identity carried forward, not re-derived: the same goal through
    # selection and consequence, the same candidate through commitment.
    assert selected["goal_id"] == goal["goal_id"]
    assert consequence["goal_id"] == goal["goal_id"]
    assert committed["candidate_id"] == selected["candidate_id"]

    # The consequence is an observed outcome, and the observer is a distinct
    # identity from the actuator -- so self-certification is readable off the
    # graph rather than asserted.
    assert consequence["outcome"] in ("ESTABLISHED", "REFUTED")
    assert consequence["verifier_id"] != consequence["actuator_id"]


def test_a_fresh_verifier_reconstructs_the_whole_chain(executed_trial) -> None:
    result = _verify(executed_trial)
    assert "ALIVE_EVIDENCE_RECONSTRUCTED" in result.stdout, result.stdout + result.stderr
    assert result.returncode == 0
    assert "INDEPENDENCE: no execution-runtime module imported" in result.stdout


def test_the_goal_is_a_first_class_object_the_observation_relates_to(executed_trial) -> None:
    ocel = json.loads((executed_trial / "actuation" / "level4.ocel.json").read_text())
    types = {o["id"]: o["type"] for o in ocel["objects"]}
    edges = [
        (o["id"], rel.get("qualifier"), rel.get("objectId"))
        for o in ocel["objects"]
        for rel in (o.get("relationships") or [])
    ]

    def typed(qualifier: str, src: str, tgt: str) -> list[tuple[str, str, str]]:
        return [
            e for e in edges if e[1] == qualifier and types.get(e[0]) == src and types.get(e[2]) == tgt
        ]

    assert typed("goal_of_task", "Goal", "Task"), "no admitted Goal object bound to the Task"
    assert typed("targets_goal", "PlanCandidate", "Goal"), "selected plan not bound to the goal"

    # Conformance and achievement are different claims: exactly one of the two
    # is emitted, and both are real checked observations of the SAME goal.
    established = typed("establishes_goal", "PostconditionObservation", "Goal")
    refuted = typed("refutes_goal", "PostconditionObservation", "Goal")
    assert bool(established) != bool(refuted), (established, refuted)
    assert typed("verified_by", "PostconditionObservation", "IndependentVerifier")


# ── the falsifier: remove the stated relations, lose the chain ───────────


def test_without_the_journal_the_same_episode_reconstructs_strictly_less(
    executed_trial, tmp_path
) -> None:
    """If the chain survived here, the edges were inferred, not stated."""
    with_journal = _established(_verify(executed_trial).stdout)

    stripped = tmp_path / executed_trial.name
    shutil.copytree(executed_trial, stripped)
    (stripped / WITNESS_JOURNAL_NAME).unlink()
    _write_level4_ocel(stripped)

    without_journal = _established(_verify(stripped).stdout)
    assert without_journal < with_journal, (
        "removing the producer's stated relations changed nothing, so those "
        f"relations were being reconstructed rather than read: {without_journal}"
    )
    assert "ALIVE_EVIDENCE_RECONSTRUCTED" not in _verify(stripped).stdout


def test_the_pre_emitter_artifact_stays_at_zero(executed_trial, tmp_path) -> None:
    """gymact's own episode OCEL carries none of the required identities.

    Kept as a permanent regression fixture: a missing join must stay UNKNOWN
    rather than be guessed back into existence by a later, looser reader.
    """
    legacy = tmp_path / ("legacy_" + executed_trial.name)
    shutil.copytree(executed_trial, legacy)
    (legacy / "actuation" / "level4.ocel.json").unlink()
    (legacy / WITNESS_JOURNAL_NAME).unlink()

    result = _verify(legacy)
    assert _established(result.stdout) == set(), result.stdout
    assert "UNKNOWN:CHAIN_INCOMPLETE" in result.stdout
    assert result.returncode == 1
