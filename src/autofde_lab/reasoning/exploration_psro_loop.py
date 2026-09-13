# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Drives PSRO end-to-end from real exploration-candidate falsification
evidence.

Closes a real gap confirmed 2026-08-21: `planner_league.psro.
PolicySpaceResponseOracle` had zero real callers anywhere in this repo
(`grep -rln "PsroState(" src/ tests/` returned only `psro.py` itself) --
built and unit-tested in isolation, never actually driven end-to-end from a
real `PayoffHypergraph` populated by real, exploration-bridge-admitted
`PayoffObservation`s.

This module is that real driver. It takes a batch of exploration candidates
(TRIZ/DOE/Monte-Carlo `ArchitectureCandidate`s from `laboratory.py` sections
14-16) plus their real `FalsificationResult`s (from `laboratory.
falsify_candidate`, over real `ExperimentReceipt`s), admits each one's
payoff via `exploration_payoff_bridge.admit_exploration_candidate_payoff`
into a real `PayoffHypergraph`, seeds a real `PsroState` over a fixed
opponent (falsifier) population, and runs one real
`planner_league.psro.PolicySpaceResponseOracle.step()` -- returning the
real advance/refusal outcome exactly as those real objects computed it,
never a fabricated or re-derived summary of it
(`.claude/rules/no-dual-bookkeeping.md`).

`PolicySpaceResponseOracle.step()`'s own real
`empirical_best_response` skips (never blocks on) a candidate missing
complete opponent coverage -- it only refuses
(`REFUSED:PSRO_MISSING_PAYOFF_CLOSURE`) when *no* candidate has complete
coverage. This module changes nothing about that contract; it only supplies
the real admitted edges that contract consumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from autofde_lab.planner_league import PayoffHypergraph, PlannerLeague
from autofde_lab.planner_league.psro import PolicySpaceResponseOracle, PsroState, PsroStep

from .exploration_payoff_bridge import (
    ExplorationPayoffOutcome,
    admit_exploration_candidate_payoff,
)
from .laboratory import ArchitectureCandidate, FalsificationResult

__all__ = ["ExplorationPsroRoundOutcome", "run_exploration_psro_round"]


@dataclass(frozen=True, slots=True)
class ExplorationPsroRoundOutcome:
    """Real, typed result of one exploration-to-PSRO round: every real
    payoff-admission attempt made along the way (`admissions`), the real
    `PayoffHypergraph` those admissions mutated, and the real
    `PolicySpaceResponseOracle.step()` result computed from whatever ended
    up admitted. `psro_step.advanced` / `psro_step.receipt` are the real
    objects `psro.py` itself defines -- this dataclass never re-derives or
    duplicates their semantics, only bundles them with the admission trail
    that produced them."""

    admissions: tuple[ExplorationPayoffOutcome, ...]
    hypergraph: PayoffHypergraph
    psro_step: PsroStep

    @property
    def admitted_count(self) -> int:
        """How many of `admissions` actually mutated `hypergraph`."""
        return sum(1 for outcome in self.admissions if outcome.admitted)


def run_exploration_psro_round(
    candidates_and_falsifications: Sequence[tuple[ArchitectureCandidate, FalsificationResult]],
    *,
    league: PlannerLeague,
    domain: Any,
    world_id: str,
    constructor_planner_ids: Sequence[str],
    falsifier_planner_id: str,
    role_id: str = "plan_constructor",
    opponent_role_id: str = "plan_falsifier",
    observation_projection_id: str = "full_observation",
    budget_id: str = "balanced",
) -> ExplorationPsroRoundOutcome:
    """Admit every `(candidate, falsification)` pair's real payoff, once per
    real `constructor_planner_ids` entry, against the single real
    `falsifier_planner_id` opponent -- then run one real PSRO `step()`
    computing the empirical best-response constructor over that opponent.

    Each admission attempt goes through
    `admit_exploration_candidate_payoff` unmodified: an incompatible
    planner, an unscoreable `FalsificationStanding`, a candidate/
    falsification identity mismatch, or missing receipt evidence produces a
    real, named refusal in `admissions` and never mutates `hypergraph` --
    this function does not retry, coerce, or silently drop those refusals,
    it only collects them alongside whatever did get admitted.

    Never fabricates a PSRO advance: if zero admitted edges give any
    candidate complete coverage against the opponent mixture, the real
    `PolicySpaceResponseOracle.step()` returns its own real
    `REFUSED:PSRO_MISSING_PAYOFF_CLOSURE` standing, returned here
    unmodified as `psro_step`.
    """
    if not constructor_planner_ids:
        raise ValueError("REFUSED:NO_CONSTRUCTOR_CANDIDATES")

    hypergraph = PayoffHypergraph()
    admissions: list[ExplorationPayoffOutcome] = []
    for candidate, falsification in candidates_and_falsifications:
        for constructor_planner_id in constructor_planner_ids:
            outcome = admit_exploration_candidate_payoff(
                candidate,
                falsification,
                league=league,
                domain=domain,
                hypergraph=hypergraph,
                world_id=world_id,
                constructor_planner_id=constructor_planner_id,
                falsifier_planner_id=falsifier_planner_id,
                role_id=role_id,
                opponent_role_id=opponent_role_id,
                observation_projection_id=observation_projection_id,
                budget_id=budget_id,
            )
            admissions.append(outcome)

    state = PsroState.seed([falsifier_planner_id])
    oracle = PolicySpaceResponseOracle(
        hypergraph,
        role_id=role_id,
        opponent_role_id=opponent_role_id,
        world_id=world_id,
        observation_projection_id=observation_projection_id,
        budget_id=budget_id,
    )
    psro_step = oracle.step(state, candidates=constructor_planner_ids)

    return ExplorationPsroRoundOutcome(
        admissions=tuple(admissions),
        hypergraph=hypergraph,
        psro_step=psro_step,
    )
