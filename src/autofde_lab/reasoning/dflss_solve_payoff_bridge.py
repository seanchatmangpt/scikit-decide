# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Bridges `dflss_planner_solve.attempt_solve_dflss_curriculum`'s real,
per-planner DMEDI-curriculum solve outcomes into a real
`planner_league.PayoffHypergraph` -- closing a real gap confirmed this
session: `attempt_solve_dflss_curriculum`, `exploration_psro_loop.py`, and
`world_admission.py` were three separate, unconnected pieces (`grep -rn
"attempt_solve_dflss_curriculum" src/ tests/` found only its own definition
and test file -- no caller feeding its outcome into any payoff/PSRO
machinery).

Unlike `exploration_payoff_bridge.py` (which pairs a real
`plan_constructor` planner against a real `plan_falsifier` planner
attempting `laboratory.falsify_candidate`'s adversarial falsification
role), the DMEDI-curriculum PDDL problem has no adversarial counterpart --
it is a single-planner, deterministic goal-reaching task
(`dflss_planner_solve.py`'s own docstring). `PayoffObservation`/
`LeagueMatch` are structurally two-sided (`left_policy`/`right_policy`), so
this module reframes the real gap honestly rather than fabricating a
falsifier that does nothing: it drives **two** real planners, each through
its own real, independent `attempt_solve_dflss_curriculum` call, both
playing the same real `"plan_constructor"` role (nothing in
`LeagueMatch.__post_init__` requires `left_role_id != right_role_id` --
confirmed by reading `core.py` directly), and admits their real,
independently-observed solve outcomes as one real head-to-head
`PayoffObservation`: "which of these two real planners actually
constructs a goal-reaching plan for this real curriculum problem."

Reuses only existing, already-real vocabulary -- `catalog.PRIMARY_PLANNERS`
(never `NOVELTY_ORACLES`, matching `PlannerLeague.__init__`'s own
`REFUSED:LLM_NOVELTY_BOUNDARY` boundary) and the existing
`"generic_enterprise"` `world_id` / `"plan_constructor"` `role_id` already
established by `exploration_payoff_bridge.py` and `world_admission.py`.
`catalog.py` itself is never hand-edited (it is ggen-generated, "Do not
hand-edit" per its own header).

Score contract, real and explicit: `1.0` if the real
`attempt_solve_dflss_curriculum` outcome is `ALIVE` (the real planner
actually reached the real goal), `0.0` for any other real standing
(`REFUSED:DOMAIN_CONTRACT_MISMATCH`, `REFUSED:GOAL_NOT_REACHED`,
`UNSUPPORTED:*`) -- a planner structurally incapable of solving this domain
is real, legitimate losing evidence, not an error to hide. Both real
planners reaching `ALIVE` on this deterministic domain (confirmed
elsewhere this session: `Astar` and `LRTAstar` both reach the identical
52-action plan) is a real, honest tie (`1.0`/`1.0`), never forced into an
artificial zero-sum split.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from autofde_lab.planner_league import LeagueMatch, PayoffHypergraph, PayoffObservation, PolicySpec
from autofde_lab.planner_league.catalog import NOVELTY_ORACLES

from .dflss_planner_solve import PlannerSolveOutcome, attempt_solve_dflss_curriculum

__all__ = ["DflssSolvePayoffOutcome", "admit_dflss_solve_payoff"]


def _outcome_score(outcome: PlannerSolveOutcome) -> float:
    """Real, explicit, named mapping -- see module docstring's score
    contract. Never a fabricated intermediate value."""
    return 1.0 if outcome.alive else 0.0


@dataclass(frozen=True, slots=True)
class DflssSolvePayoffOutcome:
    """Real, typed result of one attempted DMEDI-curriculum head-to-head
    admission. Mirrors `exploration_payoff_bridge.ExplorationPayoffOutcome`'s
    own `(observation/standing/reason)` shape -- carries both real,
    independently-computed `PlannerSolveOutcome`s too, so a caller can
    inspect exactly what each real planner actually did, never only a
    summary derived from them."""

    left_outcome: PlannerSolveOutcome
    right_outcome: PlannerSolveOutcome
    observation: PayoffObservation | None
    standing: str
    reason: str

    @property
    def admitted(self) -> bool:
        return self.observation is not None


def admit_dflss_solve_payoff(
    left_planner_id: str,
    right_planner_id: str,
    *,
    hypergraph: PayoffHypergraph,
    world_id: str = "generic_enterprise",
    role_id: str = "plan_constructor",
    observation_projection_id: str = "full_observation",
    budget_id: str = "balanced",
) -> DflssSolvePayoffOutcome:
    """Drive `left_planner_id` and `right_planner_id` each through a real,
    independent `attempt_solve_dflss_curriculum` call, then admit their
    real outcomes as one real head-to-head `PayoffObservation` -- only on
    success does this call `hypergraph.add(observation)`.

    Refuses `REFUSED:LLM_NOVELTY_BOUNDARY` for either side named in
    `NOVELTY_ORACLES` (never `PRIMARY_PLANNERS`), matching
    `PlannerLeague.__init__`'s own real boundary -- this module never lets
    an LLM novelty oracle enter the empirical payoff ledger. A side that is
    a real, registered `PRIMARY_PLANNERS` member but structurally
    incompatible with this PDDL domain (or genuinely unloadable) is *not*
    refused here -- its real `0.0` score is legitimate losing evidence, per
    the module docstring's score contract.
    """
    for planner_id in (left_planner_id, right_planner_id):
        if planner_id in NOVELTY_ORACLES:
            refusal = PlannerSolveOutcome(planner_id, "REFUSED", "REFUSED:LLM_NOVELTY_BOUNDARY")
            return DflssSolvePayoffOutcome(
                left_outcome=refusal if planner_id == left_planner_id else PlannerSolveOutcome(
                    left_planner_id, "REFUSED", "REFUSED:LLM_NOVELTY_BOUNDARY:PEER"
                ),
                right_outcome=refusal if planner_id == right_planner_id else PlannerSolveOutcome(
                    right_planner_id, "REFUSED", "REFUSED:LLM_NOVELTY_BOUNDARY:PEER"
                ),
                observation=None,
                standing="REFUSED",
                reason=f"REFUSED:LLM_NOVELTY_BOUNDARY:{planner_id}",
            )

    left_outcome = attempt_solve_dflss_curriculum(left_planner_id)
    right_outcome = attempt_solve_dflss_curriculum(right_planner_id)

    for planner_id, outcome in ((left_planner_id, left_outcome), (right_planner_id, right_outcome)):
        if outcome.reason.startswith("REFUSED:UNKNOWN_PLANNER"):
            return DflssSolvePayoffOutcome(
                left_outcome=left_outcome,
                right_outcome=right_outcome,
                observation=None,
                standing="REFUSED",
                reason=f"REFUSED:UNKNOWN_PLANNER:{planner_id}",
            )

    match = LeagueMatch(
        world_id=world_id,
        left_role_id=role_id,
        left_policy=PolicySpec.for_role(
            left_planner_id,
            role_id,
            observation_projection_id=observation_projection_id,
            budget_id=budget_id,
        ),
        right_role_id=role_id,
        right_policy=PolicySpec.for_role(
            right_planner_id,
            role_id,
            observation_projection_id=observation_projection_id,
            budget_id=budget_id,
        ),
    )

    # A real, deterministic digest over both real planners' real solve
    # standings/reasons/plan lengths -- never a fabricated/synthetic
    # receipt id.
    receipt_id = hashlib.sha256(
        "|".join(
            (
                "dflss-solve-payoff-v1",
                left_planner_id,
                left_outcome.standing,
                left_outcome.reason,
                str(left_outcome.plan_length),
                right_planner_id,
                right_outcome.standing,
                right_outcome.reason,
                str(right_outcome.plan_length),
            )
        ).encode("utf-8")
    ).hexdigest()

    left_score = _outcome_score(left_outcome)
    right_score = _outcome_score(right_outcome)
    try:
        observation = PayoffObservation(match, left_score, right_score, receipt_id=receipt_id)
    except ValueError as exc:
        # Defensive only -- receipt_id is always real and non-empty above.
        return DflssSolvePayoffOutcome(
            left_outcome=left_outcome,
            right_outcome=right_outcome,
            observation=None,
            standing="REFUSED",
            reason=str(exc),
        )

    hypergraph.add(observation)
    return DflssSolvePayoffOutcome(
        left_outcome=left_outcome,
        right_outcome=right_outcome,
        observation=observation,
        standing="ALIVE",
        reason="ALIVE:DFLSS_SOLVE_PAYOFF_ADMITTED",
    )
