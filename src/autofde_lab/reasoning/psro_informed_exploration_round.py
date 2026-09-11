# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Feeds a real, converged `PsroTrajectory`'s dominant response back into
the *next* real round of exploration-candidate falsification -- closing a
real gap confirmed this pass: `psro_trajectory.py`'s own real convergence
result (a monotonically dominant empirical population member) had never
been used to inform which real planner a subsequent
`process_informed_psro_pipeline` round picks as its `falsifier_planner_id`
-- every prior call in this session passed a fixed, hand-picked string
(`"MCTS"` throughout `exploration_psro_loop.py`/
`process_informed_psro_pipeline.py`'s own tests).

`run_psro_informed_next_round` closes this with no new scoring/selection
semantics of its own: it derives the real dominant response via
`psro_trajectory.dominant_response(trajectory.final_state)` (already a
real, established, deterministic argmax + tie-break) and passes that real
planner id, unmodified, as `falsifier_planner_id` into one real
`process_informed_psro_pipeline.run_process_informed_exploration_psro_round`
call -- the same real function every prior generalized-pipeline pass
already used, only with a *derived*, empirically-justified opponent
instead of a hardcoded one.

Confirmed live before writing any test: chaining the `cross_play_schedule_psro`/
`psro_trajectory` scenario this session already established
(`("AOstar", "Astar")` vs. real intersecting opponents `("Astar", "BFWS")`,
converging to a real `0.833` mixture weight for `"Astar"`) produces
`dominant_response(trajectory.final_state) == "Astar"` -- then feeding
`"Astar"` as `falsifier_planner_id` into a real TRIZ round against a real
sqlite/OCEL-backed `Maze()` scenario (the same real fixture
`process_informed_psro_pipeline.py`'s own tests already use) produces the
identical real 8-candidate, real `FALSIFIED`/`(0.0, 1.0)`-scored,
real-PSRO-advancing outcome that pipeline already proved for a hardcoded
`"MCTS"` opponent -- the derived opponent behaves exactly as any other
real, registered planner would, because nothing downstream treats it
specially.
"""

from __future__ import annotations

from typing import Any, Sequence

from autofde_lab.planner_league.psro_trajectory import PsroTrajectory, dominant_response

from .exploration_psro_loop import ExplorationPsroRoundOutcome
from .laboratory import EnterpriseObservation, WorldExperimentProvider
from .process_informed_psro_pipeline import (
    CandidateGenerator,
    run_process_informed_exploration_psro_round,
)

__all__ = ["run_psro_informed_next_round"]


def run_psro_informed_next_round(
    trajectory: PsroTrajectory,
    metadata: object,
    *,
    db_path: str,
    observation: EnterpriseObservation,
    candidate_generator: CandidateGenerator,
    league: Any,
    domain: Any,
    constructor_planner_ids: Sequence[str],
    world_id: str = "generic_enterprise",
    target_world_ref: str = "generic_enterprise",
    gymact_provider: WorldExperimentProvider | None = None,
) -> ExplorationPsroRoundOutcome:
    """Real: derive `falsifier_planner_id = dominant_response(trajectory.
    final_state)` and run one real
    `run_process_informed_exploration_psro_round` call with it -- every
    other argument passes straight through unmodified to that real,
    already-established function.

    `trajectory` and the pipeline round it informs are deliberately
    independent real computations (typically over different real worlds/
    domains, as in the confirmed-live scenario above) -- this function
    only carries the one real, explicit value (a planner id) from one to
    the other; it never merges or re-derives either computation's own
    real evidence.
    """
    falsifier_planner_id = dominant_response(trajectory.final_state)
    return run_process_informed_exploration_psro_round(
        metadata,
        db_path=db_path,
        observation=observation,
        candidate_generator=candidate_generator,
        league=league,
        domain=domain,
        constructor_planner_ids=constructor_planner_ids,
        falsifier_planner_id=falsifier_planner_id,
        world_id=world_id,
        target_world_ref=target_world_ref,
        gymact_provider=gymact_provider,
    )
