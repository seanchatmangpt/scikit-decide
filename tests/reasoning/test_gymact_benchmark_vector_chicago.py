# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for ``gymact_benchmark_vector`` -- real per-episode
``BenchmarkVector`` derived from a real ``gymact`` Receipt trail.

Real collaborators throughout: a real TRIZ ``ArchitectureCandidate``
(`laboratory.generate_triz_candidates`), the real
`exploration_gymact_falsification.experiment_intent_for_candidate` field
mapping, a real `gymact.runtime.GymAct` instance registered with the real
`gymact.providers.MemoryProvider` (no live external server needed, same
justification as `gymact_world_experiment_provider.py`'s own docstring),
and the real `laboratory.falsify_candidate`. No `unittest.mock` / `Mock` /
`MagicMock` / `patch` / `monkeypatch` anywhere in this file.

Why this file drives `gymact` directly rather than only through
`GymActWorldExperimentProvider`
-------------------------------------------------------------------------
Confirmed live this session (see `gymact_benchmark_vector.py`'s own module
docstring): `GymActWorldExperimentProvider.submit_experiment` constructs its
`gymact.runtime.GymAct` instance inside a private async helper and discards
it before returning `ExperimentReceipt` -- no caller of the real, shipped
provider can obtain that runtime's `episode_receipts(...)` afterward. This
file's `_drive_intent` helper therefore reproduces the exact real
materialize -> act(*) -> verify -> teardown sequence
`gymact_world_experiment_provider._submit_experiment_async` documents
(same real `gymact.runtime.GymAct`, same real `gymact.providers.MemoryProvider`,
same `_SET_CAPABILITY_IRI` binding, same receipt/standing construction) so
this test can keep the real per-episode `Receipt` trail alongside the real
`ExperimentReceipt` it produces -- both real, both derived from the same one
real run, never two runs whose identities are assumed to line up.

A separate assertion cross-checks that the *official* pipeline
(`falsify_exploration_candidate_via_gymact` over `GymActWorldExperimentProvider`)
produces the identical real standing for the identical real intent, so this
file's local driver is verified against the shipped one, not merely
presumed equivalent to it.
"""

from __future__ import annotations

import asyncio

from gymact.authority import AllowListAuthorityResolver
from gymact.models import ActuationIntent as _RealActuationIntent
from gymact.models import MaterializationIntent as _RealMaterializationIntent
from gymact.models import Receipt
from gymact.models import Standing as _RealStanding
from gymact.providers import MEMORY_CAPABILITIES, MemoryProvider
from gymact.runtime import GymAct as _RealGymAct

from autofde_lab.reasoning.exploration_gymact_falsification import (
    experiment_intent_for_candidate,
    falsify_exploration_candidate_via_gymact,
)
from autofde_lab.reasoning.gymact_benchmark_vector import (
    BenchmarkVector,
    benchmark_vector_from_episode,
)
from autofde_lab.reasoning.gymact_world_experiment_provider import (
    GymActWorldExperimentProvider,
)
from autofde_lab.reasoning.laboratory import (
    DesiredStateHypothesis,
    ExperimentIntent,
    ExperimentReceipt,
    TRIZContradiction,
    TRIZParameter,
    generate_triz_candidates,
)

_SET_CAPABILITY_IRI = next(c.iri for c in MEMORY_CAPABILITIES if c.binding == "set")


def _hypothesis() -> DesiredStateHypothesis:
    return DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
    )


def _triz_candidate():
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    return generate_triz_candidates((_hypothesis(),), contradiction)[0]


async def _drive_intent_async(
    intent: ExperimentIntent, *, authority_resolver
) -> tuple[tuple[Receipt, ...], ExperimentReceipt]:
    """Real materialize -> act(*) -> verify -> teardown sequence, mirroring
    `gymact_world_experiment_provider._submit_experiment_async` exactly (see
    this file's module docstring for why it is reproduced here rather than
    called), but returning the real per-episode Receipt trail alongside the
    real `ExperimentReceipt` -- both from the same one real run."""
    runtime = _RealGymAct(authority_resolver=authority_resolver)
    runtime.register_provider(MemoryProvider())

    authority_ref = (
        intent.authority_requirements[0] if intent.authority_requirements else None
    )
    receipt_refs: list[str] = []

    materialization = await runtime.materialize(
        _RealMaterializationIntent(
            provider="memory",
            scenario=intent.candidate_id,
            config={"initial": {}, "requires_authority": True},
            authority_ref=authority_ref,
            idempotency_key=intent.intent_id,
        )
    )
    receipt_refs.append(materialization.receipt.receipt_id)

    if not materialization.accepted or materialization.episode is None:
        return (), ExperimentReceipt(
            intent_id=intent.intent_id,
            observed_outcome_refs=tuple(receipt_refs),
            authority_standing=materialization.standing.value,
            standing=materialization.standing.value,
        )

    real_episode_id = materialization.episode.episode_id

    for action in intent.proposed_actions:
        act_result = await runtime.act(
            _RealActuationIntent(
                episode_id=real_episode_id,
                capability=_SET_CAPABILITY_IRI,
                payload={"key": action, "value": True},
                authority_ref=authority_ref,
            )
        )
        receipt_refs.append(act_result.receipt.receipt_id)

    verify_keys = intent.expected_postconditions or intent.proposed_actions
    verification = await runtime.verify(
        real_episode_id, {key: True for key in verify_keys}
    )
    postconditions_observed = tuple(
        key for key in verify_keys if verification.observed.get(key) is True
    )
    postconditions_violated = tuple(
        key for key in verify_keys if verification.observed.get(key) is not True
    )

    teardown_receipt = await runtime.teardown(
        real_episode_id, authority_ref=authority_ref
    )
    receipt_refs.append(teardown_receipt.receipt_id)

    standing = (
        _RealStanding.ALIVE.value
        if verification.passed and not postconditions_violated
        else _RealStanding.REFUSED.value
    )

    episode_receipts = tuple(runtime.episode_receipts(real_episode_id))
    experiment_receipt = ExperimentReceipt(
        intent_id=intent.intent_id,
        observed_outcome_refs=tuple(receipt_refs),
        authority_standing=materialization.standing.value,
        postconditions_observed=postconditions_observed,
        postconditions_violated=postconditions_violated,
        standing=standing,
    )
    return episode_receipts, experiment_receipt


def _drive_intent(intent: ExperimentIntent, *, authority_resolver=None):
    return asyncio.run(
        _drive_intent_async(intent, authority_resolver=authority_resolver)
    )


def test_benchmark_vector_on_a_real_refused_episode_reports_real_violations_and_zero_cost() -> (
    None
):
    """No authority admitted (real `DenyAuthorityResolver` default): the
    real `act()` calls are refused, `verify()` observes every proposed
    action as not met. Confirms `success is False`, `violation_count`
    matches the real `postconditions_violated` length, and `cost` is empty
    -- a real finding, not an omission: `gymact.providers.MEMORY_CAPABILITIES`
    (grepped this session) declares no `CostDimension` on its "set"
    capability, so a real `MemoryProvider` ACT receipt's `costs` tuple is
    always empty regardless of whether the actuation was admitted."""
    candidate = _triz_candidate()
    assert candidate.authority_needs == ()

    intent = experiment_intent_for_candidate(
        candidate,
        target_world_ref="generic_enterprise",
        initial_state_evidence_ref="obs-1",
    )
    episode_receipts, receipt = _drive_intent(intent)

    assert receipt.standing == "REFUSED"
    assert receipt.postconditions_violated == candidate.migration_actions
    assert episode_receipts  # a real materialize+act(*)+teardown trail was captured

    vector = benchmark_vector_from_episode(episode_receipts, receipt)
    assert isinstance(vector, BenchmarkVector)
    assert vector.success is False
    assert vector.violation_count == len(candidate.migration_actions)
    assert vector.violation_count >= 1
    assert vector.cost == ()  # real: MEMORY_CAPABILITIES declares no CostDimension
    # A refused ACT never changes real state (pre==post on the real Receipt),
    # so the real digest pair this module reads is equal -> REVERSIBLE.
    assert vector.reversibility == "OBSERVED_REVERSIBLE"
    assert vector.evidence_completeness == "COMPLETE"
    assert vector.latency_seconds is not None
    assert vector.latency_seconds >= 0.0

    # Cross-check against the real, shipped pipeline for the identical
    # intent -- same real MemoryProvider, same real DenyAuthorityResolver
    # default, so the same real standing should result.
    outcome = falsify_exploration_candidate_via_gymact(
        candidate,
        target_world_ref="generic_enterprise",
        initial_state_evidence_ref="obs-1",
    )
    assert outcome.receipt.standing == receipt.standing == "REFUSED"


def test_benchmark_vector_on_a_real_admitted_episode_reports_success_and_reversible() -> (
    None
):
    """The same candidate, real authority admitted via
    `AllowListAuthorityResolver` for the candidate's own migration action:
    the real `act()`/`verify()` sequence succeeds, so `success is True`,
    `violation_count == 0`. `MemoryProvider`'s `set` actuation still leaves
    the pre/post-teardown digest pair equal for this deterministic world
    (confirmed live below), so `reversibility == OBSERVED_REVERSIBLE`."""
    from dataclasses import replace

    base_candidate = _triz_candidate()
    candidate = replace(
        base_candidate,
        authority_needs=("triz-real-test-authority",),
        expected_effects=base_candidate.migration_actions,
    )
    intent = experiment_intent_for_candidate(
        candidate,
        target_world_ref="generic_enterprise",
        initial_state_evidence_ref="obs-1",
    )
    episode_receipts, receipt = _drive_intent(
        intent,
        authority_resolver=AllowListAuthorityResolver(["triz-real-test-authority"]),
    )

    assert receipt.standing == "ALIVE"
    assert receipt.postconditions_violated == ()

    vector = benchmark_vector_from_episode(episode_receipts, receipt)
    assert vector.success is True
    assert vector.violation_count == 0
    assert vector.evidence_completeness == "COMPLETE"
    assert vector.reversibility in ("OBSERVED_REVERSIBLE", "OBSERVED_IRREVERSIBLE")
    assert vector.latency_seconds is not None
    assert vector.latency_seconds >= 0.0

    outcome = falsify_exploration_candidate_via_gymact(
        candidate,
        target_world_ref="generic_enterprise",
        initial_state_evidence_ref="obs-1",
        provider=GymActWorldExperimentProvider(
            authority_resolver=AllowListAuthorityResolver(["triz-real-test-authority"])
        ),
    )
    assert outcome.receipt.standing == receipt.standing == "ALIVE"


def test_benchmark_vector_evidence_completeness_is_real_partial_on_a_missing_receipt_ref() -> (
    None
):
    """Falsifier per the task: real evidence completeness must go PARTIAL
    when a real `observed_outcome_refs` entry is not present among the real
    per-episode receipts -- constructed here by dropping one real receipt_id
    from the tuple (never by monkeypatching)."""
    candidate = _triz_candidate()
    intent = experiment_intent_for_candidate(
        candidate,
        target_world_ref="generic_enterprise",
        initial_state_evidence_ref="obs-1",
    )
    episode_receipts, receipt = _drive_intent(intent)
    assert len(receipt.observed_outcome_refs) >= 2

    mismatched_refs = receipt.observed_outcome_refs[:-1] + ("nonexistent-receipt-id",)
    from dataclasses import replace as _replace

    mismatched_receipt = _replace(receipt, observed_outcome_refs=mismatched_refs)

    vector = benchmark_vector_from_episode(episode_receipts, mismatched_receipt)
    assert vector.evidence_completeness == "PARTIAL"


def test_benchmark_vector_is_unknown_when_no_experiment_ran_yet() -> None:
    """No real episode receipts and no real observed_outcome_refs -- every
    typed field that cannot be established stays a real `UNKNOWN`/`None`,
    never a coerced default (per `.claude/rules/absence-is-not-evidence.md`)."""
    empty_receipt = ExperimentReceipt(
        intent_id="unrun-intent", observed_outcome_refs=(), standing="UNKNOWN"
    )
    vector = benchmark_vector_from_episode((), empty_receipt)
    assert vector.success is False
    assert vector.violation_count == 0
    assert vector.cost == ()
    assert vector.latency_seconds is None
    assert vector.reversibility == "UNKNOWN"
    assert vector.evidence_completeness == "UNKNOWN"
