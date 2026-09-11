# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Drives real, sqlite/OCEL-sourced exploration candidates all the way
through a real gymact-mediated experiment into a real PSRO step.

This module is pure composition of already-real functions -- no new core
evidence/scoring logic is introduced here, only orchestration:

1. `process_informed_exploration.process_informed_hypotheses` -- real
   sqlite/OCEL evidence -> real `tuple[DesiredStateHypothesis, ...]`.
2. A caller-supplied `candidate_generator` -- hypotheses -> real
   `ArchitectureCandidate`s. Deliberately generic over which real
   exploration generator produces them (`generate_triz_candidates`/
   `generate_doe_candidates`/`generate_montecarlo_candidates`, or any
   future one) -- see "Why generic, not TRIZ-specific" below.
3. `exploration_gymact_falsification.falsify_exploration_candidate_via_gymact`
   -- each real candidate -> a real gymact-mediated experiment (materialize/
   act/verify/teardown) -> a real `FalsificationResult`.
4. `exploration_psro_loop.run_exploration_psro_round` -- the real
   `(candidate, falsification)` pairs -> a real `PayoffHypergraph` +
   `PolicySpaceResponseOracle.step()`.

Every real object each stage produces flows unmodified into the next; this
module coerces, re-derives, or fabricates nothing along the way.

Why generic, not TRIZ-specific
-------------------------------
The first version of this module (`run_process_informed_triz_psro_round`,
this session's own prior pass) hardcoded `generate_triz_candidates` and a
`TRIZContradiction` parameter. A later pass's own real caller-count sweep
(`grep -rln "generate_doe_candidates|generate_montecarlo_candidates"
tests/reasoning/test_exploration_gymact_falsification_chicago.py
tests/reasoning/test_exploration_psro_loop_chicago.py`) found DOE already
covered in both, but **Monte Carlo covered in neither** -- Monte Carlo
candidates had real coverage only in `exploration_payoff_bridge.py`'s own
unit test (hand-built `ExperimentReceipt` fixtures), never through a real
gymact-mediated experiment or a real PSRO step, and never through this
pipeline. Rather than hand-copy the TRIZ-specific function into a
near-identical `run_process_informed_montecarlo_psro_round` (the exact
low-novelty duplication this pass was explicitly told to avoid), this
module generalizes the one real difference between the three call sites
(which generator, with which generator-specific parameters, turns
hypotheses into candidates) behind a single `candidate_generator` callable
parameter -- removing the TRIZ-only coupling entirely rather than adding a
second copy of it. `run_process_informed_triz_psro_round`'s only real
caller (its own test file, confirmed via `grep -rln
"run_process_informed_triz_psro_round" src/ tests/` before this refactor)
was updated in the same commit to call the new generic function with a
real `lambda hypotheses: generate_triz_candidates(hypotheses,
contradiction)` -- zero behavior change for the TRIZ path, confirmed by
re-running its own existing assertions unmodified.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .exploration_gymact_falsification import falsify_exploration_candidate_via_gymact
from .exploration_psro_loop import ExplorationPsroRoundOutcome, run_exploration_psro_round
from .laboratory import (
    ArchitectureCandidate,
    DesiredStateHypothesis,
    EnterpriseObservation,
    FalsificationResult,
    WorldExperimentProvider,
)
from .process_informed_exploration import process_informed_hypotheses

__all__ = ["run_process_informed_exploration_psro_round"]

CandidateGenerator = Callable[[tuple[DesiredStateHypothesis, ...]], tuple[ArchitectureCandidate, ...]]


def run_process_informed_exploration_psro_round(
    metadata: object,
    *,
    db_path: str,
    observation: EnterpriseObservation,
    candidate_generator: CandidateGenerator,
    league: Any,
    domain: Any,
    constructor_planner_ids: Sequence[str],
    falsifier_planner_id: str,
    world_id: str = "generic_enterprise",
    target_world_ref: str = "generic_enterprise",
    gymact_provider: WorldExperimentProvider | None = None,
) -> ExplorationPsroRoundOutcome:
    """Real, four-stage pipeline: real sqlite/OCEL evidence -> real
    exploration candidates (via `candidate_generator`) -> real
    gymact-mediated falsification (one independent experiment per
    candidate) -> a real PSRO step over the resulting real payoff evidence.

    `db_path`/`observation` are the same real arguments
    `process_informed_hypotheses` already takes -- an already-written real
    sqlite db and the real `EnterpriseObservation` it describes.
    `candidate_generator` receives the real `tuple[DesiredStateHypothesis,
    ...]` `process_informed_hypotheses` returns and must return a real
    `tuple[ArchitectureCandidate, ...]` -- typically a thin real closure
    over `generate_triz_candidates`/`generate_doe_candidates`/
    `generate_montecarlo_candidates` and that generator's own
    generator-specific parameters (a `TRIZContradiction`, DOE's
    `cost_levels`/`authority_levels`, or Monte Carlo's `cost_model`/`n`).
    `league`/`domain`/`constructor_planner_ids`/`falsifier_planner_id`/
    `world_id` are the same real arguments `exploration_psro_loop.
    run_exploration_psro_round` already takes. `gymact_provider` defaults
    to `None`, meaning `falsify_exploration_candidate_via_gymact`'s own
    default: a fresh, fail-closed `GymActWorldExperimentProvider()`.

    Each real candidate's `initial_state_evidence_ref` is `db_path` itself
    -- the real sqlite file the candidate's own generating hypothesis was
    actually observed from, never a fabricated reference.
    """
    hypotheses = process_informed_hypotheses(metadata, db_path=db_path, observation=observation)
    candidates: tuple[ArchitectureCandidate, ...] = candidate_generator(hypotheses)

    candidates_and_falsifications: list[tuple[ArchitectureCandidate, FalsificationResult]] = []
    for candidate in candidates:
        outcome = falsify_exploration_candidate_via_gymact(
            candidate,
            target_world_ref=target_world_ref,
            initial_state_evidence_ref=str(db_path),
            provider=gymact_provider,
        )
        candidates_and_falsifications.append((candidate, outcome.falsification))

    return run_exploration_psro_round(
        candidates_and_falsifications,
        league=league,
        domain=domain,
        world_id=world_id,
        constructor_planner_ids=constructor_planner_ids,
        falsifier_planner_id=falsifier_planner_id,
    )
