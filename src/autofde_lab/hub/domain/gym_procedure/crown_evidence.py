# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Branchless, typed-evidence Level 4 crown standing.

`crown_factor.py` scored the acceptance equation as a conjunction of seven
independently-constructed booleans-with-provenance. That representation is
kept, unchanged, as a read-only compatibility shim over legacy scoreboard
rows (see `conjunction_from_row`) -- but it is no longer the live
construction path.

This module's first typed-evidence pass (commit 106e595) collapsed two
genuinely distinct claims into one `AliveEvidence` type:

1. the execution's OCEL process evidence is conformant (schema-valid,
   conformant operations, valid replay, receipts present);
2. the Level 4 task's actual goal consequence was independently observed as
   achieved.

That commit's own message named the fault line directly: replacing
`real_goal_attained` (a boolean field on `TrialReport`) with nothing --
`standing_from_episode`'s chain never checked the goal at all, so a
perfectly-evidenced-but-wrong-final-state episode (every process check
green, goal never established) could reach `AliveEvidence`. This revision
splits the claim so that can no longer happen:

* :class:`ConformantExecutionEvidence` -- what `AliveEvidence` used to mean:
  every real process check (schema, conformance replay, replay validity,
  receipted postcondition reference) produced positive evidence. Says
  nothing about the goal.
* :class:`GoalConsequenceEvidence` -- a real, independently-observed
  postcondition read directly off a `verify_goal_consequence` OCEL event
  (projected from a real `gymact.models.VerificationResult` by
  `level4_crown.py`'s execution bridge -- see that module's `_EXECUTE_SCRIPT`
  and `standing_from_episode`'s `_goal_consequence_from_log`). Never a
  locally re-derived `final_state == expected` comparison.
* :class:`Level4AliveEvidence` -- the ONLY green verdict. Constructible only
  by composing a real `ConformantExecutionEvidence` with a real
  `GoalConsequenceEvidence` whose `passed` is `True`. Composition, not a
  boolean flag: there is no constructor path that accepts "trust me, the
  goal was met" without the actual `GoalConsequenceEvidence` object.
* :class:`ConformantButGoalUnmetEvidence` -- the process evidence is clean
  (a real `ConformantExecutionEvidence` was built) but the goal consequence
  is either absent from the OCEL graph or was independently observed as
  `passed=False`. This is a real, checked, negative finding, and is
  deliberately its own type rather than folding into `UnknownEvidence`: a
  caller must be able to tell "the process ran cleanly and the goal was NOT
  established" apart from "we don't know what happened."
* :class:`UnknownEvidence` -- the chain stopped at a named point because a
  process-level check failed or its precondition (a postcondition
  reference, a non-empty receipt list) was absent. Never reached the point
  of having a `ConformantExecutionEvidence` to evaluate the goal against.
* :class:`RefusedEvidence` / :class:`BlockedEvidence` / :class:`UnsupportedEvidence`
  -- typed non-outcomes for call sites that need to report a refusal,
  external blocker, or missing capability without going through the episode
  chain at all (mirrors `CrownFactor.refused/.blocked/.unsupported`).

None of the seven variants defines ``__bool__``: there is no boolean
shortcut standing in for "is this ALIVE?" -- callers must ``match`` on the
type, exactly as `CrownFactor.holds` denies `if factor:` a plausible verdict.

See `.claude/rules/absence-is-not-evidence.md` and `crown_factor.py`'s own
module docstring for the governing law this file inherits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import jsonschema

from gymact.ocel import digest_ocel_log, validate_ocel_log
from gymact.process import ConformanceChecker, ConformanceResult
from gymact.replay import ReplayReport

#: The OCEL event type `level4_crown.py`'s execution bridge projects a real
#: `gymact.models.VerificationResult` into. `gymact.ocel.receipts_to_ocel`
#: does not itself emit this event type -- the independent final-goal
#: verification runs through a bare `kernel.verify()` call and produces no
#: `Receipt`, so nothing in gymact's own OCEL projection carries it. The
#: bridge script appends this event by hand, from the real
#: `VerificationResult` it already has in memory, before the log crosses the
#: subprocess boundary. See `level4_crown.py`'s `_EXECUTE_SCRIPT`.
GOAL_CONSEQUENCE_EVENT_TYPE = "verify_goal_consequence"


@dataclass(frozen=True)
class ConformantExecutionEvidence:
    """Every real process-level check in the chain produced positive
    evidence: OCEL schema validity, conformant operation replay, a valid
    `ReplayReport`, a named postcondition reference, and a non-empty receipt
    list. Says nothing about whether the goal itself was established --
    that is `GoalConsequenceEvidence`'s claim, not this one.

    Every field is a real artifact reference or a real collaborator's own
    return value -- never a fabricated default. `standing_from_episode` is
    the only place permitted to construct this type.
    """

    episode_digest: str
    conformance: ConformanceResult
    replay: ReplayReport
    receipt_id: str
    postcondition_ref: str


@dataclass(frozen=True)
class GoalConsequenceEvidence:
    """A real, independently-observed postcondition for the exact admitted
    goal of the exact admitted task -- read directly off a real
    `verify_goal_consequence` OCEL event, itself projected from a real
    `gymact.models.VerificationResult` (`verification_id`, `passed`,
    `expected`, `observed`, `state_digest`). Never a locally re-derived
    `final_state == expected` boolean comparison: the `passed` field here is
    gymact's own kernel's own independent verdict, carried through
    unmodified.
    """

    verification_id: str
    passed: bool
    expected_digest: str
    observed_digest: str
    state_digest: str


@dataclass(frozen=True)
class Level4AliveEvidence:
    """The ONLY green verdict. Constructible only by composing a real
    `ConformantExecutionEvidence` with a real `GoalConsequenceEvidence`
    whose `passed` is `True` -- composition, not a boolean flag. A
    perfectly-evidenced-but-wrong-final-state episode (every process check
    green, goal never established or reported False) cannot reach this
    type; it reaches `ConformantButGoalUnmetEvidence` instead.
    """

    conformant: ConformantExecutionEvidence
    goal: GoalConsequenceEvidence


@dataclass(frozen=True)
class ConformantButGoalUnmetEvidence:
    """The process evidence is real and clean -- a real
    `ConformantExecutionEvidence` was built -- but the goal consequence is
    either absent from the OCEL graph (`goal is None`) or was independently
    observed as `passed=False`. A real, checked, negative finding:
    deliberately its own type rather than `UnknownEvidence`, so a caller can
    tell "the process ran cleanly and the goal was NOT established" apart
    from "we don't know what happened at all."
    """

    conformant: ConformantExecutionEvidence
    goal: GoalConsequenceEvidence | None
    reason: str


@dataclass(frozen=True)
class UnknownEvidence:
    """The chain stopped at a named point, before a `ConformantExecutionEvidence`
    could even be built. Never evidence of failure, and never evidence of
    success -- exactly `FactorState.UNKNOWN`'s meaning."""

    missing: str
    episode_digest: str | None = None


@dataclass(frozen=True)
class RefusedEvidence:
    """A typed refusal is a real answer, not an absence."""

    reason: str
    subject: str


@dataclass(frozen=True)
class BlockedEvidence:
    """A named external prerequisite prevented observation."""

    reason: str


@dataclass(frozen=True)
class UnsupportedEvidence:
    """A capability/dependency genuinely absent."""

    reason: str


Standing = Union[
    Level4AliveEvidence,
    ConformantButGoalUnmetEvidence,
    UnknownEvidence,
    RefusedEvidence,
    BlockedEvidence,
    UnsupportedEvidence,
]


def _conformant_execution_evidence_to_dict(evidence: ConformantExecutionEvidence) -> dict:
    return {
        "episode_digest": evidence.episode_digest,
        "conformance": {
            "conformant": evidence.conformance.conformant,
            "deviations": [d.model_dump() for d in evidence.conformance.deviations],
        },
        "replay": {
            "mode": evidence.replay.mode.value
            if hasattr(evidence.replay.mode, "value")
            else str(evidence.replay.mode),
            "valid": evidence.replay.valid,
            "record_count": evidence.replay.record_count,
            "head_digest": evidence.replay.head_digest,
            "mismatches": list(evidence.replay.mismatches),
        },
        "receipt_id": evidence.receipt_id,
        "postcondition_ref": evidence.postcondition_ref,
    }


def _conformant_execution_evidence_from_dict(payload: dict) -> ConformantExecutionEvidence:
    from gymact.process import ConformanceResult
    from gymact.replay import ReplayMode, ReplayReport

    replay_payload = dict(payload["replay"])
    replay_payload["mode"] = ReplayMode(replay_payload["mode"])
    return ConformantExecutionEvidence(
        episode_digest=payload["episode_digest"],
        conformance=ConformanceResult.model_validate(payload["conformance"]),
        replay=ReplayReport.model_validate(replay_payload),
        receipt_id=payload["receipt_id"],
        postcondition_ref=payload["postcondition_ref"],
    )


def _goal_consequence_evidence_to_dict(goal: GoalConsequenceEvidence | None) -> dict | None:
    if goal is None:
        return None
    return {
        "verification_id": goal.verification_id,
        "passed": goal.passed,
        "expected_digest": goal.expected_digest,
        "observed_digest": goal.observed_digest,
        "state_digest": goal.state_digest,
    }


def _goal_consequence_evidence_from_dict(payload: dict | None) -> GoalConsequenceEvidence | None:
    if payload is None:
        return None
    return GoalConsequenceEvidence(
        verification_id=payload["verification_id"],
        passed=payload["passed"],
        expected_digest=payload["expected_digest"],
        observed_digest=payload["observed_digest"],
        state_digest=payload["state_digest"],
    )


def standing_to_dict(standing: Standing) -> dict:
    """Lossless dict representation, discriminated by `variant`, so
    `crown_run.json` can serialize any of the six live cases without
    guessing which fields are present."""
    if isinstance(standing, Level4AliveEvidence):
        return {
            "variant": "Level4AliveEvidence",
            "conformant": _conformant_execution_evidence_to_dict(standing.conformant),
            "goal": _goal_consequence_evidence_to_dict(standing.goal),
        }
    if isinstance(standing, ConformantButGoalUnmetEvidence):
        return {
            "variant": "ConformantButGoalUnmetEvidence",
            "conformant": _conformant_execution_evidence_to_dict(standing.conformant),
            "goal": _goal_consequence_evidence_to_dict(standing.goal),
            "reason": standing.reason,
        }
    if isinstance(standing, UnknownEvidence):
        return {
            "variant": "UnknownEvidence",
            "missing": standing.missing,
            "episode_digest": standing.episode_digest,
        }
    if isinstance(standing, RefusedEvidence):
        return {"variant": "RefusedEvidence", "reason": standing.reason, "subject": standing.subject}
    if isinstance(standing, BlockedEvidence):
        return {"variant": "BlockedEvidence", "reason": standing.reason}
    if isinstance(standing, UnsupportedEvidence):
        return {"variant": "UnsupportedEvidence", "reason": standing.reason}
    raise TypeError(f"UNKNOWN_STANDING_VARIANT:{type(standing).__name__}")


def standing_from_dict(payload: dict) -> Standing:
    """Reconstruct a `Standing` from its `standing_to_dict` serialization,
    using real gymact model reconstruction (`model_validate`) for the
    nested `ConformanceResult`/`ReplayReport` -- never a re-derived or
    approximated stand-in for either."""
    variant = payload["variant"]
    if variant == "Level4AliveEvidence":
        goal = _goal_consequence_evidence_from_dict(payload["goal"])
        if goal is None:
            # Level4AliveEvidence.goal is non-Optional by construction (see
            # its class docstring) -- a serialized row claiming this variant
            # with a null goal is a corrupted/malformed record, not a
            # legitimate Level4AliveEvidence. Refuse rather than silently
            # constructing a type-invalid instance (dataclasses don't
            # enforce field types at runtime).
            raise ValueError(
                "CORRUPT_LEVEL4_ALIVE_EVIDENCE_ROW:goal is null but "
                "Level4AliveEvidence requires a real GoalConsequenceEvidence"
            )
        return Level4AliveEvidence(
            conformant=_conformant_execution_evidence_from_dict(payload["conformant"]),
            goal=goal,
        )
    if variant == "ConformantButGoalUnmetEvidence":
        return ConformantButGoalUnmetEvidence(
            conformant=_conformant_execution_evidence_from_dict(payload["conformant"]),
            goal=_goal_consequence_evidence_from_dict(payload["goal"]),
            reason=payload["reason"],
        )
    if variant == "UnknownEvidence":
        return UnknownEvidence(missing=payload["missing"], episode_digest=payload["episode_digest"])
    if variant == "RefusedEvidence":
        return RefusedEvidence(reason=payload["reason"], subject=payload["subject"])
    if variant == "BlockedEvidence":
        return BlockedEvidence(reason=payload["reason"])
    if variant == "UnsupportedEvidence":
        return UnsupportedEvidence(reason=payload["reason"])
    raise ValueError(f"UNKNOWN_STANDING_VARIANT_IN_PAYLOAD:{variant}")


def _goal_consequence_from_log(log: dict) -> GoalConsequenceEvidence | None:
    """Scan `log`'s real OCEL events for a real `verify_goal_consequence`
    event -- the independently-observed postcondition for the task's exact
    admitted goal, projected by `level4_crown.py`'s execution bridge from a
    real `gymact.models.VerificationResult` (see that module's
    `_EXECUTE_SCRIPT`). Returns `None` when no such event is present in the
    graph -- never fabricates one, and never falls back to a locally
    re-derived comparison.
    """
    for event in log.get("events", []) or []:
        if event.get("type") != GOAL_CONSEQUENCE_EVENT_TYPE:
            continue
        attrs = {a["name"]: a["value"] for a in event.get("attributes", []) or []}
        if "verification_id" not in attrs or "passed" not in attrs:
            continue
        # OCEL 2.0's schema requires every event attribute `value` to be a
        # JSON string (see `level4_crown.py`'s `_EXECUTE_SCRIPT` comment at
        # the projection site), so `passed` arrives as the real boolean's
        # string form ("True"/"False"), never a native JSON boolean.
        # `bool(attrs["passed"])` would be wrong here -- `bool("False")` is
        # `True` -- so this compares the string explicitly instead.
        raw_passed = attrs["passed"]
        passed = raw_passed is True or str(raw_passed) == "True"
        return GoalConsequenceEvidence(
            verification_id=str(attrs["verification_id"]),
            passed=passed,
            expected_digest=str(attrs.get("expected_digest", "")),
            observed_digest=str(attrs.get("observed_digest", "")),
            state_digest=str(attrs.get("state_digest", "")),
        )
    return None


def standing_from_episode(
    log: dict,
    operations: list,
    receipts: list,
    *,
    replay: ReplayReport,
    receipt_id: str | None = None,
    postcondition_ref: str | None,
) -> Standing:
    """The ONLY constructor of a live `Standing`. Runs the real chain:

    1. real OCEL 2.0 schema validation of ``log``
       (`gymact.ocel.validate_ocel_log`);
    2. real conformance replay of ``operations``
       (`gymact.process.ConformanceChecker().check(...)`);
    3. the passed-in, already-produced `replay` (`gymact.replay.ReplayReport`)
       for this episode, checked for `.valid`;
    4. requiring ``postcondition_ref`` is not None and ``receipts`` is
       non-empty.

    Only when every one of those steps produces real positive evidence does
    a real `ConformantExecutionEvidence` get built. That is necessary but no
    longer sufficient for a green verdict: this function then looks, in
    ``log`` itself, for a real `GoalConsequenceEvidence`
    (`_goal_consequence_from_log`) -- an independently-observed postcondition
    for the task's exact admitted goal. Only when BOTH the process evidence
    is clean AND the goal consequence was observed `passed=True` does this
    return `Level4AliveEvidence`. Clean process evidence with an absent or
    failing goal consequence returns `ConformantButGoalUnmetEvidence`
    instead -- a real, checked, negative finding, not a silent `AliveEvidence`
    and not an `UnknownEvidence`.

    This function takes no boolean `success` or `goal_reached` parameter and
    derives its answer from nothing but the real collaborators given to it
    and the real evidence already present in ``log``.

    Deviation from the literal signature named in the task spec: `replay`
    is threaded in as an explicit keyword argument rather than derived
    inside this function, because producing a `ReplayReport` requires a
    live `LedgerLike` (`gymact.replay.replay_ledger(ledger, ...)`), and this
    function is deliberately kept free of any ledger/subprocess/IO
    dependency so it can be unit-tested with plain real objects. The task
    text itself says "then the passed-in replay report", which only parses
    if `replay` is a parameter; the four-argument signature literally
    written in the task omits it, which would make step 3 an unaddressable
    instruction. `receipt_id` is likewise threaded in explicitly (taken
    from the first real receipt when the caller does not supply one) so
    `ConformantExecutionEvidence.receipt_id` names a real receipt rather
    than a fabricated placeholder.
    """
    try:
        validate_ocel_log(log)
    except jsonschema.ValidationError as exc:
        return UnknownEvidence(missing=f"OCEL_SCHEMA_INVALID:{exc.message}", episode_digest=None)

    episode_digest = digest_ocel_log(log)

    conformance = ConformanceChecker().check(operations)
    if not conformance.conformant:
        reasons = "; ".join(d.reason for d in conformance.deviations)
        return UnknownEvidence(
            missing=f"CONFORMANCE_DEVIATIONS:{reasons}", episode_digest=episode_digest
        )

    if not replay.valid:
        mismatches = "; ".join(replay.mismatches) or "REPLAY_REPORTED_INVALID_NO_MISMATCH_DETAIL"
        return UnknownEvidence(missing=f"REPLAY_INVALID:{mismatches}", episode_digest=episode_digest)

    if postcondition_ref is None:
        return UnknownEvidence(missing="POSTCONDITION_REF_ABSENT", episode_digest=episode_digest)

    if not receipts:
        return UnknownEvidence(missing="RECEIPTS_EMPTY", episode_digest=episode_digest)

    resolved_receipt_id = receipt_id if receipt_id is not None else str(receipts[0].receipt_id)

    conformant = ConformantExecutionEvidence(
        episode_digest=episode_digest,
        conformance=conformance,
        replay=replay,
        receipt_id=resolved_receipt_id,
        postcondition_ref=postcondition_ref,
    )

    goal = _goal_consequence_from_log(log)
    if goal is not None and goal.passed:
        return Level4AliveEvidence(conformant=conformant, goal=goal)

    reason = (
        "GOAL_CONSEQUENCE_ABSENT_FROM_OCEL_GRAPH"
        if goal is None
        else f"GOAL_CONSEQUENCE_REPORTED_FALSE:verification_id={goal.verification_id}"
    )
    return ConformantButGoalUnmetEvidence(conformant=conformant, goal=goal, reason=reason)
