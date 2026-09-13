# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Level 4 chain vocabulary as a real :class:`autofde_lab.ocel.log.OcelLog`.

Why this module exists
----------------------
Before it, a Level 4 trial left two artifacts on disk that shared no identity:

* ``actuation/commitment.ttl`` -- subject ``urn:trial:<run_id>``, carrying
  ``powl:planDigest`` and ``powl:modelDigest``;
* ``actuation/episode.ocel.json`` -- gymact's ``receipts_to_ocel`` export,
  keyed on ``episode_id``.

Grepping the plan digest in the OCEL and the episode id in the Turtle both
returned zero. The only join was filesystem adjacency, so *"did the execution
conform to the committed solution?"* was not answerable from the evidence --
not answered "no", **not answerable**, which per
``.claude/rules/absence-is-not-evidence.md`` is ``UNKNOWN``.

Two things are done here, and only these two:

1. :func:`build_level4_ocel` reads the artifacts a trial *already wrote* and
   builds one OCEL 2.0 log over the Level 4 chain vocabulary -- 13 object
   types, 14 event types, real O2O edges. It is strictly a reader: it opens
   no environment, runs no planner, actuates nothing.
2. :func:`link_commitment_ttl` writes the observed ``episodeId`` and
   ``environmentId`` back into ``commitment.ttl``, and the POWLCommitment
   object in the log carries ``planDigest``/``modelDigest`` as attributes.
   After both, the join is greppable in **both** directions.

What is deliberately *not* done
-------------------------------
Nothing is fabricated. Every object and every event in the emitted log is
backed by a byte that exists on disk. Where a source is absent -- a trial that
never reached actuation has no ledger, a standalone trial directory has no
crown manifest -- the corresponding object/event type is **omitted** and named
in :class:`Level4OcelReport.absent_object_types` /
``absent_event_types`` with the reason. An omitted type means "no evidence
here", never "observed to be empty".

Timestamps
----------
Only receipts carry an observed wall clock (``occurred_at``). The pre-actuation
stages (probe, induce, plan, commit) leave no timestamp on disk at all. Rather
than invent one, every pre-actuation event is given a **derived ordinal**
placed 1ns apart immediately *before* the first receipt, and the log records
``time_basis="DERIVED_ORDINAL"`` as an event attribute on exactly those
events. Receipt-derived events carry ``time_basis="OBSERVED"``. A reader can
therefore tell an observed instant from a reconstructed ordering without
consulting this docstring.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelObject,
    OcelValueKind,
    parse_ns,
)

__all__ = [
    "LEVEL4_EVENT_TYPES",
    "LEVEL4_OBJECT_TYPES",
    "WITNESS_JOURNAL_NAME",
    "Level4Ocel",
    "Level4OcelReport",
    "WitnessJournal",
    "build_level4_ocel",
    "link_commitment_ttl",
    "read_commitment",
    "task_identity",
]

#: The Level 4 chain vocabulary, in chain order. Declared as a closed set so a
#: populated/absent report is a partition of it rather than a list of whatever
#: happened to be built.
LEVEL4_EVENT_TYPES: tuple[str, ...] = (
    "TaskAdmitted",
    "GoalAdmitted",
    "CandidateSelected",
    "GoalConsequenceObserved",
    "SessionStarted",
    "CapabilitiesObserved",
    "ProbeExecuted",
    "ModelInferred",
    "PlanConstructed",
    "POWLCommitted",
    "AuthorityAdmitted",
    "ActuationOpened",
    "ActuationClosed",
    "PostconditionObserved",
    "PostconditionVerified",
    "ReceiptEmitted",
    "ReplayCompleted",
)

LEVEL4_OBJECT_TYPES: tuple[str, ...] = (
    "Task",
    "Goal",
    "Environment",
    "Capability",
    "Probe",
    "DiscoveredDomain",
    "PlannerAttempt",
    "PlanCandidate",
    "POWLCommitment",
    "AuthorityEnvelope",
    "Actuation",
    "PostconditionObservation",
    "IndependentVerifier",
    "Receipt",
    "Replay",
)


# ── the witness journal: relations recorded WHEN THEY BECOME TRUE ────────
#
# Every edge below used to be either absent or reconstructed afterwards from
# whatever happened to be adjacent on disk. Both are refused by
# `.claude/rules/no-dual-bookkeeping.md`: a relation inferred after the fact
# is a claim about a claim.
#
# `WitnessJournal` is the producer's place to *state* a relation at the exact
# transition where it becomes true -- goal admission, candidate selection,
# commitment, independent goal verification, replay. It is append-only, it
# names both endpoints by exact identity, and `build_level4_ocel` emits the
# corresponding typed O2O edge ONLY from a record here. No record, no edge,
# and the relation stays UNKNOWN -- never guessed from ordering, digests that
# happen to coincide, filenames, or counts.
#
# The one lookup performed anywhere in this module is
# :meth:`WitnessJournal.complete_replay`'s head-digest -> receipt_id
# resolution, and it is done BY THE PRODUCER, at the moment of replay, against
# the ledger the replay just verified. A receipt digest is that receipt's
# cryptographic identity, not a coincidence; and if no receipt in the ledger
# carries the digest the replay reports, nothing is recorded at all.

WITNESS_JOURNAL_NAME = "witness.jsonl"


def task_identity(evidence_dir: Path) -> str:
    """The Task identity for a trial directory.

    Exported so the producer and the OCEL build cannot disagree about it: an
    edge naming a Task the log does not contain is a dangling reference, and
    two independent spellings of the same rule is exactly the dual bookkeeping
    that produced the joins this module exists to end.
    """
    evidence_dir = Path(evidence_dir)
    seed = _seed_from_dir(evidence_dir)
    parts = evidence_dir.name.split("_", 2)
    run_id = parts[2] if len(parts) == 3 else evidence_dir.name
    return f"urn:level4:task:{seed if seed is not None else run_id}"


class WitnessJournal:
    """Append-only record of relations, written at the causal moment.

    Not a summary and not a projection: nothing here is derived from anything
    else in the evidence directory. Each method takes the identities of both
    endpoints from the caller, which is only possible at the transition where
    the producer actually holds them.
    """

    def __init__(self, evidence_dir: Path) -> None:
        self.evidence_dir = Path(evidence_dir)
        self.path = self.evidence_dir / WITNESS_JOURNAL_NAME
        self.task_id = task_identity(self.evidence_dir)

    def _append(self, kind: str, **fields: Any) -> dict[str, Any]:
        record = {"kind": kind, "task_id": self.task_id, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    # -- admission ---------------------------------------------------------

    def admit_goal(self, *, goal_id: str, expression: str, target: Mapping[str, Any]) -> str:
        """At goal admission. The admitted Goal becomes a durable object with
        its own identity, so runtime ``final_state`` can never be what
        establishes standing."""
        self._append(
            "goal_admitted",
            goal_id=goal_id,
            expression=expression,
            target={str(k): str(v) for k, v in dict(target).items()},
        )
        return goal_id

    # -- selection ---------------------------------------------------------

    def select_candidate(
        self,
        *,
        candidate_id: str,
        goal_id: str,
        planner: str,
        source: str,
        plan: tuple[str, ...],
    ) -> str:
        """At the moment one candidate is selected FOR that goal.

        Recorded here rather than reconstructed from ``typed_validation.json``
        because "the first candidate the file lists as valid" re-derives the
        selection rule instead of reading the selection.
        """
        self._append(
            "candidate_selected",
            candidate_id=candidate_id,
            goal_id=goal_id,
            planner=planner,
            source=source,
            plan=list(plan),
        )
        return candidate_id

    def commit_plan(self, *, commitment_subject: str, candidate_id: str) -> None:
        """At ``commit()``. THIS commitment realizes THAT candidate -- the one
        relation ``commitment.ttl`` cannot carry, since it records the plan's
        digest and not which candidate produced it."""
        self._append(
            "plan_committed",
            commitment_subject=commitment_subject,
            candidate_id=candidate_id,
        )

    # -- independent consequence -------------------------------------------

    def observe_goal_consequence(
        self,
        *,
        verification_id: str,
        goal_id: str,
        outcome: str,
        actuation_receipt_id: str,
        verifier_id: str,
        actuator_id: str,
    ) -> None:
        """At the independent ``gym.verify(episode, final_expected)`` return.

        ``outcome`` is ``ESTABLISHED`` or ``REFUTED`` -- both real, checked
        observations. A verification that did not run records nothing, which
        is UNKNOWN and must never be written as ``REFUTED``.

        ``verifier_id`` and ``actuator_id`` are both recorded so
        ``SELF_CERTIFIED_POSTCONDITION`` is a property of the graph (the two
        identities coincide) rather than a flag anyone can set.
        """
        if outcome not in ("ESTABLISHED", "REFUTED"):
            raise ValueError(
                f"GOAL_CONSEQUENCE_OUTCOME_MUST_BE_OBSERVED: {outcome!r} is neither "
                f"ESTABLISHED nor REFUTED; an unobserved goal records nothing"
            )
        self._append(
            "goal_consequence_observed",
            verification_id=verification_id,
            goal_id=goal_id,
            outcome=outcome,
            actuation_receipt_id=actuation_receipt_id,
            verifier_id=verifier_id,
            actuator_id=actuator_id,
        )

    # -- replay ------------------------------------------------------------

    def complete_replay(
        self,
        *,
        ledger: Path,
        head_digest: str,
        record_count: int,
        valid: bool,
        mode: str,
    ) -> str | None:
        """At the moment ``replay_ledger`` returns, naming the exact receipt.

        The replay reports the head digest it verified; that digest is the
        cryptographic identity of one receipt row, resolved here against the
        very ledger that was replayed. If no row carries it, nothing is
        recorded -- an unbindable replay is UNKNOWN, not a replay of "some
        receipt".
        """
        ledger = Path(ledger)
        if not head_digest or not ledger.is_file():
            return None
        conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
        try:
            # `record_digest` is the ledger's own per-record chain digest --
            # the thing `replay_ledger` walks and reports as its head. It is
            # NOT `receipt_digest`; matching against that column silently
            # found nothing, which correctly recorded no replay at all rather
            # than binding an approximate receipt.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(receipt_evidence)")}
            if "record_digest" not in columns:
                return None
            row = conn.execute(
                "SELECT receipt_id FROM receipt_evidence WHERE record_digest = ?",
                (head_digest,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        self._append(
            "replay_completed",
            receipt_id=row[0],
            head_digest=head_digest,
            record_count=int(record_count),
            valid=bool(valid),
            mode=mode,
        )
        return str(row[0])

    @staticmethod
    def final_actuation_receipt_id(ledger: Path, *, operations: tuple[str, ...] = ("act",)) -> str | None:
        """The receipt of the last actuating step, for the producer's own use.

        Called by the producer immediately after execution, where "the last
        actuating step" is a fact of its own control flow -- the step whose
        post-state the independent goal verification then observed. It is a
        lookup in the producer's own ledger, not a reconstruction by a reader:
        nothing in :func:`build_level4_ocel` calls it, and a consumer that
        tried to would be inferring a relation from ordering.
        """
        ledger = Path(ledger)
        if not ledger.is_file():
            return None
        conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT receipt_id, receipt_json FROM receipt_evidence ORDER BY sequence"
            ).fetchall()
        finally:
            conn.close()
        found = None
        for receipt_id, receipt_json in rows:
            if str(json.loads(receipt_json).get("operation")) in operations:
                found = str(receipt_id)
        return found

    # -- reading -----------------------------------------------------------

    @staticmethod
    def read(evidence_dir: Path) -> tuple[dict[str, Any], ...]:
        path = Path(evidence_dir) / WITNESS_JOURNAL_NAME
        if not path.is_file():
            return ()
        return tuple(
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )


# ── small typed-attribute helpers ────────────────────────────────────────


def _s(value: str) -> OcelAttributeValue:
    return OcelAttributeValue(OcelValueKind.STRING, value)


def _i(value: int) -> OcelAttributeValue:
    return OcelAttributeValue(OcelValueKind.INTEGER, int(value))


def _f(value: float) -> OcelAttributeValue:
    return OcelAttributeValue(OcelValueKind.FLOAT, float(value))


def _b(value: bool) -> OcelAttributeValue:
    return OcelAttributeValue(OcelValueKind.BOOLEAN, bool(value))


def _attrs(pairs: Mapping[str, OcelAttributeValue | None]) -> tuple[OcelAttribute, ...]:
    """Build attributes, dropping every ``None``.

    ``None`` here means *no source byte*, and an absent attribute is the honest
    encoding of that. It is never rendered as a null-valued attribute, which a
    downstream reader could not distinguish from an observed null.
    """
    return tuple(OcelAttribute(k, v) for k, v in pairs.items() if v is not None)


# ── commitment.ttl (parsed with rdflib, never with a regex) ──────────────


@dataclass(frozen=True)
class Commitment:
    """The committed solution, as read back out of ``commitment.ttl``."""

    subject: str
    plan_digest: str
    model_digest: str
    plan_length: int | None
    sequence: tuple[str, ...]
    episode_id: str | None = None
    environment_id: str | None = None


_POWL = "urn:powl:"


def read_commitment(path: Path) -> Commitment:
    """Parse ``commitment.ttl`` with the real rdflib Turtle parser.

    A regex over Turtle would silently accept documents rdflib rejects and
    reject ones it accepts; ``shacl_conformance.py`` exists in this repo
    precisely because a hand-written re-expression of a committed artifact
    drifted from the artifact undetected. Same mistake, same refusal to
    repeat it.
    """
    import rdflib

    graph = rdflib.Graph()
    graph.parse(str(path), format="turtle")

    subject = None
    for s, _p, _o in graph.triples((None, rdflib.RDF.type, rdflib.URIRef(_POWL + "Commitment"))):
        subject = str(s)
        break
    if subject is None:
        raise ValueError(f"NO_POWL_COMMITMENT_SUBJECT: {path} declares no powl:Commitment")

    def one(name: str) -> str | None:
        for value in graph.objects(rdflib.URIRef(subject), rdflib.URIRef(_POWL + name)):
            return str(value)
        return None

    sequence: list[str] = []
    for head in graph.objects(rdflib.URIRef(subject), rdflib.URIRef(_POWL + "sequence")):
        node = head
        while node and node != rdflib.RDF.nil:
            for item in graph.objects(node, rdflib.RDF.first):
                sequence.append(str(item))
            rest = list(graph.objects(node, rdflib.RDF.rest))
            node = rest[0] if rest else None

    length = one("planLength")
    plan_digest = one("planDigest")
    model_digest = one("modelDigest")
    if plan_digest is None or model_digest is None:
        raise ValueError(
            f"INCOMPLETE_COMMITMENT: {path} lacks "
            f"{'planDigest' if plan_digest is None else 'modelDigest'}"
        )
    return Commitment(
        subject=subject,
        plan_digest=plan_digest,
        model_digest=model_digest,
        plan_length=int(length) if length is not None else None,
        sequence=tuple(sequence),
        episode_id=one("episodeId"),
        environment_id=one("environmentId"),
    )


def link_commitment_ttl(path: Path, *, episode_id: str, environment_id: str) -> Commitment:
    """Write the observed episode and environment identity into the commitment.

    This is the half of the join that lives in the Turtle. The other half --
    ``planDigest``/``modelDigest`` on the ``POWLCommitment`` OCEL object -- is
    built by :func:`build_level4_ocel`. Both halves are needed: one direction
    alone still leaves a grep in the other direction at zero.

    Idempotent: re-linking a commitment that already carries the same identity
    rewrites identical bytes. Re-linking one that carries a *different*
    identity is refused -- silently rebinding a committed plan to a second
    episode is exactly the confusion this module was written to end.
    """
    existing = read_commitment(path)
    for name, was, now in (
        ("episodeId", existing.episode_id, episode_id),
        ("environmentId", existing.environment_id, environment_id),
    ):
        if was is not None and was != now:
            raise ValueError(
                f"COMMITMENT_ALREADY_BOUND: {path} binds powl:{name} {was!r}; "
                f"refusing to rebind to {now!r}"
            )

    text = path.read_text(encoding="utf-8")
    if existing.episode_id is None or existing.environment_id is None:
        # Append before the terminating '.' of the subject block, so the
        # document stays one well-formed Turtle statement. Verified by
        # re-parsing below -- never assumed.
        stripped = text.rstrip()
        if not stripped.endswith("."):
            raise ValueError(f"UNEXPECTED_COMMITMENT_SHAPE: {path} does not end a statement")
        body = stripped[:-1].rstrip()
        additions = []
        if existing.episode_id is None:
            additions.append(f'    powl:episodeId "{episode_id}" ;')
        if existing.environment_id is None:
            additions.append(f'    powl:environmentId "{environment_id}" ;')
        text = body + " ;\n" + "\n".join(additions).rstrip(" ;") + " .\n"
        path.write_text(text, encoding="utf-8")

    linked = read_commitment(path)
    if linked.episode_id != episode_id or linked.environment_id != environment_id:
        raise ValueError(
            f"COMMITMENT_LINK_NOT_READABLE: wrote episodeId/environmentId to {path} but "
            f"re-parsing yields {linked.episode_id!r}/{linked.environment_id!r}"
        )
    return linked


# ── report ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Level4OcelReport:
    """Which vocabulary terms were backed by real data, and why not otherwise."""

    populated_object_types: tuple[str, ...] = ()
    populated_event_types: tuple[str, ...] = ()
    absent_object_types: tuple[tuple[str, str], ...] = ()
    absent_event_types: tuple[tuple[str, str], ...] = ()
    sources_read: tuple[str, ...] = ()
    sources_absent: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "populated_object_types": list(self.populated_object_types),
            "populated_event_types": list(self.populated_event_types),
            "absent_object_types": {k: v for k, v in self.absent_object_types},
            "absent_event_types": {k: v for k, v in self.absent_event_types},
            "sources_read": list(self.sources_read),
            "sources_absent": {k: v for k, v in self.sources_absent},
        }


@dataclass(frozen=True)
class Level4Ocel:
    """The built log plus the provenance report and the identities it joins."""

    log: OcelLog
    report: Level4OcelReport
    commitment: Commitment | None
    episode_id: str | None
    environment_id: str | None
    task_id: str


# ── ledger reading ────────────────────────────────────────────────────────


def _read_receipts(ledger: Path) -> list[dict[str, Any]]:
    """Read every receipt in ledger order, with its chain digests.

    ``receipt_json`` alone drops ``previous_digest``/``receipt_digest``, which
    are the ledger's own hash chain -- the thing a Replay actually verifies.
    """
    conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT sequence, receipt_id, previous_digest, receipt_digest, receipt_json "
            "FROM receipt_evidence ORDER BY sequence"
        ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for sequence, receipt_id, previous_digest, receipt_digest, receipt_json in rows:
        record = json.loads(receipt_json)
        record["_sequence"] = sequence
        record["_previous_digest"] = previous_digest
        record["_receipt_digest"] = receipt_digest
        record.setdefault("receipt_id", receipt_id)
        out.append(record)
    return out


def _maybe_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_from_dir(evidence_dir: Path) -> int | None:
    """``realtrial_<seed>_<uuid>`` -> seed. Returns None if the name differs."""
    parts = evidence_dir.name.split("_")
    if len(parts) >= 3 and parts[0] == "realtrial" and parts[1].isdigit():
        return int(parts[1])
    return None


def _crown_manifest_digest(evidence_dir: Path) -> str | None:
    """The frozen-crown manifest digest, if this trial sits inside a crown run."""
    for candidate in (
        evidence_dir.parent / "crown_run.json",
        evidence_dir.parent / "crown_manifest.json",
    ):
        data = _maybe_json(candidate)
        if isinstance(data, dict) and isinstance(data.get("manifest_digest"), str):
            return data["manifest_digest"]
    return None


# ── the build ─────────────────────────────────────────────────────────────


def build_level4_ocel(evidence_dir: Path) -> Level4Ocel:
    """Build one Level 4 OCEL log from the artifacts a trial left on disk.

    ``evidence_dir`` is a ``realtrial_<seed>_<run_id>`` directory as written by
    :func:`autofde_lab.hub.domain.gym_procedure.level4_crown.run_real_trial`.
    Nothing outside it (and its parent's crown manifest, if any) is read, and
    nothing at all is executed.
    """
    evidence_dir = Path(evidence_dir)
    if not evidence_dir.is_dir():
        raise FileNotFoundError(f"NO_EVIDENCE_DIR: {evidence_dir}")

    sources_read: list[str] = []
    sources_absent: list[tuple[str, str]] = []
    populated_objects: list[str] = []
    populated_events: list[str] = []
    absent_objects: list[tuple[str, str]] = []
    absent_events: list[tuple[str, str]] = []

    objects: list[OcelObject] = []
    o2o: list[ObjectObjectLink] = []

    def source(name: str, path: Path) -> Any | None:
        data = _maybe_json(path)
        if data is None:
            sources_absent.append((name, f"NOT_ON_DISK:{path}"))
        else:
            sources_read.append(name)
        return data

    probe_doc = source("typed_probe_log.json", evidence_dir / "typed_probe_log.json")
    federation = source("federation.json", evidence_dir / "federation.json")
    ttl_path = evidence_dir / "actuation" / "commitment.ttl"
    ledger_path = evidence_dir / "actuation" / "receipts.sqlite3"

    commitment: Commitment | None = None
    if ttl_path.exists():
        commitment = read_commitment(ttl_path)
        sources_read.append("actuation/commitment.ttl")
    else:
        sources_absent.append(("actuation/commitment.ttl", f"NOT_ON_DISK:{ttl_path}"))

    receipts: list[dict[str, Any]] = []
    if ledger_path.exists():
        receipts = _read_receipts(ledger_path)
        sources_read.append("actuation/receipts.sqlite3")
    else:
        sources_absent.append(("actuation/receipts.sqlite3", f"NOT_ON_DISK:{ledger_path}"))

    # --- identities ------------------------------------------------------
    seed = _seed_from_dir(evidence_dir)
    manifest_digest = _crown_manifest_digest(evidence_dir)
    run_id = evidence_dir.name.split("_", 2)[2] if len(evidence_dir.name.split("_", 2)) == 3 else evidence_dir.name
    task_id = f"urn:level4:task:{seed if seed is not None else run_id}"

    episode_ids = sorted({r["episode_id"] for r in receipts if r.get("episode_id")})
    environment_ids = sorted({r["subject_ref"] for r in receipts if r.get("subject_ref")})
    episode_id = episode_ids[0] if len(episode_ids) == 1 else None
    environment_id = environment_ids[0] if len(environment_ids) == 1 else None

    # --- Task (always: the directory itself is the evidence) -------------
    objects.append(
        OcelObject(
            task_id,
            "Task",
            _attrs(
                {
                    "seed": _i(seed) if seed is not None else None,
                    "run_id": _s(run_id),
                    "manifest_digest": _s(manifest_digest) if manifest_digest else None,
                    "evidence_dir": _s(str(evidence_dir)),
                }
            ),
        )
    )
    populated_objects.append("Task")

    # --- Goal: a first-class durable object, or nothing ------------------
    #
    # Emitted ONLY from a `goal_admitted` witness record. There is deliberately
    # no fallback that reads the goal out of the runtime, the commitment, or a
    # final state: a goal recovered from the outcome cannot fail to be met.
    journal = WitnessJournal.read(evidence_dir)
    if journal:
        sources_read.append(WITNESS_JOURNAL_NAME)
    else:
        sources_absent.append((WITNESS_JOURNAL_NAME, f"NOT_ON_DISK:{evidence_dir / WITNESS_JOURNAL_NAME}"))

    def _records(kind: str) -> list[dict[str, Any]]:
        return [r for r in journal if r.get("kind") == kind]

    goal_ids: list[str] = []
    for record in _records("goal_admitted"):
        goal_id = str(record["goal_id"])
        objects.append(
            OcelObject(
                goal_id,
                "Goal",
                _attrs(
                    {
                        "expression": _s(str(record.get("expression", ""))),
                        # One canonical string rather than a list: a `list`
                        # attribute has to be declared `string` anyway (it is
                        # not in OCEL 2.0's five-valued type vocabulary), and
                        # declaring a type the value does not have is the
                        # secondary-representation drift this module refuses.
                        "target": _s(
                            ",".join(
                                f"{k}={v}" for k, v in sorted((record.get("target") or {}).items())
                            )
                        )
                        if record.get("target")
                        else None,
                    }
                ),
            )
        )
        o2o.append(ObjectObjectLink(goal_id, task_id, "goal_of_task"))
        goal_ids.append(goal_id)
    if goal_ids:
        populated_objects.append("Goal")
    else:
        absent_objects.append(("Goal", "NO_goal_admitted_RECORD_IN_WITNESS_JOURNAL"))

    if manifest_digest is None:
        sources_absent.append(("crown manifest_digest", "NO_CROWN_RUN_JSON_IN_PARENT"))

    # --- Environment / Capability (from receipts only) -------------------
    if environment_ids:
        for env_id in environment_ids:
            objects.append(OcelObject(env_id, "Environment", _attrs({"subject_ref": _s(env_id)})))
        populated_objects.append("Environment")
    else:
        absent_objects.append(("Environment", "NO_RECEIPTS_WITH_SUBJECT_REF"))

    capability_ids = sorted({r["capability_ref"] for r in receipts if r.get("capability_ref")})
    if capability_ids:
        for cap in capability_ids:
            objects.append(
                OcelObject(cap, "Capability", _attrs({"capability_ref": _s(cap)}))
            )
        populated_objects.append("Capability")
    else:
        absent_objects.append(("Capability", "NO_RECEIPTS_WITH_CAPABILITY_REF"))

    # --- Probe -----------------------------------------------------------
    probe_records: list[dict[str, Any]] = []
    if isinstance(probe_doc, dict) and isinstance(probe_doc.get("probe_log"), list):
        probe_records = probe_doc["probe_log"]
    if probe_records:
        for index, probe in enumerate(probe_records):
            probe_id = f"{task_id}:probe:{index}"
            objects.append(
                OcelObject(
                    probe_id,
                    "Probe",
                    _attrs(
                        {
                            "index": _i(index),
                            "action": _s(str(probe.get("action", ""))),
                            "applicable": _b(bool(probe.get("applicable", False))),
                            "n_delta_added": _i(len(probe.get("delta_added", []))),
                            "n_delta_removed": _i(len(probe.get("delta_removed", []))),
                        }
                    ),
                )
            )
            o2o.append(ObjectObjectLink(probe_id, task_id, "probe_of_task"))
        populated_objects.append("Probe")
    else:
        absent_objects.append(("Probe", "NO_PROBE_LOG_ON_DISK"))

    # --- DiscoveredDomain (model_digest is only ever in the commitment) ---
    domain_id: str | None = None
    if commitment is not None:
        domain_id = f"urn:level4:domain:{commitment.model_digest}"
        objects.append(
            OcelObject(
                domain_id,
                "DiscoveredDomain",
                _attrs(
                    {
                        "model_digest": _s(commitment.model_digest),
                        "n_probes_induced_from": _i(len(probe_records)) if probe_records else None,
                    }
                ),
            )
        )
        o2o.append(ObjectObjectLink(domain_id, task_id, "domain_of_task"))
        populated_objects.append("DiscoveredDomain")
    else:
        absent_objects.append(("DiscoveredDomain", "NO_COMMITMENT_TTL_SO_NO_MODEL_DIGEST"))

    # --- PlannerAttempt / PlanCandidate ----------------------------------
    attempt_records = federation if isinstance(federation, list) else []
    if attempt_records:
        for index, attempt in enumerate(attempt_records):
            attempt_id = f"{task_id}:attempt:{index}"
            objects.append(
                OcelObject(
                    attempt_id,
                    "PlannerAttempt",
                    _attrs(
                        {
                            "planner": _s(str(attempt.get("planner", ""))),
                            "outcome": _s(str(attempt.get("outcome", ""))),
                            "duration_s": _f(attempt["duration_s"])
                            if isinstance(attempt.get("duration_s"), (int, float))
                            else None,
                            "detail": _s(str(attempt["detail"]))
                            if attempt.get("detail") is not None
                            else None,
                            "plan_length": _i(len(attempt.get("plan", []))),
                        }
                    ),
                )
            )
            o2o.append(ObjectObjectLink(attempt_id, task_id, "attempt_of_task"))
            if domain_id is not None:
                o2o.append(ObjectObjectLink(attempt_id, domain_id, "planned_over_model"))
        populated_objects.append("PlannerAttempt")
    else:
        absent_objects.append(("PlannerAttempt", "NO_FEDERATION_JSON_OR_NO_ATTEMPTS"))

    candidate_ids: list[str] = []
    for index, attempt in enumerate(attempt_records):
        plan = attempt.get("plan") or []
        if not plan:
            continue
        candidate_id = f"{task_id}:candidate:{index}"
        objects.append(
            OcelObject(
                candidate_id,
                "PlanCandidate",
                _attrs(
                    {
                        "planner": _s(str(attempt.get("planner", ""))),
                        "plan_length": _i(len(plan)),
                        "sequence": OcelAttributeValue(
                            OcelValueKind.LIST, tuple(_s(str(a)) for a in plan)
                        ),
                    }
                ),
            )
        )
        o2o.append(ObjectObjectLink(candidate_id, f"{task_id}:attempt:{index}", "proposed_by"))
        candidate_ids.append(candidate_id)
    # The SELECTED candidate, stated by the producer at selection time. It is
    # not necessarily one of the federation attempts above -- a plan found by
    # `search_plan_typed` is equally a candidate, and reconstructing "which
    # one was chosen" from the attempt list would re-derive the selection rule
    # rather than read the selection.
    selected_candidates: list[str] = []
    for record in _records("candidate_selected"):
        candidate_id = str(record["candidate_id"])
        if candidate_id not in candidate_ids:
            plan = [str(a) for a in (record.get("plan") or [])]
            objects.append(
                OcelObject(
                    candidate_id,
                    "PlanCandidate",
                    _attrs(
                        {
                            "planner": _s(str(record.get("planner", ""))),
                            "source": _s(str(record.get("source", ""))),
                            "plan_length": _i(len(plan)),
                            "sequence": OcelAttributeValue(
                                OcelValueKind.LIST, tuple(_s(a) for a in plan)
                            )
                            if plan
                            else None,
                        }
                    ),
                )
            )
            candidate_ids.append(candidate_id)
        goal_id = str(record.get("goal_id") or "")
        if goal_id in goal_ids:
            o2o.append(ObjectObjectLink(candidate_id, goal_id, "targets_goal"))
        selected_candidates.append(candidate_id)

    if candidate_ids:
        populated_objects.append("PlanCandidate")
    else:
        absent_objects.append(("PlanCandidate", "NO_PLANNER_ATTEMPT_RETURNED_A_NON_EMPTY_PLAN"))

    # --- POWLCommitment: the object that carries the join ----------------
    commitment_id: str | None = None
    if commitment is not None:
        commitment_id = commitment.subject
        objects.append(
            OcelObject(
                commitment_id,
                "POWLCommitment",
                _attrs(
                    {
                        # These two are the greppable half of the join that
                        # lives in the OCEL. Before this module they existed
                        # only in the Turtle.
                        "plan_digest": _s(commitment.plan_digest),
                        "model_digest": _s(commitment.model_digest),
                        "plan_length": _i(commitment.plan_length)
                        if commitment.plan_length is not None
                        else None,
                        "sequence": OcelAttributeValue(
                            OcelValueKind.LIST, tuple(_s(a) for a in commitment.sequence)
                        )
                        if commitment.sequence
                        else None,
                        "episode_id": _s(commitment.episode_id) if commitment.episode_id else None,
                        "environment_id": _s(commitment.environment_id)
                        if commitment.environment_id
                        else None,
                        "commitment_ttl": _s(str(ttl_path)),
                    }
                ),
            )
        )
        o2o.append(ObjectObjectLink(commitment_id, task_id, "commitment_of_task"))
        # THIS commitment realizes THAT candidate. Stated at `commit()`;
        # `commitment.ttl` records the plan's digest and cannot carry it.
        for record in _records("plan_committed"):
            if str(record.get("commitment_subject")) != commitment_id:
                continue
            candidate_id = str(record.get("candidate_id") or "")
            if candidate_id in candidate_ids:
                o2o.append(ObjectObjectLink(commitment_id, candidate_id, "realizes_candidate"))
        if domain_id is not None:
            o2o.append(ObjectObjectLink(commitment_id, domain_id, "commits_model"))
        populated_objects.append("POWLCommitment")
    else:
        absent_objects.append(("POWLCommitment", "NO_COMMITMENT_TTL_ON_DISK"))

    # --- AuthorityEnvelope (populated only where receipts carry it) ------
    authority_pairs = sorted(
        {
            (r["authority_ref"], r.get("authority_evidence_ref") or "")
            for r in receipts
            if r.get("authority_ref")
        }
    )
    authority_of_receipt: dict[str, str] = {}
    if authority_pairs:
        for ref, evidence in authority_pairs:
            envelope_id = f"urn:level4:authority:{ref}"
            objects.append(
                OcelObject(
                    envelope_id,
                    "AuthorityEnvelope",
                    _attrs(
                        {
                            "authority_ref": _s(ref),
                            "authority_evidence_ref": _s(evidence) if evidence else None,
                        }
                    ),
                )
            )
        for r in receipts:
            if r.get("authority_ref"):
                authority_of_receipt[r["receipt_id"]] = f"urn:level4:authority:{r['authority_ref']}"
        populated_objects.append("AuthorityEnvelope")
    else:
        absent_objects.append(
            ("AuthorityEnvelope", "NO_RECEIPT_CARRIES_authority_ref (all NULL in this ledger)")
        )

    # --- Receipt / Actuation / PostconditionObservation -------------------
    actuation_ops = {"act", "materialize"}
    receipt_ids = {r["receipt_id"] for r in receipts}
    actuation_of_receipt: dict[str, str] = {}
    observation_of_receipt: dict[str, str] = {}
    # Real bug found and fixed this session (van der Aalst-style integrity
    # audit): NEITHER of the two loops below that can append a real
    # `PostconditionObservation` object guarded against appending the SAME
    # `observation_id` (derived purely from `verification_id`) twice --
    # not even within a single loop. Two different receipts sharing one
    # `verification_id` (a real, legitimate case) silently double-declared
    # the same object id, which `OcelLog.validate()`'s DUPLICATE_ENTITY_ID
    # law (OCPQ Definition 2, law 3) now catches. One real, shared guard
    # for both loops.
    seen_postcondition_ids: set[str] = set()

    for r in receipts:
        rid = r["receipt_id"]
        objects.append(
            OcelObject(
                rid,
                "Receipt",
                _attrs(
                    {
                        "sequence": _i(r["_sequence"]),
                        "operation": _s(str(r.get("operation", ""))),
                        "standing": _s(str(r["standing"])) if r.get("standing") else None,
                        "idempotency_key": _s(str(r["idempotency_key"]))
                        if r.get("idempotency_key")
                        else None,
                        "receipt_digest": _s(str(r["_receipt_digest"])),
                        "previous_digest": _s(str(r["_previous_digest"]))
                        if r.get("_previous_digest")
                        else None,
                        "occurred_at": _s(str(r["occurred_at"])) if r.get("occurred_at") else None,
                    }
                ),
            )
        )
    if receipts:
        populated_objects.append("Receipt")
    else:
        absent_objects.append(("Receipt", "NO_LEDGER_SO_NO_RECEIPTS"))

    # The causal DAG gymact's exporter drops at the OCEL boundary.
    parent_edges = 0
    for r in receipts:
        for parent in r.get("parent_receipt_ids") or []:
            if parent in receipt_ids:
                o2o.append(ObjectObjectLink(r["receipt_id"], parent, "caused_by"))
                parent_edges += 1

    for r in receipts:
        rid = r["receipt_id"]
        if str(r.get("operation")) in actuation_ops:
            actuation_id = f"urn:level4:actuation:{rid}"
            actuation_of_receipt[rid] = actuation_id
            objects.append(
                OcelObject(
                    actuation_id,
                    "Actuation",
                    _attrs(
                        {
                            "operation": _s(str(r.get("operation", ""))),
                            "capability_ref": _s(str(r["capability_ref"]))
                            if r.get("capability_ref")
                            else None,
                            "pre_state_digest": _s(str(r["pre_state_digest"]))
                            if r.get("pre_state_digest")
                            else None,
                            "post_state_digest": _s(str(r["post_state_digest"]))
                            if r.get("post_state_digest")
                            else None,
                            "world_changed": _b(r["world_changed"])
                            if isinstance(r.get("world_changed"), bool)
                            else None,
                        }
                    ),
                )
            )
            o2o.append(ObjectObjectLink(actuation_id, rid, "evidenced_by_receipt"))
            # The edge that did not exist before this module: the committed
            # plan and the thing that actually ran.
            if commitment_id is not None:
                o2o.append(ObjectObjectLink(actuation_id, commitment_id, "actuates_commitment"))
            if r.get("capability_ref") in capability_ids:
                o2o.append(ObjectObjectLink(actuation_id, r["capability_ref"], "exercises_capability"))
            if r.get("subject_ref") in environment_ids:
                o2o.append(ObjectObjectLink(actuation_id, r["subject_ref"], "acts_on_environment"))
            envelope = authority_of_receipt.get(rid)
            if envelope is not None:
                o2o.append(ObjectObjectLink(actuation_id, envelope, "authorized_by"))

        if r.get("verification_id"):
            observation_id = f"urn:level4:postcondition:{r['verification_id']}"
            observation_of_receipt[rid] = observation_id
            if observation_id not in seen_postcondition_ids:
                seen_postcondition_ids.add(observation_id)
                objects.append(
                    OcelObject(
                        observation_id,
                        "PostconditionObservation",
                        _attrs(
                            {
                                "verification_id": _s(str(r["verification_id"])),
                                "verified": _b(r["verified"])
                                if isinstance(r.get("verified"), bool)
                                else None,
                                "acknowledgement_status": _s(str(r["acknowledgement_status"]))
                                if r.get("acknowledgement_status")
                                else None,
                                "observation_confidence": _f(r["observation_confidence"])
                                if isinstance(r.get("observation_confidence"), (int, float))
                                else None,
                            }
                        ),
                    )
                )
            o2o.append(ObjectObjectLink(observation_id, rid, "evidenced_by_receipt"))
            # An observation observes the actuation it was derived from --
            # the receipt whose id appears in this receipt's parents.
            for parent in r.get("parent_receipt_ids") or []:
                target = actuation_of_receipt.get(parent)
                if target is not None:
                    o2o.append(ObjectObjectLink(observation_id, target, "observes_actuation"))

    # --- independent goal consequence ------------------------------------
    #
    # The admitted Goal's consequence is a SEPARATE claim from process
    # conformance, and it enters only through a `goal_consequence_observed`
    # record written when the independent verifier returned. A lawful
    # execution that did not reach the goal stays fully representable here --
    # it records `refutes_goal`, which is a checked negative observation, not
    # an absence.
    verifier_ids: list[str] = []
    goal_observations: list[str] = []
    # Reuses `seen_postcondition_ids` declared above the first
    # `PostconditionObservation` loop (do NOT re-initialize it here --
    # this loop must see ids the first loop already appended too, which a
    # prior version of this fix got wrong by shadowing the name with a
    # narrower, loop-2-only set).
    for record in _records("goal_consequence_observed"):
        goal_id = str(record.get("goal_id") or "")
        actuation_id = actuation_of_receipt.get(str(record.get("actuation_receipt_id") or ""))
        if goal_id not in goal_ids or actuation_id is None:
            continue
        observation_id = f"urn:level4:postcondition:{record['verification_id']}"
        if observation_id not in seen_postcondition_ids:
            seen_postcondition_ids.add(observation_id)
            objects.append(
                OcelObject(
                    observation_id,
                    "PostconditionObservation",
                    _attrs(
                        {
                            "verification_id": _s(str(record["verification_id"])),
                            "scope": _s("ADMITTED_GOAL"),
                            "outcome": _s(str(record["outcome"])),
                        }
                    ),
                )
            )
        o2o.append(ObjectObjectLink(observation_id, actuation_id, "observes_actuation"))
        o2o.append(
            ObjectObjectLink(
                observation_id,
                goal_id,
                "establishes_goal" if record["outcome"] == "ESTABLISHED" else "refutes_goal",
            )
        )
        goal_observations.append(observation_id)

        # The observer is an object with its own identity, so
        # SELF_CERTIFIED_POSTCONDITION is readable off the graph (the verifier
        # identity coincides with the actuator identity) instead of asserted.
        verifier_id = str(record.get("verifier_id") or "")
        if verifier_id:
            if verifier_id not in verifier_ids:
                objects.append(
                    OcelObject(
                        verifier_id,
                        "IndependentVerifier",
                        _attrs(
                            {
                                "verifier_id": _s(verifier_id),
                                "actuator_id": _s(str(record.get("actuator_id") or "")),
                            }
                        ),
                    )
                )
                verifier_ids.append(verifier_id)
            o2o.append(ObjectObjectLink(observation_id, verifier_id, "verified_by"))
    if verifier_ids:
        populated_objects.append("IndependentVerifier")
    else:
        absent_objects.append(
            ("IndependentVerifier", "NO_goal_consequence_observed_RECORD_IN_WITNESS_JOURNAL")
        )
    if actuation_of_receipt:
        populated_objects.append("Actuation")
    else:
        absent_objects.append(("Actuation", "NO_RECEIPT_WITH_OPERATION_IN_{act,materialize}"))
    if observation_of_receipt or goal_observations:
        populated_objects.append("PostconditionObservation")
    else:
        absent_objects.append(
            ("PostconditionObservation", "NO_RECEIPT_CARRIES_verification_id")
        )

    # --- Replay: the ledger's own head, which is what a replay checks -----
    # A Replay object used to be synthesised here from `receipts[-1]`, i.e.
    # from the mere existence of a ledger head. That manufactured a replay out
    # of the absence of one: a trial whose `replay_ledger` never ran got an
    # identical object to a trial whose replay ran and passed. It is now
    # emitted only from a `replay_completed` record, which names the exact
    # receipt the replay bound.
    replay_id: str | None = None
    for record in _records("replay_completed"):
        receipt_id = str(record.get("receipt_id") or "")
        if receipt_id not in receipt_ids:
            continue
        replay_id = f"urn:level4:replay:{record['head_digest']}"
        objects.append(
            OcelObject(
                replay_id,
                "Replay",
                _attrs(
                    {
                        "head_digest": _s(str(record["head_digest"])),
                        "record_count": _i(record["record_count"]),
                        "mode": _s(str(record.get("mode", ""))),
                        "valid": _b(bool(record.get("valid"))),
                        "ledger": _s(str(ledger_path)),
                    }
                ),
            )
        )
        o2o.append(ObjectObjectLink(replay_id, task_id, "replay_of_task"))
        o2o.append(ObjectObjectLink(replay_id, receipt_id, "replays"))
    if replay_id is not None:
        populated_objects.append("Replay")
    else:
        absent_objects.append(
            ("Replay", "NO_replay_completed_RECORD_BINDING_A_RECEIPT_IN_THIS_LEDGER")
        )

    # ── events ────────────────────────────────────────────────────────────
    #
    # Every event links the Task, so `validate_locality("Task", ...)` has a
    # unique reference object per event (Gianola Assumption 3).

    log = OcelLog.new(objects=objects, object_object_links=o2o)
    # Real object-centric integrity check (OCPQ Definition 2, per
    # OcelLog.validate()'s own docstring) -- van der Aalst-style audit
    # found this function previously constructed and returned/persisted
    # its log with NO integrity check anywhere in its own call chain
    # (`_persist_level4_ocel` writes `built.log.to_ocel2_json()` straight
    # to disk). Events are appended below with real, individually-gated
    # O2O links; validating here, before any event is appended, would be
    # premature (no events exist yet) -- the real check happens once
    # events are appended, right before this function returns (see the
    # `log = log.validate()` call near the end of this function).

    first_receipt_ns = (
        parse_ns(receipts[0]["occurred_at"]) if receipts and receipts[0].get("occurred_at") else 0
    )

    pre: list[tuple[str, str, list[Any], dict[str, OcelAttributeValue | None]]] = []

    pre.append(
        (
            f"{task_id}:TaskAdmitted",
            "TaskAdmitted",
            [(task_id, "task")],
            {
                "seed": _i(seed) if seed is not None else None,
                "manifest_digest": _s(manifest_digest) if manifest_digest else None,
            },
        )
    )
    for goal_id in goal_ids:
        pre.append(
            (
                f"{goal_id}:GoalAdmitted",
                "GoalAdmitted",
                [(task_id, "task"), (goal_id, "goal")],
                {},
            )
        )
    for candidate_id in selected_candidates:
        links_sel: list[Any] = [(task_id, "task"), (candidate_id, "candidate")]
        for goal_id in goal_ids:
            links_sel.append((goal_id, "goal"))
        pre.append((f"{candidate_id}:CandidateSelected", "CandidateSelected", links_sel, {}))
    if environment_id is not None:
        pre.append(
            (
                f"{task_id}:SessionStarted",
                "SessionStarted",
                [(task_id, "task"), (environment_id, "environment")],
                {"episode_id": _s(episode_id) if episode_id else None},
            )
        )
    if capability_ids:
        pre.append(
            (
                f"{task_id}:CapabilitiesObserved",
                "CapabilitiesObserved",
                [(task_id, "task")] + [(c, "capability") for c in capability_ids],
                {"n_capabilities": _i(len(capability_ids))},
            )
        )
    for index, probe in enumerate(probe_records):
        pre.append(
            (
                f"{task_id}:ProbeExecuted:{index}",
                "ProbeExecuted",
                [(task_id, "task"), (f"{task_id}:probe:{index}", "probe")],
                {
                    "action": _s(str(probe.get("action", ""))),
                    "applicable": _b(bool(probe.get("applicable", False))),
                },
            )
        )
    if domain_id is not None:
        pre.append(
            (
                f"{task_id}:ModelInferred",
                "ModelInferred",
                [(task_id, "task"), (domain_id, "model")],
                {"model_digest": _s(commitment.model_digest)} if commitment else {},
            )
        )
    for index, attempt in enumerate(attempt_records):
        links: list[Any] = [(task_id, "task"), (f"{task_id}:attempt:{index}", "attempt")]
        candidate_id = f"{task_id}:candidate:{index}"
        if candidate_id in candidate_ids:
            links.append((candidate_id, "candidate"))
        pre.append(
            (
                f"{task_id}:PlanConstructed:{index}",
                "PlanConstructed",
                links,
                {
                    "planner": _s(str(attempt.get("planner", ""))),
                    "outcome": _s(str(attempt.get("outcome", ""))),
                },
            )
        )
    if commitment_id is not None and commitment is not None:
        links = [(task_id, "task"), (commitment_id, "commitment")]
        if domain_id is not None:
            links.append((domain_id, "model"))
        pre.append(
            (
                f"{task_id}:POWLCommitted",
                "POWLCommitted",
                links,
                {
                    "plan_digest": _s(commitment.plan_digest),
                    "model_digest": _s(commitment.model_digest),
                    "episode_id": _s(commitment.episode_id) if commitment.episode_id else None,
                },
            )
        )

    # Derived ordinals, strictly before the first observed receipt instant.
    span = len(pre)
    for offset, (event_id, activity, links, attributes) in enumerate(pre):
        attributes = dict(attributes)
        attributes["time_basis"] = _s("DERIVED_ORDINAL")
        log = log.append_event(
            event_id,
            activity,
            links,
            timestamp_ns=first_receipt_ns - (span - offset),
            attributes=_attrs(attributes),
        )
        populated_events.append(activity)

    # --- receipt-derived events (observed instants) ----------------------
    emitted_authority: set[str] = set()
    for r in receipts:
        rid = r["receipt_id"]
        when = parse_ns(r["occurred_at"]) if r.get("occurred_at") else 0
        base: list[Any] = [(task_id, "task"), (rid, "receipt")]
        if r.get("subject_ref") in environment_ids:
            base.append((r["subject_ref"], "environment"))
        if r.get("capability_ref") in capability_ids:
            base.append((r["capability_ref"], "capability"))

        envelope = authority_of_receipt.get(rid)
        if envelope is not None and envelope not in emitted_authority:
            emitted_authority.add(envelope)
            log = log.append_event(
                f"{rid}:AuthorityAdmitted",
                "AuthorityAdmitted",
                [(task_id, "task"), (envelope, "authority")],
                timestamp_ns=when,
                attributes=_attrs(
                    {"authority_ref": _s(str(r["authority_ref"])), "time_basis": _s("OBSERVED")}
                ),
            )
            populated_events.append("AuthorityAdmitted")

        actuation_id = actuation_of_receipt.get(rid)
        if actuation_id is not None:
            opened = list(base) + [(actuation_id, "actuation")]
            if commitment_id is not None:
                opened.append((commitment_id, "commitment"))
            if envelope is not None:
                opened.append((envelope, "authority"))
            log = log.append_event(
                f"{rid}:ActuationOpened",
                "ActuationOpened",
                opened,
                timestamp_ns=when,
                attributes=_attrs(
                    {
                        "operation": _s(str(r.get("operation", ""))),
                        "pre_state_digest": _s(str(r["pre_state_digest"]))
                        if r.get("pre_state_digest")
                        else None,
                        "time_basis": _s("OBSERVED"),
                    }
                ),
            )
            populated_events.append("ActuationOpened")
            log = log.append_event(
                f"{rid}:ActuationClosed",
                "ActuationClosed",
                opened,
                timestamp_ns=when,
                attributes=_attrs(
                    {
                        "post_state_digest": _s(str(r["post_state_digest"]))
                        if r.get("post_state_digest")
                        else None,
                        "world_changed": _b(r["world_changed"])
                        if isinstance(r.get("world_changed"), bool)
                        else None,
                        "time_basis": _s("OBSERVED"),
                    }
                ),
            )
            populated_events.append("ActuationClosed")

        observation_id = observation_of_receipt.get(rid)
        if observation_id is not None:
            observed = list(base) + [(observation_id, "observation")]
            log = log.append_event(
                f"{rid}:PostconditionObserved",
                "PostconditionObserved",
                observed,
                timestamp_ns=when,
                attributes=_attrs(
                    {
                        "verification_id": _s(str(r["verification_id"])),
                        "time_basis": _s("OBSERVED"),
                    }
                ),
            )
            populated_events.append("PostconditionObserved")
            if isinstance(r.get("verified"), bool):
                log = log.append_event(
                    f"{rid}:PostconditionVerified",
                    "PostconditionVerified",
                    observed,
                    timestamp_ns=when,
                    attributes=_attrs(
                        {
                            "verified": _b(r["verified"]),
                            "acknowledgement_status": _s(str(r["acknowledgement_status"]))
                            if r.get("acknowledgement_status")
                            else None,
                            "time_basis": _s("OBSERVED"),
                        }
                    ),
                )
                populated_events.append("PostconditionVerified")

        log = log.append_event(
            f"{rid}:ReceiptEmitted",
            "ReceiptEmitted",
            base,
            timestamp_ns=when,
            attributes=_attrs(
                {
                    "receipt_digest": _s(str(r["_receipt_digest"])),
                    "standing": _s(str(r["standing"])) if r.get("standing") else None,
                    "time_basis": _s("OBSERVED"),
                }
            ),
        )
        populated_events.append("ReceiptEmitted")

    if goal_observations and receipts:
        after_ns = parse_ns(receipts[-1]["occurred_at"]) if receipts[-1].get("occurred_at") else 0
        for record in _records("goal_consequence_observed"):
            observation_id = f"urn:level4:postcondition:{record['verification_id']}"
            if observation_id not in goal_observations:
                continue
            links_goal: list[Any] = [
                (task_id, "task"),
                (observation_id, "observation"),
                (str(record["goal_id"]), "goal"),
            ]
            if str(record.get("verifier_id") or "") in verifier_ids:
                links_goal.append((str(record["verifier_id"]), "verifier"))
            log = log.append_event(
                f"{observation_id}:GoalConsequenceObserved",
                "GoalConsequenceObserved",
                links_goal,
                timestamp_ns=after_ns + 1,
                attributes=_attrs(
                    {
                        "outcome": _s(str(record["outcome"])),
                        "verification_id": _s(str(record["verification_id"])),
                        "time_basis": _s("DERIVED_ORDINAL"),
                    }
                ),
            )
            populated_events.append("GoalConsequenceObserved")

    if replay_id is not None and receipts:
        last_ns = parse_ns(receipts[-1]["occurred_at"]) if receipts[-1].get("occurred_at") else 0
        log = log.append_event(
            f"{task_id}:ReplayCompleted",
            "ReplayCompleted",
            [(task_id, "task"), (replay_id, "replay")],
            timestamp_ns=last_ns + 1,
            attributes=_attrs(
                {
                    "head_digest": _s(str(receipts[-1]["_receipt_digest"])),
                    "record_count": _i(len(receipts)),
                    "time_basis": _s("DERIVED_ORDINAL"),
                }
            ),
        )
        populated_events.append("ReplayCompleted")

    populated_event_set = tuple(t for t in LEVEL4_EVENT_TYPES if t in set(populated_events))
    for name in LEVEL4_EVENT_TYPES:
        if name in populated_event_set:
            continue
        absent_events.append((name, _EVENT_ABSENCE_REASON.get(name, "NO_SOURCE_DATA_ON_DISK")))

    report = Level4OcelReport(
        populated_object_types=tuple(t for t in LEVEL4_OBJECT_TYPES if t in set(populated_objects)),
        populated_event_types=populated_event_set,
        absent_object_types=tuple(absent_objects),
        absent_event_types=tuple(absent_events),
        sources_read=tuple(sources_read),
        sources_absent=tuple(sources_absent),
    )
    # Real integrity check before this log is ever returned/persisted --
    # OcelLog.validate() enforces OCPQ Definition 2 (no dangling E2O
    # links, no duplicate ids, no time-stable-attribute mutation, every
    # event has >=1 real object link). Raises OcelError, never silently
    # swallowed -- a structurally invalid Level 4 log must never reach
    # `_persist_level4_ocel`'s `to_ocel2_json()` write to disk.
    log = log.validate()

    return Level4Ocel(
        log=log,
        report=report,
        commitment=commitment,
        episode_id=episode_id,
        environment_id=environment_id,
        task_id=task_id,
    )


_EVENT_ABSENCE_REASON: dict[str, str] = {
    "GoalAdmitted": "NO_goal_admitted_RECORD_IN_WITNESS_JOURNAL",
    "CandidateSelected": "NO_candidate_selected_RECORD_IN_WITNESS_JOURNAL",
    "GoalConsequenceObserved": "NO_goal_consequence_observed_RECORD_IN_WITNESS_JOURNAL",
    "SessionStarted": "NO_SINGLE_ENVIRONMENT_ID_IN_RECEIPTS",
    "CapabilitiesObserved": "NO_RECEIPTS_WITH_CAPABILITY_REF",
    "ProbeExecuted": "NO_PROBE_LOG_ON_DISK",
    "ModelInferred": "NO_COMMITMENT_TTL_SO_NO_MODEL_DIGEST",
    "PlanConstructed": "NO_FEDERATION_JSON_OR_NO_ATTEMPTS",
    "POWLCommitted": "NO_COMMITMENT_TTL_ON_DISK",
    "AuthorityAdmitted": "NO_RECEIPT_CARRIES_authority_ref",
    "ActuationOpened": "NO_RECEIPT_WITH_OPERATION_IN_{act,materialize}",
    "ActuationClosed": "NO_RECEIPT_WITH_OPERATION_IN_{act,materialize}",
    "PostconditionObserved": "NO_RECEIPT_CARRIES_verification_id",
    "PostconditionVerified": "NO_RECEIPT_CARRIES_BOOLEAN_verified",
    "ReceiptEmitted": "NO_LEDGER_SO_NO_RECEIPTS",
    "ReplayCompleted": "NO_replay_completed_RECORD_BINDING_A_RECEIPT_IN_THIS_LEDGER",
}
