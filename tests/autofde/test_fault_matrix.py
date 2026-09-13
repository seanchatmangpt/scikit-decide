# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The deterministic fault matrix: eleven faults, exactly one outcome each.

Deliberately few collected items. Each test loops the whole table and
**accumulates** every mismatch before asserting the accumulator is empty, so a
failure names every misclassified fault at once instead of stopping at the
first. A suite that reports one fault per run turns an eleven-way regression
into eleven debugging sessions.
"""

from __future__ import annotations

import pytest

from autofde_lab.agent.faults import (
    DECLARED_MAPPING_ONLY,
    FaultKind,
    FaultObservation,
    FaultOutcome,
    classify,
    observe_duplicate_observation,
    observe_label_context_collision,
    observe_torn_fire,
)
from autofde_lab.agent.ledger import OccurrenceLedger
from autofde_lab.agent.refusals import AgentRefusal, AgentRefusalCode
from autofde_lab.powl.identity import OccurrenceKey

K = FaultKind
O = FaultOutcome

#: ``(spec number, observation, required outcome)``. The spec numbering is
#: carried so a failure message points at the requirement, not just the enum.
FAULT_CASES: tuple[tuple[int, FaultObservation, FaultOutcome], ...] = (
    (1, FaultObservation(K.DUPLICATE_OBSERVATION, already_committed=True), O.CONTINUE),
    (2, FaultObservation(K.OUT_OF_ORDER_OBSERVATION), O.REPAIR),
    (3, FaultObservation(K.DOWNSTREAM_TIMEOUT, attempt=1, retry_bound=3), O.RETRY_WITHIN_BOUND),
    (4, FaultObservation(K.NOTIFICATION_REJECTED), O.REPAIR),
    (5, FaultObservation(K.EVIDENCE_SINK_UNAVAILABLE, attempt=1, retry_bound=3), O.RETRY_WITHIN_BOUND),
    (6, FaultObservation(K.IDENTITY_FORBIDDEN), O.REQUEST_NEW_AUTHORITY),
    (7, FaultObservation(K.AUTHORITY_EXPIRED), O.REQUEST_NEW_AUTHORITY),
    (8, FaultObservation(K.POPULATION_EXPANDED), O.REPLAN),
    (9, FaultObservation(K.POSTCONDITION_UNCONFIRMED), O.UNKNOWN),
    (
        10,
        FaultObservation(K.LABEL_CONTEXT_COLLISION, keys_compared=True, context_diverged=True),
        O.REPLAN,
    ),
    (11, FaultObservation(K.TORN_FIRE, torn=True), O.REFUSE),
)

#: Anti-vacuity: a silently shrinking table must not pass.
assert len(FAULT_CASES) == 11, "the fault matrix has exactly eleven required faults"

RETRYABLE = (K.DOWNSTREAM_TIMEOUT, K.EVIDENCE_SINK_UNAVAILABLE)


def test_the_eleven_to_one_matrix() -> None:
    """Every one of the eleven faults maps to exactly the required outcome."""
    mismatches: list[str] = []
    for number, obs, expected in FAULT_CASES:
        got = classify(obs).outcome
        if got is not expected:
            mismatches.append(
                f"fault {number} ({obs.kind.value}): expected {expected.value}, got {got.value}"
            )
    assert not mismatches, "fault matrix violations:\n  " + "\n  ".join(mismatches)

    # every case in the table is a distinct fault, and the table covers the enum
    assert {obs.kind for _, obs, _ in FAULT_CASES} == set(FaultKind)


def test_every_fault_kind_has_a_classification() -> None:
    """Adding a ``FaultKind`` without classifying it fails loudly, not silently.

    ``classify`` has no permissive default: an unenumerated member reaches the
    ``case _`` and raises. This test drives every member through it so the
    failure surfaces here rather than in production as a stray ``continue``.
    """
    unclassified: list[str] = []
    for kind in FaultKind:
        try:
            result = classify(FaultObservation(kind))
        except Exception as exc:  # noqa: BLE001 - the point is to name it
            unclassified.append(f"{kind.value}: raised {type(exc).__name__}: {exc}")
            continue
        if not isinstance(result.outcome, FaultOutcome):
            unclassified.append(f"{kind.value}: returned non-outcome {result.outcome!r}")
        if result.kind is not kind:
            unclassified.append(f"{kind.value}: verdict carries kind {result.kind.value}")
    assert not unclassified, "unclassified FaultKind members:\n  " + "\n  ".join(unclassified)


def test_classification_is_pure_and_deterministic() -> None:
    """Same input, same outcome — every time, and with no observable I/O."""
    drift: list[str] = []
    for number, obs, _ in FAULT_CASES:
        first = classify(obs)
        for _ in range(5):
            again = classify(obs)
            if (again.outcome, again.reason, again.refusal_code) != (
                first.outcome,
                first.reason,
                first.refusal_code,
            ):
                drift.append(f"fault {number} ({obs.kind.value}) is not deterministic")
                break
        # a rebuilt-but-equal observation must classify identically too
        clone = FaultObservation(**{f: getattr(obs, f) for f in obs.__slots__})
        if classify(clone).outcome is not first.outcome:
            drift.append(f"fault {number} ({obs.kind.value}) depends on identity, not value")
    assert not drift, "determinism violations:\n  " + "\n  ".join(drift)


# ── fault 11: torn fire — the one the happy path never exercises ────────────


def test_fault_11_torn_ledger_refuses_resume_by_name() -> None:
    """A real torn ledger: INTENDED written, never committed, then resume.

    The session must refuse by name. It must never guess: assume it committed
    and an action is lost; assume it did not and the action double-fires.
    """
    from autofde_lab.hub.domain.maze import Maze

    from autofde_lab.agent.session import AgentSession

    torn = OccurrenceLedger()
    torn.intend((0,), "ctx-before-crash", activity_sha256="a" * 64, detail="PRE_ACT")
    # crash happens exactly here — no commit() is ever reached

    # 1. the ledger itself knows it is unresumable
    assert torn.is_resumable() is False
    assert [r.phase.value for r in torn.records()] == ["INTENDED"]
    assert torn.committed() == ()

    # 2. the fault matrix derives the fault from that real state
    obs = observe_torn_fire(torn)
    assert obs is not None, "a torn ledger must produce a TORN_FIRE observation"
    verdict = classify(obs)
    assert verdict.outcome is O.REFUSE
    assert verdict.refusal_code is AgentRefusalCode.LEDGER_UNRESUMABLE
    assert verdict.outcome is not O.CONTINUE  # no silent continue. ever.

    # 3. and resuming a session on it refuses by name, not by exception type alone
    with pytest.raises(AgentRefusal) as excinfo:
        AgentSession(Maze(), ledger=OccurrenceLedger.from_records(torn.records()))
    assert excinfo.value.code is AgentRefusalCode.LEDGER_UNRESUMABLE
    assert "SKD-AGENT-006" in str(excinfo.value)


def test_fault_11_control_a_committed_ledger_is_not_torn() -> None:
    """The refusal is conditional on real torn state, not unconditional."""
    resolved = OccurrenceLedger()
    token = resolved.intend((0,), "ctx", activity_sha256="a" * 64)
    resolved.commit(token, activity_sha256="a" * 64)

    assert resolved.is_resumable() is True
    assert observe_torn_fire(resolved) is None, "a complete ledger must report no fault"
    resolved.assert_resumable()  # does not raise


# ── fault 10: same content, different meaning ───────────────────────────────


def test_fault_10_identical_activity_different_context_are_two_occurrences() -> None:
    """``activity_sha256`` cannot separate them; only ``context_sha256`` can.

    This is the case that passes in testing and fails in production, on exactly
    the replan that motivated context-keyed occurrences.
    """
    activity = "f" * 64
    before = OccurrenceKey(activity, 0, "world-state-before-expansion")
    after = OccurrenceKey(activity, 0, "world-state-after-expansion")

    # identical in every respect the label-based view can see
    assert before.activity_sha256 == after.activity_sha256
    assert before.occurrence_index == after.occurrence_index
    # yet NOT the same occurrence
    assert before != after
    assert len({before, after}) == 2, "context divergence must not collapse in a set"

    verdict = classify(observe_label_context_collision(before, after))
    assert verdict.outcome is O.REPLAN
    assert verdict.outcome is not O.CONTINUE
    assert verdict.mechanism_backed is True


def test_fault_10_control_same_context_really_is_one_occurrence() -> None:
    """The split is driven by context, not by being asked twice."""
    activity = "f" * 64
    same = OccurrenceKey(activity, 0, "one-world-state")
    twin = OccurrenceKey(activity, 0, "one-world-state")

    assert same == twin and len({same, twin}) == 1
    assert classify(observe_label_context_collision(same, twin)).outcome is O.CONTINUE


# ── fault 1: duplicate is only benign with evidence ─────────────────────────


def test_fault_1_continue_requires_committed_evidence() -> None:
    """``continue`` is reachable only when the ledger already holds the key."""
    ledger = OccurrenceLedger()
    token = ledger.intend((0,), "ctx", activity_sha256="b" * 64)
    key = ledger.commit(token, activity_sha256="b" * 64)

    committed = ledger.occurrences()
    assert classify(observe_duplicate_observation(committed, key)).outcome is O.CONTINUE

    unseen = OccurrenceKey("c" * 64, 0, "ctx")
    verdict = classify(observe_duplicate_observation(committed, unseen))
    assert verdict.outcome is O.UNKNOWN, "an unsupported duplicate claim is not benign"
    assert verdict.outcome is not O.CONTINUE


# ── bounded retry is bounded ────────────────────────────────────────────────


def test_retry_within_bound_is_refused_once_exhausted() -> None:
    """``retry_within_bound`` carries its bound and stops at it."""
    problems: list[str] = []
    for kind in RETRYABLE:
        for attempt in (1, 2):
            got = classify(FaultObservation(kind, attempt=attempt, retry_bound=3)).outcome
            if got is not O.RETRY_WITHIN_BOUND:
                problems.append(f"{kind.value} attempt {attempt}/3: got {got.value}")
        for attempt in (3, 4, 99):
            verdict = classify(FaultObservation(kind, attempt=attempt, retry_bound=3))
            if verdict.outcome is not O.REFUSE:
                problems.append(
                    f"{kind.value} attempt {attempt}/3: expected refuse, got {verdict.outcome.value}"
                )
            elif verdict.refusal_code is not AgentRefusalCode.BOUND_EXHAUSTED:
                problems.append(f"{kind.value} attempt {attempt}/3: wrong refusal code")
        # a bound of 1 means: do not retry at all
        if classify(FaultObservation(kind, attempt=1, retry_bound=1)).outcome is not O.REFUSE:
            problems.append(f"{kind.value}: retry_bound=1 must not permit a retry")
    assert not problems, "unbounded-retry violations:\n  " + "\n  ".join(problems)


def test_unknown_is_reachable_and_never_means_probably_fine() -> None:
    """``unknown`` is a real outcome, and no fault silently continues."""
    unknowns = {c.kind for _, obs, _ in FAULT_CASES if (c := classify(obs)).outcome is O.UNKNOWN}
    assert K.POSTCONDITION_UNCONFIRMED in unknowns, "unknown must be reachable"

    # `continue` is reachable by exactly one fault, and only with evidence
    continues = {obs.kind for _, obs, exp in FAULT_CASES if exp is O.CONTINUE}
    assert continues == {K.DUPLICATE_OBSERVATION}

    # and no fault classified with *no* supporting field defaults to continue
    lax = [k.value for k in FaultKind if classify(FaultObservation(k)).outcome is O.CONTINUE]
    assert lax == [], f"faults defaulting to continue on an empty observation: {lax}"


def test_mechanism_boundary_is_declared_not_blurred() -> None:
    """The honest split: which faults have logic, which are a table entry.

    Blurring this would make the deliverable worse than not having it — a
    declared mapping read as a working mechanism is exactly the overclaim the
    matrix exists to prevent.
    """
    backed = {k for k in FaultKind if classify(FaultObservation(k)).mechanism_backed}
    assert backed == set(FaultKind) - DECLARED_MAPPING_ONLY
    assert backed == {
        K.DUPLICATE_OBSERVATION,
        K.LABEL_CONTEXT_COLLISION,
        K.TORN_FIRE,
        K.DOWNSTREAM_TIMEOUT,
        K.EVIDENCE_SINK_UNAVAILABLE,
    }
    assert len(DECLARED_MAPPING_ONLY) == 6
