# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Recompute Level 4 standing from durable artifacts alone.

This is the crown threshold, stated as an executable check rather than an
aspiration:

    Delete the Python runtime state. Load only what is on disk. Recompute the
    same standing.

If that succeeds, standing is **external to the actor** -- checkable by
someone who did not run the trial and does not trust the runtime that
produced it. If it fails, standing still depends on the implementation that
emitted it, which is self-attestation with extra steps.

This module deliberately reads NOTHING from `TrialReport`, `CrownRun`, or any
in-memory object. Its only inputs are files. What it cannot establish from a
file, it reports as a missing identity -- never as a pass, and never as a
failure-by-default (see `.claude/rules/absence-is-not-evidence.md`).

Identity, not adjacency; identity, not co-occurrence
----------------------------------------------------
An earlier version of this module established `receipt->parents` by asking
whether a parent receipt id appeared *anywhere* in the OCEL as a string.
Receipt ids are event ids in that export, so every parent id was present as a
token whether or not any ancestry edge existed: the check could not fail, and
per `.claude/rules/absence-is-not-evidence.md` a factor that cannot fail is a
factor that is not being checked. The same weakness applied, less obviously,
to `commitment->episode`, which accepted any shared digest-shaped substring.

Every join below now requires a **typed relationship or a typed attribute
equality between two named objects** -- `caused_by`, `authorized_by`,
`observes_actuation`, `powl:episodeId` == `POWLCommitment.episode_id`, the
`Replay.head_digest` == the ledger's own chain head. A join that used to pass
on token co-occurrence and now fails is a corrected measurement, not a
regression: the previous OK was reporting the presence of a string, not the
reconstructibility of the graph.

Artifacts required
------------------
`actuation/episode.ocel.json` (gymact's export), `actuation/commitment.ttl`,
`actuation/receipts.sqlite3`, and `actuation/level4.ocel.json` -- the rich
Level 4 log built by
:func:`autofde_lab.hub.domain.gym_procedure.level4_ocel.build_level4_ocel`,
which is the only artifact carrying the typed O2O edges these joins need.
Absence of any one of them is reported as `UNKNOWN:ARTIFACTS_ABSENT:<name>`,
naming the file -- never as a failing join, because a question that was not
asked did not get a "no".
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

#: The identity joins that must be reconstructible from artifacts alone for
#: standing to be recomputable externally. Each is a question a third party
#: must be able to answer without the runtime.
REQUIRED_JOINS: tuple[tuple[str, str], ...] = (
    ("commitment->episode", "was this actuation the realization of this exact commitment?"),
    ("authority->actuation", "was this exact actuation authorized by this exact authority envelope?"),
    ("postcondition->actuation", "did an independent observation of THIS actuation occur?"),
    ("receipt->parents", "can the receipt DAG be reconstructed?"),
    ("replay->receipt", "did the replay bind the exact source receipt?"),
)

#: Every file that must be on disk before any join is even attempted.
REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "episode.ocel.json",
    "commitment.ttl",
    "receipts.sqlite3",
    "level4.ocel.json",
)


@dataclass(frozen=True)
class ArtifactSet:
    """Only files. No runtime objects, by construction."""

    trial_dir: Path
    episode_ocel: Optional[dict] = None
    level4_ocel: Optional[dict] = None
    commitment_turtle: Optional[str] = None
    ledger_path: Optional[Path] = None

    @classmethod
    def load(cls, trial_dir: Path) -> "ArtifactSet":
        act = Path(trial_dir) / "actuation"

        def maybe_json(name: str) -> Optional[dict]:
            p = act / name
            return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

        ttl_path = act / "commitment.ttl"
        ledger = act / "receipts.sqlite3"
        return cls(
            trial_dir=Path(trial_dir),
            episode_ocel=maybe_json("episode.ocel.json"),
            level4_ocel=maybe_json("level4.ocel.json"),
            commitment_turtle=ttl_path.read_text(encoding="utf-8") if ttl_path.is_file() else None,
            ledger_path=ledger if ledger.is_file() else None,
        )

    def absent(self) -> tuple[str, ...]:
        present = {
            "episode.ocel.json": self.episode_ocel is not None,
            "commitment.ttl": self.commitment_turtle is not None,
            "receipts.sqlite3": self.ledger_path is not None,
            "level4.ocel.json": self.level4_ocel is not None,
        }
        return tuple(name for name in REQUIRED_ARTIFACTS if not present[name])


@dataclass(frozen=True)
class JoinResult:
    """One identity join, and the exact evidence establishing it (or not)."""

    join: str
    question: str
    established: bool
    detail: str
    witness: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecomputedStanding:
    """The verdict a third party can reach from artifacts alone."""

    trial_dir: str
    joins: tuple[JoinResult, ...]
    missing_artifacts: tuple[str, ...] = ()

    def unestablished(self) -> list[str]:
        return [j.join for j in self.joins if not j.established]

    def verdict(self) -> str:
        """`EXTERNALLY_RECOMPUTABLE` only when every required join is
        established from files. Otherwise `UNKNOWN:<reason>` -- an
        unestablished join is not a failed trial, it is an unanswerable
        question, and those are different things."""
        if self.missing_artifacts:
            return f"UNKNOWN:ARTIFACTS_ABSENT:{','.join(self.missing_artifacts)}"
        missing = self.unestablished()
        if missing:
            return f"UNKNOWN:JOIN_NOT_ESTABLISHED:{','.join(missing)}"
        return "EXTERNALLY_RECOMPUTABLE"

    def report(self) -> list[str]:
        return [
            f"{'OK ' if j.established else '-- '}{j.join}: {j.detail}" for j in self.joins
        ]


# ── artifact readers (files only) ─────────────────────────────────────────


def _receipt_rows(ledger: Path) -> list[dict]:
    """Every receipt plus the ledger's own hash-chain columns, in order."""
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sequence, receipt_id, previous_digest, receipt_digest, receipt_json "
            "FROM receipt_evidence ORDER BY sequence"
        ).fetchall()
    finally:
        con.close()
    out: list[dict] = []
    for sequence, receipt_id, previous_digest, receipt_digest, receipt_json in rows:
        rec = json.loads(receipt_json)
        rec["_sequence"] = sequence
        rec["_previous_digest"] = previous_digest
        rec["_receipt_digest"] = receipt_digest
        rec.setdefault("receipt_id", receipt_id)
        out.append(rec)
    return out


@dataclass(frozen=True)
class _ObjectIndex:
    """An OCEL 2.0 object graph, indexed for identity lookups."""

    by_id: dict[str, dict]

    @classmethod
    def of(cls, document: dict) -> "_ObjectIndex":
        return cls({o["id"]: o for o in document.get("objects", []) if isinstance(o, dict)})

    def typed(self, object_type: str) -> list[dict]:
        return [o for o in self.by_id.values() if o.get("type") == object_type]

    def attr(self, object_id: str, name: str) -> Any:
        obj = self.by_id.get(object_id)
        if obj is None:
            return None
        for a in obj.get("attributes", []) or []:
            if a.get("name") == name:
                return a.get("value")
        return None

    def edges(self, object_id: str, qualifier: str) -> list[str]:
        """Targets of a **typed** O2O relationship from ``object_id``.

        This is the whole point of the module: a target reachable only because
        its id happens to appear as a string somewhere is not returned here.
        """
        obj = self.by_id.get(object_id)
        if obj is None:
            return []
        return [
            r["objectId"]
            for r in obj.get("relationships", []) or []
            if isinstance(r, dict) and r.get("qualifier") == qualifier and r.get("objectId")
        ]


def _commitment_terms(turtle: str) -> dict[str, str]:
    """Parse ``commitment.ttl`` with the real rdflib Turtle parser.

    A regex over Turtle would re-introduce exactly the substring-matching
    weakness this module exists to remove.
    """
    from rdflib import Graph, URIRef  # local import: rdflib is an optional-weight dep

    g = Graph()
    g.parse(data=turtle, format="turtle")
    out: dict[str, str] = {}
    for _s, p, o in g:
        if isinstance(p, URIRef) and str(p).startswith("urn:powl:"):
            out[str(p).removeprefix("urn:powl:")] = str(o)
    return out


# ── the recomputation ─────────────────────────────────────────────────────


def recompute(trial_dir: Path) -> RecomputedStanding:
    """Attempt the third-party recomputation. Files only."""
    trial_dir = Path(trial_dir)
    arts = ArtifactSet.load(trial_dir)
    absent = arts.absent()
    if absent:
        return RecomputedStanding(str(trial_dir), (), absent)

    assert arts.level4_ocel is not None and arts.episode_ocel is not None
    assert arts.commitment_turtle is not None and arts.ledger_path is not None

    idx = _ObjectIndex.of(arts.level4_ocel)
    episode_idx = _ObjectIndex.of(arts.episode_ocel)
    receipts = _receipt_rows(arts.ledger_path)
    results: list[JoinResult] = []

    # 1. commitment -> episode, on the real join: the TTL's powl:episodeId and
    #    powl:planDigest against the POWLCommitment object's own attributes,
    #    and that episode id against a real `episode` object in gymact's
    #    export. Three named identities agreeing, not a shared substring.
    terms = _commitment_terms(arts.commitment_turtle)
    ttl_episode = terms.get("episodeId")
    ttl_plan_digest = terms.get("planDigest")
    commitments = idx.typed("POWLCommitment")
    matches = [
        c
        for c in commitments
        if ttl_episode is not None
        and ttl_plan_digest is not None
        and idx.attr(c["id"], "episode_id") == ttl_episode
        and idx.attr(c["id"], "plan_digest") == ttl_plan_digest
    ]
    episode_objects = {o["id"] for o in episode_idx.typed("episode")}
    episode_known = ttl_episode in episode_objects if ttl_episode else False
    established = bool(matches) and episode_known
    results.append(
        JoinResult(
            "commitment->episode",
            REQUIRED_JOINS[0][1],
            established,
            (
                f"commitment.ttl powl:episodeId={ttl_episode} == POWLCommitment.episode_id "
                f"and powl:planDigest={ttl_plan_digest} == POWLCommitment.plan_digest, "
                f"and that episode is an `episode` object in episode.ocel.json"
                if established
                else "no POWLCommitment object agrees with commitment.ttl on BOTH "
                f"episodeId and planDigest, or the episode is unknown to "
                f"episode.ocel.json (ttl episodeId={ttl_episode!r}, "
                f"planDigest={ttl_plan_digest!r}, POWLCommitment objects={len(commitments)}, "
                f"episode object known={episode_known})"
            ),
            tuple(sorted({c["id"] for c in matches})),
        )
    )

    # 2. authority -> actuation, via a typed `authorized_by` edge from the
    #    Actuation object of THIS act receipt to an AuthorityEnvelope object
    #    whose authority_ref equals the receipt's own.
    act_receipts = [r for r in receipts if r.get("operation") == "act"]
    authorized: list[str] = []
    for r in act_receipts:
        actuation_id = f"urn:level4:actuation:{r.get('receipt_id')}"
        for target in idx.edges(actuation_id, "authorized_by"):
            target_obj = idx.by_id.get(target)
            if (
                target_obj is not None
                and target_obj.get("type") == "AuthorityEnvelope"
                and idx.attr(target, "authority_ref") == r.get("authority_ref")
                and r.get("authority_ref")
            ):
                authorized.append(actuation_id)
                break
    results.append(
        JoinResult(
            "authority->actuation",
            REQUIRED_JOINS[1][1],
            bool(act_receipts) and len(authorized) == len(act_receipts),
            f"{len(authorized)}/{len(act_receipts)} act receipts have an Actuation object "
            f"with a typed `authorized_by` edge to an AuthorityEnvelope carrying the same "
            f"authority_ref",
            tuple(sorted(authorized)),
        )
    )

    # 3. postcondition -> actuation, via a typed `observes_actuation` edge to
    #    the Actuation object of a receipt this verify receipt actually names
    #    as a parent. Observing *some* actuation is not observing THIS one.
    verify_receipts = [r for r in receipts if r.get("operation") == "verify"]
    observed: list[str] = []
    for r in verify_receipts:
        vid = r.get("verification_id")
        parents = {
            f"urn:level4:actuation:{p}"
            for p in (r.get("parent_receipt_ids") or [])
        }
        post_id = f"urn:level4:postcondition:{vid}"
        if parents and set(idx.edges(post_id, "observes_actuation")) & parents:
            observed.append(post_id)
    results.append(
        JoinResult(
            "postcondition->actuation",
            REQUIRED_JOINS[2][1],
            bool(verify_receipts) and len(observed) == len(verify_receipts),
            f"{len(observed)}/{len(verify_receipts)} verify receipts have a "
            f"PostconditionObservation with a typed `observes_actuation` edge to the "
            f"Actuation of a receipt they name as parent",
            tuple(sorted(observed)),
        )
    )

    # 4. receipt DAG, via typed `caused_by` O2O edges -- one per ledger parent
    #    edge. Token presence is explicitly NOT accepted (see module docstring).
    ledger_edges = {
        (r["receipt_id"], p)
        for r in receipts
        for p in (r.get("parent_receipt_ids") or [])
        if p in {x.get("receipt_id") for x in receipts}
    }
    reconstructed = {
        (child, parent) for child, parent in ledger_edges if parent in idx.edges(child, "caused_by")
    }
    results.append(
        JoinResult(
            "receipt->parents",
            REQUIRED_JOINS[3][1],
            bool(ledger_edges) and reconstructed == ledger_edges,
            (
                f"{len(reconstructed)}/{len(ledger_edges)} ledger parent edges are present "
                f"as typed `caused_by` O2O relationships in level4.ocel.json"
                if ledger_edges
                else "ledger records no in-ledger parent_receipt_ids at all, so there is no "
                "DAG to reconstruct"
            ),
            tuple(sorted(f"{c}->{p}" for c, p in sorted(reconstructed))),
        )
    )

    # 5. replay -> receipt: a Replay object whose head_digest is the ledger's
    #    own chain head. That binds the replay to the exact final receipt,
    #    where the existence of a `replay*.json` file bound it to nothing.
    chain_head = receipts[-1]["_receipt_digest"] if receipts else None
    replays = idx.typed("Replay")
    bound = [
        rp["id"] for rp in replays if chain_head and idx.attr(rp["id"], "head_digest") == chain_head
    ]
    results.append(
        JoinResult(
            "replay->receipt",
            REQUIRED_JOINS[4][1],
            bool(bound),
            (
                f"Replay head_digest == ledger chain head {chain_head}"
                if bound
                else f"no Replay object binds the ledger chain head "
                f"(chain_head={chain_head!r}, Replay objects={len(replays)})"
            ),
            tuple(sorted(bound)),
        )
    )

    return RecomputedStanding(str(trial_dir), tuple(results))
