# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Swap one identity; the fresh verifier must reject.

A fully populated graph and a causally correct one look identical until you
mutate an identity. These fixtures do exactly that: build a complete OCEL
episode carrying all seven explicit chain edges, confirm the standalone
verifier reconstructs standing from it, then repoint ONE edge at the wrong
object and require the verdict to collapse.

This is what distinguishes explicit causal identity from a graph that merely
has enough nodes in it. Edge *count* closure is necessary and not sufficient:
7/7 edges that point at the wrong objects is a conforming-looking graph
describing an execution that did not happen.

The fixture is hand-built rather than produced by a trial ON PURPOSE. The
producer does not yet emit these edges (a real trial reconstructs 0/7 today),
so this file specifies the contract the producer must satisfy, and fails the
moment the verifier is loosened to accept something weaker. It is the
acceptance test for the emitter, written before the emitter.

No mocks: the verifier under test is the real
`standalone_verifier.verify`, run over real JSON/SQLite artifacts written to a
real temp directory.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.standalone_verifier import (
    REQUIRED_CHAIN,
    verify,
)

_VERIFIER = (
    Path(__file__).resolve().parents[2]
    / "src/autofde_lab/hub/domain/gym_procedure/standalone_verifier.py"
)

ACTUATION = "act-1"
COMMITMENT = "commit-1"
CANDIDATE = "cand-1"
AUTHORITY = "auth-1"
OBSERVATION = "obs-1"
RECEIPT_A = "rcpt-a"
RECEIPT_B = "rcpt-b"
REPLAY = "replay-1"

DECOY_ACTUATION = "act-DECOY"
DECOY_COMMITMENT = "commit-DECOY"
DECOY_RECEIPT = "rcpt-DECOY"


def _obj(oid: str, otype: str, rels: list[tuple[str, str]] | None = None) -> dict:
    return {
        "id": oid,
        "type": otype,
        "attributes": [],
        "relationships": [
            {"objectId": target, "qualifier": qual} for qual, target in (rels or [])
        ],
    }


def _complete_log() -> dict:
    """An episode carrying every one of the seven explicit chain edges."""
    objects = [
        _obj(CANDIDATE, "PlanCandidate"),
        _obj(COMMITMENT, "POWLCommitment", [("realizes_candidate", CANDIDATE)]),
        _obj(DECOY_COMMITMENT, "POWLCommitment", [("realizes_candidate", CANDIDATE)]),
        _obj(AUTHORITY, "AuthorityEnvelope"),
        _obj(
            ACTUATION,
            "Actuation",
            [("actuates_commitment", COMMITMENT), ("authorized_by", AUTHORITY)],
        ),
        _obj(DECOY_ACTUATION, "Actuation"),
        _obj(OBSERVATION, "PostconditionObservation", [("observes_actuation", ACTUATION)]),
        _obj(RECEIPT_A, "Receipt"),
        _obj(RECEIPT_B, "Receipt", [("caused_by", RECEIPT_A)]),
        _obj(DECOY_RECEIPT, "Receipt"),
        _obj(REPLAY, "Replay", [("replays", RECEIPT_B)]),
    ]
    return {
        "eventTypes": [{"name": "ActuationClosed", "attributes": []}],
        "objectTypes": [
            {"name": t, "attributes": []}
            for t in sorted(
                {
                    "PlanCandidate",
                    "POWLCommitment",
                    "AuthorityEnvelope",
                    "Actuation",
                    "PostconditionObservation",
                    "Receipt",
                    "Replay",
                }
            )
        ],
        "events": [
            {
                "id": "evt-1",
                "type": "ActuationClosed",
                "time": "2026-08-08T12:00:00Z",
                "attributes": [],
                "relationships": [{"objectId": ACTUATION, "qualifier": "actuation"}],
            }
        ],
        "objects": objects,
    }


def _write_trial(root: Path, log: dict) -> Path:
    act = root / "actuation"
    act.mkdir(parents=True, exist_ok=True)
    (act / "level4.ocel.json").write_text(json.dumps(log, sort_keys=True, separators=(",", ":")))
    (act / "commitment.ttl").write_text(
        '@prefix powl: <urn:powl:> .\n'
        f'<urn:commitment:{COMMITMENT}> powl:episodeId "ep-1" .\n'
    )
    con = sqlite3.connect(act / "receipts.sqlite3")
    con.execute(
        "CREATE TABLE receipt_evidence (sequence INTEGER PRIMARY KEY, receipt_id TEXT, "
        "previous_digest TEXT, receipt_digest TEXT, record_digest TEXT, receipt_json TEXT)"
    )
    for seq, (rid, parents) in enumerate([(RECEIPT_A, []), (RECEIPT_B, [RECEIPT_A])]):
        con.execute(
            "INSERT INTO receipt_evidence VALUES (?,?,?,?,?,?)",
            (
                seq,
                rid,
                None,
                f"d{seq}",
                f"r{seq}",
                json.dumps(
                    {
                        "receipt_id": rid,
                        "operation": "act",
                        "authority_ref": "urn:test:authority",
                        "parent_receipt_ids": parents,
                    }
                ),
            ),
        )
    con.commit()
    con.close()
    return root


def test_complete_chain_reconstructs_from_artifacts_alone(tmp_path: Path):
    """Baseline: all seven explicit edges present -> standing reconstructed."""
    trial = _write_trial(tmp_path / "complete", _complete_log())
    standing = verify(trial)
    assert standing.unestablished() == [], "\n".join(standing.report())
    assert standing.verdict() == "ALIVE_EVIDENCE_RECONSTRUCTED", standing.verdict()


@pytest.mark.parametrize(
    ("mutation", "expected_broken"),
    [
        ("actuation_points_at_wrong_commitment", "commitment->actuation"),
        ("authority_bound_to_wrong_actuation", "authority->actuation"),
        ("observation_observes_wrong_actuation", "actuation->postcondition"),
        ("replay_replays_wrong_receipt", "replay->receipt"),
        ("receipt_ancestry_removed", "receipt->dag"),
    ],
)
def test_swapping_one_identity_is_rejected(tmp_path: Path, mutation: str, expected_broken: str):
    """Mutate exactly ONE identity. The graph stays fully populated and every
    activity is still present -- only the causal target changes. The verdict
    must collapse anyway, because a conforming-looking graph describing an
    execution that did not happen is not evidence."""
    log = _complete_log()
    by_id = {o["id"]: o for o in log["objects"]}

    def repoint(oid: str, qualifier: str, new_target: str) -> None:
        for rel in by_id[oid]["relationships"]:
            if rel["qualifier"] == qualifier:
                rel["objectId"] = new_target

    if mutation == "actuation_points_at_wrong_commitment":
        # Still a real POWLCommitment -- just not the one that was committed.
        repoint(ACTUATION, "actuates_commitment", DECOY_COMMITMENT)
        by_id[DECOY_COMMITMENT]["type"] = "PlanCandidate"  # break the typed edge
    elif mutation == "authority_bound_to_wrong_actuation":
        by_id[DECOY_ACTUATION]["relationships"].append(
            {"objectId": AUTHORITY, "qualifier": "authorized_by"}
        )
        by_id[ACTUATION]["relationships"] = [
            r for r in by_id[ACTUATION]["relationships"] if r["qualifier"] != "authorized_by"
        ]
    elif mutation == "observation_observes_wrong_actuation":
        repoint(OBSERVATION, "observes_actuation", DECOY_ACTUATION)
        by_id[DECOY_ACTUATION]["type"] = "Receipt"  # no longer an Actuation
    elif mutation == "replay_replays_wrong_receipt":
        repoint(REPLAY, "replays", DECOY_RECEIPT)
        by_id[DECOY_RECEIPT]["type"] = "PlanCandidate"
    elif mutation == "receipt_ancestry_removed":
        by_id[RECEIPT_B]["relationships"] = []
    else:  # pragma: no cover - parametrize guards this
        raise AssertionError(mutation)

    trial = _write_trial(tmp_path / mutation, log)
    standing = verify(trial)

    assert expected_broken in standing.unestablished(), (
        f"mutation {mutation!r} left {expected_broken} established:\n"
        + "\n".join(standing.report())
    )
    assert standing.verdict().startswith("UNKNOWN:CHAIN_INCOMPLETE"), standing.verdict()


def test_edge_count_closure_is_not_sufficient(tmp_path: Path):
    """7 edges pointing at the wrong objects is not 7/7.

    The strongest confusion this suite exists to prevent: a graph can be fully
    populated -- every qualifier present, every activity emitted -- while
    describing an execution that never occurred. Count closure is necessary,
    never sufficient."""
    log = _complete_log()
    by_id = {o["id"]: o for o in log["objects"]}
    # Same NUMBER of relationships, all pointing somewhere real, none correct.
    by_id[ACTUATION]["relationships"] = [
        {"objectId": CANDIDATE, "qualifier": "actuates_commitment"},
        {"objectId": RECEIPT_A, "qualifier": "authorized_by"},
    ]
    trial = _write_trial(tmp_path / "populated_but_wrong", log)
    standing = verify(trial)

    total_rels = sum(len(o["relationships"]) for o in log["objects"])
    assert total_rels >= 7, total_rels  # the graph is not sparse
    assert "commitment->actuation" in standing.unestablished()
    assert "authority->actuation" in standing.unestablished()


def test_verifier_runs_independently_in_a_fresh_process(tmp_path: Path):
    """The destructive criterion: a separate process, given only files, with
    zero producer imports. Enforced by the verifier's own
    assert_no_runtime_imports, so independence is checked and not asserted."""
    trial = _write_trial(tmp_path / "fresh", _complete_log())
    completed = subprocess.run(
        [sys.executable, str(_VERIFIER), str(trial)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "INDEPENDENCE: no execution-runtime module imported" in completed.stdout, (
        completed.stdout + completed.stderr
    )
    assert "ALIVE_EVIDENCE_RECONSTRUCTED" in completed.stdout, completed.stdout
    assert completed.returncode == 0, completed.stderr


def test_every_required_chain_edge_has_a_mutation_guard():
    """Coverage guard: if a new chain edge is added to REQUIRED_CHAIN, this
    file must gain a mutation for it. Otherwise an unguarded edge could be
    satisfied incidentally and nothing here would notice."""
    guarded = {
        "commitment->actuation",
        "authority->actuation",
        "actuation->postcondition",
        "replay->receipt",
        "receipt->dag",
    }
    declared = {name for name, _ in REQUIRED_CHAIN}
    unguarded = declared - guarded
    assert unguarded == {"plan_candidate->commitment", "postcondition->independent"}, (
        f"REQUIRED_CHAIN changed; unguarded edges are now {sorted(unguarded)}. "
        f"Add a mutation fixture for each new edge."
    )
