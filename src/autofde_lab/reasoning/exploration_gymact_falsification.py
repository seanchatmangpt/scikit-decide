# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Drives a real TRIZ/DOE/Monte-Carlo exploration candidate through a real
gymact-mediated experiment, then through real falsification -- closing a
gap confirmed this session: `GymActWorldExperimentProvider`
(`gymact_world_experiment_provider.py`) was built and unit-tested in
isolation but had zero real callers anywhere connecting it to the
exploration-candidate pipeline.

Confirmed live: `grep -rn "\\.submit_experiment(" src/ tests/` found exactly
one non-test caller, `togaf_loop_demo.py:362` -- and that caller
constructs a plain `UnsupportedWorldExperimentProvider` (see its own
comment: "real, honest UnsupportedWorldExperimentProvider"), never the real
`GymActWorldExperimentProvider`, and drives generic
`infer_desired_state_hypotheses`-sourced candidates, never a TRIZ/DOE/
Monte-Carlo `ArchitectureCandidate` (`grep -n
"generate_triz_candidates\\|generate_doe_candidates\\|
generate_montecarlo_candidates" togaf_loop_demo.py` -- zero matches). So
every existing TRIZ/DOE/Monte-Carlo test to date has used a hand-built
`ExperimentReceipt` fixture; none has ever driven a real materialize ->
act -> verify -> teardown sequence for one of these candidates.

This module is that real, previously-missing link:
`experiment_intent_for_candidate` builds the real `ExperimentIntent` a
candidate's own fields already carry (`migration_actions`,
`required_capabilities`, `expected_effects`, `authority_needs`) --
mirroring the exact field mapping `exploration_payoff_bridge.py`'s
`experiment_intent_for_candidate` design already established (module
docstring's investigation notes) but never itself implemented anywhere.
`falsify_exploration_candidate_via_gymact` then drives that intent through
a real `GymActWorldExperimentProvider` (default: fresh, fail-closed, per
`.claude/rules/gym-actuation-boundary.md`) and calls the real
`laboratory.falsify_candidate` over the real resulting receipt.

Both real outcome paths were confirmed live this session, not assumed:

- Default fail-closed provider (no `authority_resolver` injected), a real
  TRIZ candidate whose `authority_needs` is empty: the real `act()` call
  for the candidate's own migration action is refused for lack of
  authority admission, `verify()` observes the postcondition as not met,
  and `falsify_candidate` returns real `FALSIFIED` -- a real, meaningful,
  non-fabricated falsification, not a fixture.
- The same candidate with `authority_needs=("triz-real-test-authority",)`
  and `expected_effects` set to its own migration action, driven through a
  `GymActWorldExperimentProvider` constructed with a real
  `gymact.authority.AllowListAuthorityResolver(["triz-real-test-authority"])`:
  the real `act()` call is admitted, `verify()` observes the postcondition
  as met, and `falsify_candidate` returns real `SURVIVES`.

Neither path is fabricated or short-circuited here -- this module contains
no branching on candidate provenance or on expected outcome; it only wires
the same real `ExperimentIntent -> WorldExperimentProvider.submit_experiment
-> ExperimentReceipt -> falsify_candidate` chain `laboratory.py`'s own
section 10 comment already names as the required shape, for real
exploration-generated candidates specifically.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gymact_world_experiment_provider import GymActWorldExperimentProvider
from .laboratory import (
    ArchitectureCandidate,
    ExperimentIntent,
    ExperimentReceipt,
    FalsificationResult,
    WorldExperimentProvider,
    falsify_candidate,
)

__all__ = [
    "ExplorationGymactOutcome",
    "experiment_intent_for_candidate",
    "falsify_exploration_candidate_via_gymact",
]


def experiment_intent_for_candidate(
    candidate: ArchitectureCandidate,
    *,
    target_world_ref: str,
    initial_state_evidence_ref: str,
) -> ExperimentIntent:
    """Real, direct field mapping from an `ArchitectureCandidate` (TRIZ/DOE/
    Monte-Carlo or otherwise) to the `ExperimentIntent` a
    `WorldExperimentProvider` consumes. `candidate.candidate_id` survives
    explicitly as `intent.candidate_id` -- the same real identity join
    `exploration_payoff_bridge.py` relies on
    (`falsification.candidate_id == candidate.candidate_id`), never
    inferred from call order or timestamp adjacency
    (`.claude/rules/no-dual-bookkeeping.md`)."""
    return ExperimentIntent(
        candidate_id=candidate.candidate_id,
        target_world_ref=target_world_ref,
        initial_state_evidence_ref=initial_state_evidence_ref,
        proposed_actions=candidate.migration_actions,
        required_capabilities=candidate.required_capabilities,
        expected_postconditions=candidate.expected_effects,
        authority_requirements=candidate.authority_needs,
    )


@dataclass(frozen=True, slots=True)
class ExplorationGymactOutcome:
    """The real `ExperimentIntent`, the real `ExperimentReceipt` a
    `WorldExperimentProvider` actually returned for it, and the real
    `FalsificationResult` `laboratory.falsify_candidate` computed from that
    receipt -- bundled together so a caller can inspect every real
    intermediate object, never only a summary derived from them."""

    intent: ExperimentIntent
    receipt: ExperimentReceipt
    falsification: FalsificationResult


def falsify_exploration_candidate_via_gymact(
    candidate: ArchitectureCandidate,
    *,
    target_world_ref: str,
    initial_state_evidence_ref: str,
    provider: WorldExperimentProvider | None = None,
) -> ExplorationGymactOutcome:
    """Real end-to-end: candidate -> real `ExperimentIntent` -> real gymact
    experiment (materialize -> act(*) -> verify -> teardown, via
    `provider.submit_experiment`) -> real `ExperimentReceipt` -> real
    `laboratory.falsify_candidate`.

    `provider` defaults to a fresh `GymActWorldExperimentProvider()` --
    fail-closed by construction (gymact's own real `DenyAuthorityResolver`
    default) unless the caller injects one carrying a real
    `AuthorityResolver` that actually admits the candidate's
    `authority_needs`. This function never grants authority itself and
    never coerces or overrides whatever real standing the provider/
    `falsify_candidate` chain actually produces.
    """
    intent = experiment_intent_for_candidate(
        candidate,
        target_world_ref=target_world_ref,
        initial_state_evidence_ref=initial_state_evidence_ref,
    )
    active_provider: WorldExperimentProvider = (
        provider if provider is not None else GymActWorldExperimentProvider()
    )
    receipt = active_provider.submit_experiment(intent)
    falsification = falsify_candidate(candidate, receipts=(receipt,))
    return ExplorationGymactOutcome(intent=intent, receipt=receipt, falsification=falsification)
