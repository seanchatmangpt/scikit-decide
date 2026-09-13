# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A verifier that does not trust — or import — the runtime that produced the evidence.

This is the destructive test for dual bookkeeping, and the strongest claim the
Level 4 architecture can make:

    1. Run the frozen crown.
    2. Persist OCEL 2.0 + commitment + receipts + replay artifacts.
    3. Discard ALL in-memory TrialReport / CrownRun / runtime state.
    4. Start a FRESH process.
    5. Give it only the durable artifacts.
    6. Recompute standing.
    7. Require the same typed standing from evidence alone.

If a fresh process can reconstruct

    PlanCandidate -> POWLCommitment -> AuthorityEnvelope -> Actuation
    -> independent PostconditionObservation -> Receipt DAG -> Replay

without importing the execution runtime, then **standing is no longer owned by
the actor**. The consequence has independently acquired standing. That is a
different and much stronger claim than a green test suite, which only says the
actor agrees with itself.

## The import discipline is the test

This module imports the standard library and (optionally) rdflib. It must
NEVER import `level4_crown`, `level4_crown_runner`, `level4_gymact_bridge`,
`level4_ocel`, `typed_induction`, `gymact`, or anything else that participates
in producing evidence. :func:`assert_no_runtime_imports` enforces that at
runtime by inspecting `sys.modules` after a verification, so the discipline is
checked rather than merely intended. A verifier that imports the producer is
not independent, however carefully it is written.

## Identity is explicit or it does not exist

An identity join may be established ONLY by an explicit typed edge. Never by:
timestamps, filename similarity, token overlap, activity ordering alone,
matching labels, or matching counts. Each of those is a correlation that
happens to hold; none is a statement the producer committed to.

A consequence worth stating plainly: **tightening a join may lower the count**,
e.g. 2/5 -> 1/5. If the previous join was incidental, that is a CORRECT
regression and the lower number is the more honest one. Do not optimize this
module toward a green result; optimize toward every required identity being
explicit in durable evidence.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Modules whose presence would mean the verifier is not independent.
FORBIDDEN_RUNTIME_MODULES: tuple[str, ...] = (
    "autofde_lab.hub.domain.gym_procedure.level4_crown",
    "autofde_lab.hub.domain.gym_procedure.level4_crown_runner",
    "autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge",
    "autofde_lab.hub.domain.gym_procedure.level4_ocel",
    "autofde_lab.hub.domain.gym_procedure.typed_induction",
    "gymact",
)

#: The chain a third party must be able to reconstruct, in order. Each entry is
#: (edge_name, human question). An edge is established only by an explicit
#: typed relationship in the durable evidence.
REQUIRED_CHAIN: tuple[tuple[str, str], ...] = (
    ("plan_candidate->commitment", "was the committed procedure the one that was selected?"),
    ("commitment->actuation", "was this actuation the realization of that exact commitment?"),
    ("authority->actuation", "was this exact actuation authorized by this exact envelope?"),
    ("actuation->postcondition", "was THIS actuation independently observed?"),
    ("postcondition->independent", "was the observer identity distinct from the actuator?"),
    ("receipt->dag", "is the receipt ancestry an explicit edge, not a shared token?"),
    ("replay->receipt", "did a replay bind the exact source receipt?"),
)


@dataclass(frozen=True)
class Edge:
    name: str
    question: str
    established: bool
    basis: str  # exactly what evidence established it, or why nothing did
    witness: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndependentStanding:
    """What a third party can conclude from artifacts alone."""

    trial_dir: str
    edges: tuple[Edge, ...]
    artifacts_seen: tuple[str, ...]
    artifacts_absent: tuple[str, ...]

    def unestablished(self) -> list[str]:
        return [e.name for e in self.edges if not e.established]

    def verdict(self) -> str:
        if self.artifacts_absent:
            return f"UNKNOWN:ARTIFACTS_ABSENT:{','.join(self.artifacts_absent)}"
        missing = self.unestablished()
        if missing:
            return f"UNKNOWN:CHAIN_INCOMPLETE:{','.join(missing)}"
        return "ALIVE_EVIDENCE_RECONSTRUCTED"

    def report(self) -> list[str]:
        return [f"{'OK ' if e.established else '-- '}{e.name}: {e.basis}" for e in self.edges]


def _load_json(path: Path) -> Optional[dict]:
    return json.loads(path.read_text()) if path.is_file() else None


def _receipts(ledger: Path) -> list[dict]:
    con = sqlite3.connect(ledger)
    try:
        rows = con.execute(
            "SELECT receipt_json FROM receipt_evidence ORDER BY sequence"
        ).fetchall()
    finally:
        con.close()
    return [json.loads(r[0]) for r in rows]


def _o2o_edges(ocel: dict) -> list[tuple[str, str, str]]:
    """Explicit object-to-object relationships only: (source, qualifier, target).

    Event-to-object links are NOT counted here. An event referencing two
    objects does not assert that those objects are related to each other --
    treating co-reference as a relationship is precisely the incidental join
    this module refuses.
    """
    edges: list[tuple[str, str, str]] = []
    for obj in ocel.get("objects", []) or []:
        for rel in obj.get("relationships", []) or []:
            target = rel.get("objectId")
            if target:
                edges.append((obj.get("id", ""), rel.get("qualifier", ""), target))
    return edges


def verify(trial_dir: Path) -> IndependentStanding:
    """Reconstruct standing from durable artifacts. Files only, explicit edges only."""
    act = trial_dir / "actuation"
    candidates = {
        "ocel": act / "level4.ocel.json",
        "ocel_legacy": act / "episode.ocel.json",
        "commitment": act / "commitment.ttl",
        "ledger": act / "receipts.sqlite3",
    }
    ocel = _load_json(candidates["ocel"]) or _load_json(candidates["ocel_legacy"])
    ttl = candidates["commitment"].read_text() if candidates["commitment"].is_file() else None
    ledger = candidates["ledger"] if candidates["ledger"].is_file() else None

    seen = [k for k, p in candidates.items() if p.is_file()]
    absent = [
        name
        for name, present in (
            ("ocel", ocel is not None),
            ("commitment.ttl", ttl is not None),
            ("receipts.sqlite3", ledger is not None),
        )
        if not present
    ]
    if absent:
        return IndependentStanding(str(trial_dir), (), tuple(seen), tuple(absent))

    assert ocel is not None and ttl is not None and ledger is not None
    receipts = _receipts(ledger)
    edges = _o2o_edges(ocel)
    by_qualifier: dict[str, list[tuple[str, str, str]]] = {}
    for src, qual, tgt in edges:
        by_qualifier.setdefault(qual, []).append((src, qual, tgt))

    obj_types = {o.get("id"): o.get("type") for o in ocel.get("objects", []) or []}

    def typed_edge(qualifier: str, src_type: str, tgt_type: str) -> list[tuple[str, str, str]]:
        return [
            (s, q, t)
            for s, q, t in by_qualifier.get(qualifier, [])
            if obj_types.get(s) == src_type and obj_types.get(t) == tgt_type
        ]

    results: list[Edge] = []

    def add(name: str, question: str, found: list, basis_ok: str, basis_no: str) -> None:
        results.append(
            Edge(
                name,
                question,
                bool(found),
                basis_ok if found else basis_no,
                tuple(f"{s}-[{q}]->{t}" for s, q, t in found[:3]),
            )
        )

    # Each of these demands an EXPLICIT typed O2O edge. No token matching.
    pc = typed_edge("realizes_candidate", "POWLCommitment", "PlanCandidate") or typed_edge(
        "commits_candidate", "POWLCommitment", "PlanCandidate"
    )
    add(
        "plan_candidate->commitment",
        REQUIRED_CHAIN[0][1],
        pc,
        f"{len(pc)} explicit POWLCommitment->PlanCandidate edge(s)",
        "no explicit typed edge from POWLCommitment to PlanCandidate",
    )

    # THE CHAIN MUST BE CHAINED.
    #
    # Checking each edge for mere EXISTENCE is the correct-sequence/wrong-identity
    # hole: a graph can hold an Actuation->Commitment edge AND an
    # Actuation->Authority edge while they hang off DIFFERENT actuations, so
    # nothing was ever both committed and authorized. A mutation fixture caught
    # exactly that here. Each link below is therefore anchored to the SAME
    # actuation identity carried forward from the previous link.
    ca = typed_edge("actuates_commitment", "Actuation", "POWLCommitment")
    committed_actuations = {s_ for s_, _, _ in ca}
    add(
        "commitment->actuation",
        REQUIRED_CHAIN[1][1],
        ca,
        f"{len(ca)} explicit Actuation->POWLCommitment edge(s)",
        "no explicit typed edge from Actuation to POWLCommitment",
    )

    # Authority must bind an actuation that is ALSO committed -- not merely some
    # actuation somewhere in the graph.
    aa = [
        (s_, q_, t_)
        for s_, q_, t_ in typed_edge("authorized_by", "Actuation", "AuthorityEnvelope")
        if s_ in committed_actuations
    ]
    authorized_actuations = {s_ for s_, _, _ in aa}
    add(
        "authority->actuation",
        REQUIRED_CHAIN[2][1],
        aa,
        f"{len(aa)} authority edge(s) on an actuation that is also committed",
        "no AuthorityEnvelope bound to a COMMITTED actuation "
        "(an authority edge on some other actuation does not authorize this one)",
    )

    # The observation must observe an actuation that is committed AND authorized.
    ap = [
        (s_, q_, t_)
        for s_, q_, t_ in typed_edge("observes_actuation", "PostconditionObservation", "Actuation")
        if t_ in authorized_actuations
    ]
    add(
        "actuation->postcondition",
        REQUIRED_CHAIN[3][1],
        ap,
        f"{len(ap)} observation(s) of a committed+authorized actuation",
        "no PostconditionObservation observes a committed+authorized actuation",
    )

    # Independence: the observer is not the thing it observes.
    independent = [(s_, q_, t_) for s_, q_, t_ in ap if s_ != t_]
    add(
        "postcondition->independent",
        REQUIRED_CHAIN[4][1],
        independent,
        f"{len(independent)} observation(s) whose observer identity differs from the actuation",
        "observer identity not distinguishable from actuator in the graph",
    )

    caused = typed_edge("caused_by", "Receipt", "Receipt")
    ledger_parents = sum(len(r.get("parent_receipt_ids") or []) for r in receipts)
    add(
        "receipt->dag",
        REQUIRED_CHAIN[5][1],
        caused,
        f"{len(caused)} explicit Receipt->Receipt caused_by edge(s) "
        f"(ledger records {ledger_parents} parent refs)",
        f"ledger records {ledger_parents} parent refs but the OCEL carries NO explicit "
        f"Receipt->Receipt edge (token co-occurrence does not count)",
    )

    # Replay must bind a receipt that is actually in the ancestry DAG, not any
    # object that happens to be typed Receipt.
    dag_receipts = {s_ for s_, _, _ in caused} | {t_ for _, _, t_ in caused}
    rr = [
        (s_, q_, t_)
        for s_, q_, t_ in (
            typed_edge("replays", "Replay", "Receipt")
            or typed_edge("replays_receipt", "Replay", "Receipt")
        )
        if t_ in dag_receipts
    ]
    add(
        "replay->receipt",
        REQUIRED_CHAIN[6][1],
        rr,
        f"{len(rr)} Replay edge(s) binding a receipt in the ancestry DAG",
        "no Replay binds a receipt that participates in the receipt DAG",
    )

    return IndependentStanding(str(trial_dir), tuple(results), tuple(seen), ())


def assert_no_runtime_imports() -> None:
    """Fail loudly if the producing runtime got imported.

    Checked rather than intended: a verifier that imports the producer is not
    independent no matter how carefully its logic avoids using it.
    """
    leaked = [m for m in FORBIDDEN_RUNTIME_MODULES if m in sys.modules]
    if leaked:
        raise RuntimeError(
            f"VERIFIER_NOT_INDEPENDENT: the execution runtime is imported in this "
            f"process ({leaked}); standing computed here would not be external to "
            f"the actor"
        )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: standalone_verifier.py <trial_dir>", file=sys.stderr)
        return 2
    standing = verify(Path(argv[1]))
    for line in standing.report():
        print(" ", line)
    print()
    print("VERDICT:", standing.verdict())
    assert_no_runtime_imports()
    print("INDEPENDENCE: no execution-runtime module imported in this process")
    return 0 if standing.verdict() == "ALIVE_EVIDENCE_RECONSTRUCTED" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
