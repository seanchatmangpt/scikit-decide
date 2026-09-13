# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The external-recompute acceptance test: standing without the runtime.

Chicago style throughout, and here that is not a stylistic preference -- it is
the only way this suite could mean anything. The claim under test is *"a third
party can recompute this standing from files alone"*. A mocked artifact would
be a file this repo's runtime invented for the occasion, which is precisely the
self-attestation the check exists to rule out. So: a real
:func:`run_real_trial` against a real gymact provider over a real subprocess
bridge, real receipts in a real SQLite ledger, the real
:func:`build_level4_ocel` reader, and real mutations of real bytes on disk.

Three things are asserted, and the third is the load-bearing one:

1. a complete artifact set recomputes ``EXTERNALLY_RECOMPUTABLE``;
2. deleting any ONE required artifact yields ``UNKNOWN:ARTIFACTS_ABSENT``
   naming that artifact -- never a pass, and never a failed join, because an
   unasked question did not get a "no"
   (``.claude/rules/absence-is-not-evidence.md``);
3. each strengthened join **can fail**. A check that cannot fail is not being
   performed, so every join is falsified once by deleting the typed edge or
   the typed identity it depends on -- while leaving the corresponding id
   present elsewhere in the document as a bare token, which is exactly what
   the previous, weaker version of this module accepted.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sqlite3

import pytest

from autofde_lab.hub.domain.gym_procedure.external_recompute import (
    REQUIRED_ARTIFACTS,
    recompute,
)
from autofde_lab.hub.domain.gym_procedure.level4_crown import run_real_trial
from autofde_lab.hub.domain.gym_procedure.level4_ocel import (
    build_level4_ocel,
    link_commitment_ttl,
)


@pytest.fixture(scope="module")
def recomputable_trial(tmp_path_factory) -> pathlib.Path:
    """One real executed trial, with the full durable artifact set on disk.

    The `link_commitment_ttl` + `level4.ocel.json` write is the documented
    emit path for the rich log (`level4_ocel`'s module docstring); it is
    performed here because no runner emits it yet -- a real gap, reported
    rather than papered over, and it belongs to `level4_crown.py`, which this
    test does not own.
    """
    root = tmp_path_factory.mktemp("external_recompute")
    report = run_real_trial(
        3979297810, "resource_flow", {"target": 3, "capacity": 4, "mine_rate": 1}, root
    )
    if report.outcome != "EXECUTED":
        pytest.skip(
            f"UNSUPPORTED: trial did not reach actuation (outcome={report.outcome}); "
            "there is no actuation artifact set to recompute from"
        )
    evidence = pathlib.Path(report.evidence_dir)
    built = build_level4_ocel(evidence)
    assert built.episode_id is not None and built.environment_id is not None
    link_commitment_ttl(
        evidence / "actuation" / "commitment.ttl",
        episode_id=built.episode_id,
        environment_id=built.environment_id,
    )
    rebuilt = build_level4_ocel(evidence)
    (evidence / "actuation" / "level4.ocel.json").write_text(
        json.dumps(rebuilt.log.to_ocel2_json(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return evidence


@pytest.fixture
def scratch_trial(recomputable_trial: pathlib.Path, tmp_path) -> pathlib.Path:
    """A byte-for-byte copy, so mutation tests never share state."""
    dest = tmp_path / recomputable_trial.name
    shutil.copytree(recomputable_trial, dest)
    return dest


def _ocel(trial: pathlib.Path) -> dict:
    return json.loads((trial / "actuation" / "level4.ocel.json").read_text(encoding="utf-8"))


def _write_ocel(trial: pathlib.Path, document: dict) -> None:
    (trial / "actuation" / "level4.ocel.json").write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def _join(standing, name: str):
    (result,) = [j for j in standing.joins if j.join == name]
    return result


# ── 1. the complete set recomputes ───────────────────────────────────────


def test_complete_artifact_set_is_externally_recomputable(recomputable_trial) -> None:
    standing = recompute(recomputable_trial)
    assert standing.verdict() == "EXTERNALLY_RECOMPUTABLE", "\n".join(standing.report())
    assert standing.unestablished() == []
    assert len(standing.joins) == 5
    # Every established join must exhibit a witness -- an OK with no named
    # identity would be an assertion, not evidence.
    for j in standing.joins:
        assert j.witness, f"{j.join} established without naming any identity"


# ── 2. absence is UNKNOWN, naming the artifact ───────────────────────────


@pytest.mark.parametrize("artifact", REQUIRED_ARTIFACTS)
def test_deleting_any_one_artifact_yields_unknown_naming_it(scratch_trial, artifact) -> None:
    (scratch_trial / "actuation" / artifact).unlink()
    standing = recompute(scratch_trial)

    verdict = standing.verdict()
    assert verdict.startswith("UNKNOWN:ARTIFACTS_ABSENT:"), verdict
    assert artifact in verdict.split(":", 2)[2].split(",")
    assert standing.missing_artifacts == (artifact,)
    # Not a pass, and not a failed join: no join was evaluated at all.
    assert standing.joins == ()
    assert "EXTERNALLY_RECOMPUTABLE" not in verdict
    assert "JOIN_NOT_ESTABLISHED" not in verdict


# ── 3. every strengthened join can fail ──────────────────────────────────


def test_receipt_parents_fails_without_typed_caused_by_edges(scratch_trial) -> None:
    """The exact defect the previous version could not detect.

    Only the `caused_by` relationships are removed. Every parent receipt id
    remains in the document as an object id and as a token, so a check based
    on string co-occurrence would still report OK here. The typed check must
    not.
    """
    doc = _ocel(scratch_trial)
    removed = 0
    for obj in doc["objects"]:
        keep = [r for r in obj.get("relationships", []) if r.get("qualifier") != "caused_by"]
        removed += len(obj.get("relationships", [])) - len(keep)
        obj["relationships"] = keep
    assert removed > 0, "fixture carried no caused_by edges, so this test proves nothing"
    _write_ocel(scratch_trial, doc)

    standing = recompute(scratch_trial)
    parents = _join(standing, "receipt->parents")
    assert not parents.established, parents.detail
    assert "caused_by" in parents.detail
    assert standing.verdict() == "UNKNOWN:JOIN_NOT_ESTABLISHED:receipt->parents"

    # The tokens are still there -- proving the failure is about the edge, not
    # about the ids having gone missing. Parent ids come from the real ledger.
    raw = (scratch_trial / "actuation" / "level4.ocel.json").read_text(encoding="utf-8")
    con = sqlite3.connect(f"file:{scratch_trial / 'actuation' / 'receipts.sqlite3'}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT receipt_json FROM receipt_evidence").fetchall()
    finally:
        con.close()
    parent_ids = {p for (rj,) in rows for p in (json.loads(rj).get("parent_receipt_ids") or [])}
    assert parent_ids
    for parent_id in parent_ids:
        assert parent_id in raw, f"{parent_id} vanished; this test would prove nothing"


def test_authority_actuation_fails_without_typed_authorized_by_edge(scratch_trial) -> None:
    doc = _ocel(scratch_trial)
    removed = 0
    for obj in doc["objects"]:
        keep = [r for r in obj.get("relationships", []) if r.get("qualifier") != "authorized_by"]
        removed += len(obj.get("relationships", [])) - len(keep)
        obj["relationships"] = keep
    assert removed > 0
    _write_ocel(scratch_trial, doc)

    result = _join(recompute(scratch_trial), "authority->actuation")
    assert not result.established, result.detail
    assert result.detail.startswith("0/")


def test_postcondition_fails_when_it_observes_a_different_actuation(scratch_trial) -> None:
    """Observing *some* actuation is not observing THIS one."""
    doc = _ocel(scratch_trial)
    retargeted = 0
    for obj in doc["objects"]:
        for rel in obj.get("relationships", []):
            if rel.get("qualifier") == "observes_actuation":
                rel["objectId"] = "urn:level4:actuation:not-a-real-receipt"
                retargeted += 1
    assert retargeted > 0
    _write_ocel(scratch_trial, doc)

    result = _join(recompute(scratch_trial), "postcondition->actuation")
    assert not result.established, result.detail
    assert result.detail.startswith("0/")


def test_replay_fails_when_it_does_not_bind_the_ledger_head(scratch_trial) -> None:
    doc = _ocel(scratch_trial)
    tampered = 0
    for obj in doc["objects"]:
        if obj.get("type") == "Replay":
            for attr in obj.get("attributes", []):
                if attr.get("name") == "head_digest":
                    attr["value"] = "0" * 64
                    tampered += 1
    assert tampered > 0
    _write_ocel(scratch_trial, doc)

    result = _join(recompute(scratch_trial), "replay->receipt")
    assert not result.established, result.detail
    assert "no Replay object binds the ledger chain head" in result.detail


def test_commitment_episode_fails_on_a_plan_digest_disagreement(scratch_trial) -> None:
    """Adjacency, and even a correct episode id, is not the join.

    The commitment keeps its episode id -- only the plan digest is changed, so
    the two documents still share plenty of identities. The join must require
    the commitment and the log to agree on *which plan* was committed.
    """
    ttl_path = scratch_trial / "actuation" / "commitment.ttl"
    turtle = ttl_path.read_text(encoding="utf-8")
    doc = _ocel(scratch_trial)
    (commitment,) = [o for o in doc["objects"] if o["type"] == "POWLCommitment"]
    real_digest = next(a["value"] for a in commitment["attributes"] if a["name"] == "plan_digest")
    assert real_digest in turtle
    ttl_path.write_text(turtle.replace(real_digest, "f" * len(real_digest)), encoding="utf-8")

    result = _join(recompute(scratch_trial), "commitment->episode")
    assert not result.established, result.detail
    assert "no POWLCommitment object agrees" in result.detail
