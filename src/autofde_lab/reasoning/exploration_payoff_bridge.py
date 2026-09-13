# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Bridges `laboratory.py`'s exploration-candidate generators (TRIZ section
14, DOE section 15, Monte Carlo section 16 -- `generate_triz_candidates`,
`generate_doe_candidates`, `generate_montecarlo_candidates`) to the real
role-conditioned planner league (`autofde_lab.planner_league`).

**The one thing this module refuses to do**: put an `ArchitectureCandidate`'s
own `provenance` string (`"triz-v1"` / `"doe-v1"` / `"montecarlo-v1"`) into
`PolicySpec.planner_id`. `PlannerLeague.compatibility()` resolves
`planner_id` through `load_registered_solver` -> a real
`importlib.metadata.entry_points(group="autofde_lab.solvers", ...)` lookup
(`utils.py`) against real `Solver` subclasses exposing `check_domain()` --
TRIZ/DOE/Monte Carlo are plain generator functions over
`DesiredStateHypothesis`, never `Solver` subclasses, and no
`autofde_lab.solvers` entry point named `triz-v1`/`doe-v1`/`montecarlo-v1`
exists in this repo's `pyproject.toml`. Putting a generator's provenance tag
into `planner_id` would structurally always resolve
`UNSUPPORTED:PLANNER_LOAD_FAILED` in `PlannerLeague.compatibility()` -- a
candidate that constructs cleanly and then always refuses the moment anyone
tries to score it. `planner_league/catalog.py`'s own header confirms this:
it is generated from an ontology of registered `Solver` capabilities that
has never modeled TRIZ/DOE/Monte Carlo at all.

The real, correct join instead: a real registered planner (from
`planner_league.catalog.PRIMARY_PLANNERS`) plays `"plan_constructor"` and
realizes the exploration candidate's `target_state_assertions` as its own
goal; a second real registered planner plays `"plan_falsifier"` and attempts
`laboratory.falsify_candidate`'s own real falsification role -- exactly the
`plan_constructor` / `plan_falsifier` role pair `planner_league.catalog.
ROLE_SPECS` already names (`"construct_goal_reaching_plan"` /
`"find_plan_counterexample"`). The already-real `FalsificationResult`
(computed by `laboratory.falsify_candidate` over real `ExperimentReceipt`s
-- never re-derived here) becomes the real payoff edge between those two
real planners.

The exploration candidate's own identity survives the join **explicitly**,
via `FalsificationResult.candidate_id == ArchitectureCandidate.candidate_id`
(checked below, refused on mismatch) -- never via filename, call order, or
timestamp adjacency (`.claude/rules/no-dual-bookkeeping.md`). No new
vocabulary/table is introduced to carry that identity; the existing
`candidate_id` field on both real, already-existing types is reused as-is.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from autofde_lab.planner_league import (
    LeagueMatch,
    PayoffHypergraph,
    PayoffObservation,
    PlannerLeague,
    PolicySpec,
)

from .laboratory import ArchitectureCandidate, FalsificationResult, FalsificationStanding

__all__ = [
    "ExplorationPayoffOutcome",
    "falsification_to_payoff_scores",
    "admit_exploration_candidate_payoff",
]


def falsification_to_payoff_scores(
    standing: FalsificationStanding,
) -> tuple[float, float] | None:
    """Real, explicit, named mapping from a real `FalsificationStanding` to
    `(constructor_score, falsifier_score)` -- covers exactly `SURVIVES`
    (the constructor's candidate withstood falsification: constructor wins
    outright), `FALSIFIED` (the falsifier found a real counterexample:
    falsifier wins outright), and `PARTIAL` (split, real evidence on both
    sides). `UNKNOWN`/`UNSUPPORTED`/`REFUSED` carry no real scoreable
    evidence and return `None`, never a fabricated `0.0`/`0.0` placeholder
    score -- per `absence-is-not-evidence.md`, absence of a falsification
    verdict is not evidence the candidate ties."""
    if standing is FalsificationStanding.SURVIVES:
        return (1.0, 0.0)
    if standing is FalsificationStanding.FALSIFIED:
        return (0.0, 1.0)
    if standing is FalsificationStanding.PARTIAL:
        return (0.5, 0.5)
    return None


@dataclass(frozen=True, slots=True)
class ExplorationPayoffOutcome:
    """Result of attempting to admit one exploration candidate's real
    falsification evidence into a real `PayoffHypergraph`. Mirrors
    `psro.PsroStep`'s own `(state/receipt/standing/reason)` shape -- a
    refused/unsupported attempt is a real, named, inspectable outcome, never
    a silently absent `PayoffObservation` with no reason attached."""

    observation: PayoffObservation | None
    standing: str
    reason: str

    @property
    def admitted(self) -> bool:
        """Whether a real `PayoffObservation` was constructed and added to
        the caller's `PayoffHypergraph`."""
        return self.observation is not None


def admit_exploration_candidate_payoff(
    candidate: ArchitectureCandidate,
    falsification: FalsificationResult,
    *,
    league: PlannerLeague,
    domain: Any,
    hypergraph: PayoffHypergraph,
    world_id: str,
    constructor_planner_id: str,
    falsifier_planner_id: str,
    role_id: str = "plan_constructor",
    opponent_role_id: str = "plan_falsifier",
    observation_projection_id: str = "full_observation",
    budget_id: str = "balanced",
) -> ExplorationPayoffOutcome:
    """Admit one real exploration-generated `ArchitectureCandidate`'s real
    `FalsificationResult` as one real `PayoffObservation` edge between two
    real registered planners (`constructor_planner_id` realizing the
    candidate under `role_id`, `falsifier_planner_id` attempting to falsify
    it under `opponent_role_id`) -- and, only on success, actually calls
    `hypergraph.add(observation)`.

    Never puts `candidate.provenance` (`"triz-v1"`/`"doe-v1"`/
    `"montecarlo-v1"`) into a `PolicySpec.planner_id` -- see module
    docstring. Refuses, with a named standing/reason and no mutation of
    `hypergraph`, on any of:

    - `falsification.candidate_id != candidate.candidate_id` (explicit
      identity mismatch -- `no-dual-bookkeeping.md`).
    - `falsification.standing` not in `{SURVIVES, FALSIFIED, PARTIAL}` (no
      real scoreable evidence -- `absence-is-not-evidence.md`).
    - either planner is not `COMPATIBLE` for its role against `domain`, per
      a real `league.compatibility()` call (never assumed).
    - `falsification.receipt_refs` is empty (no real receipt to bind the
      payoff to).
    - the real `PayoffObservation.__post_init__` fail-closed check itself
      refuses. Given this function's own upstream guards (a real, non-empty
      SHA-256 hex `receipt_id` is always computed once `receipt_refs` is
      confirmed non-empty), this branch is unreachable through this
      function alone as of this implementation -- the `try`/`except` is
      kept so that if `PayoffObservation`'s own construction contract ever
      grows an additional failure mode, this function still returns a
      typed outcome instead of an uncaught exception, and the real guard
      is never silently bypassed either way: it is the same
      `PayoffObservation.__post_init__` `tests/planner_league/
      test_planner_league.py::test_payoff_hypergraph_rejects_unreceipted_execution`
      already exercises directly, not a re-derived copy of its logic.
    """
    if falsification.candidate_id != candidate.candidate_id:
        return ExplorationPayoffOutcome(
            observation=None,
            standing="REFUSED",
            reason=(
                "REFUSED:FALSIFICATION_CANDIDATE_MISMATCH:"
                f"falsification.candidate_id={falsification.candidate_id!r} != "
                f"candidate.candidate_id={candidate.candidate_id!r}"
            ),
        )

    scores = falsification_to_payoff_scores(falsification.standing)
    if scores is None:
        return ExplorationPayoffOutcome(
            observation=None,
            standing=falsification.standing.value,
            reason=(
                "UNSUPPORTED:NO_SCOREABLE_EVIDENCE:FalsificationStanding."
                f"{falsification.standing.name} carries no real payoff evidence "
                "-- only SURVIVES/FALSIFIED/PARTIAL do"
            ),
        )

    constructor_compat = league.compatibility(domain, constructor_planner_id, role_id)
    if not constructor_compat.compatible:
        return ExplorationPayoffOutcome(
            observation=None,
            standing=constructor_compat.standing.value,
            reason=f"constructor:{constructor_compat.reason}",
        )

    falsifier_compat = league.compatibility(domain, falsifier_planner_id, opponent_role_id)
    if not falsifier_compat.compatible:
        return ExplorationPayoffOutcome(
            observation=None,
            standing=falsifier_compat.standing.value,
            reason=f"falsifier:{falsifier_compat.reason}",
        )

    if not falsification.receipt_refs:
        return ExplorationPayoffOutcome(
            observation=None,
            standing="REFUSED",
            reason="REFUSED:NO_RECEIPT_REFS_ON_FALSIFICATION_RESULT",
        )

    match = LeagueMatch(
        world_id=world_id,
        left_role_id=role_id,
        left_policy=PolicySpec.for_role(
            constructor_planner_id,
            role_id,
            observation_projection_id=observation_projection_id,
            budget_id=budget_id,
        ),
        right_role_id=opponent_role_id,
        right_policy=PolicySpec.for_role(
            falsifier_planner_id,
            opponent_role_id,
            observation_projection_id=observation_projection_id,
            budget_id=budget_id,
        ),
    )

    # A real, deterministic digest over the exploration candidate's own
    # identity, its real generator provenance, the real falsification
    # standing, and every real receipt reference the falsification result
    # carries -- never a fabricated/synthetic receipt id, and never the bare
    # candidate_id alone (which would collide across distinct falsification
    # runs of the same candidate).
    receipt_id = hashlib.sha256(
        "|".join(
            (
                "exploration-payoff-v1",
                candidate.candidate_id,
                candidate.provenance,
                falsification.standing.value,
                *falsification.receipt_refs,
            )
        ).encode("utf-8")
    ).hexdigest()

    left_score, right_score = scores
    try:
        observation = PayoffObservation(match, left_score, right_score, receipt_id=receipt_id)
    except ValueError as exc:
        # Defensive only -- see docstring. Never bypassed: this is the same
        # real PayoffObservation.__post_init__ fail-closed check, not a
        # re-derived copy of its logic.
        return ExplorationPayoffOutcome(observation=None, standing="REFUSED", reason=str(exc))

    hypergraph.add(observation)
    return ExplorationPayoffOutcome(
        observation=observation,
        standing="ALIVE",
        reason="ALIVE:EXPLORATION_FALSIFICATION_PAYOFF_ADMITTED",
    )
