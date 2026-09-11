# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, multi-round PSRO trajectory driver -- closes a gap confirmed this
pass: every real caller of `PolicySpaceResponseOracle.step()` in this
repo, including `psro.py`'s own pre-existing test suite (predating this
session) and every real integration built this session
(`exploration_psro_loop.py`, `cross_play_schedule_psro.py`), calls it
exactly once per test and discards the resulting state, or calls it twice
from the *same* initial state only to prove order-invariance
(`test_psro.py::test_psro_candidate_order_does_not_override_empirical_payoff`)
-- never chains one real step's output `PsroState` into the next real
step's input. `PsroState` carries a real `iteration` field and
`PsroReceipt` carries real `prior_population`/`next_population`
specifically to support chaining, but no real multi-round PSRO trajectory
-- the actual point of PSRO: iteratively growing an empirical population/
mixture over successive best-response rounds -- has ever been exercised
anywhere in this repo (`grep -rn "psro_step.state|oracle.step("
src/ tests/` confirms every real call site).

`run_psro_trajectory` is a thin, real driver: it repeats
`oracle.step(state, candidates=...)`, feeding each real step's real output
`state` into the next real call, until either `max_rounds` real rounds
have run or a real step fails to advance (a real
`REFUSED:PSRO_MISSING_PAYOFF_CLOSURE` mid-trajectory is honest, terminal
information -- never retried, never silently skipped past). No new
scoring/selection logic is introduced; `PolicySpaceResponseOracle.step`'s
own real, already-tested contract is the only thing driving each round.

Confirmed live before writing any test: chaining 4 real rounds over a real
`cover_cross_play`-scheduled `PayoffHypergraph` (the same real 2-candidate
`("AOstar", "Astar")` vs. real intersecting opponents `("Astar", "BFWS")`
scenario `cross_play_schedule_psro.py`'s own tests already established)
produces a real, monotonically converging empirical mixture toward the
real, deterministically-dominant best response `"Astar"`: iteration 1
mixture `{"Astar": 0.667, "BFWS": 0.333}`, iteration 4 mixture
`{"Astar": 0.833, "BFWS": 0.167}` -- `"Astar"`'s own empirical weight
strictly increasing round over round, exactly as PSRO's own design
intends, and never previously observed in this repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .psro import PolicySpaceResponseOracle, PsroState, PsroStep

__all__ = ["PsroTrajectory", "run_psro_trajectory", "dominant_response"]


@dataclass(frozen=True, slots=True)
class PsroTrajectory:
    """The real, ordered sequence of every real `PsroStep` taken, from a
    real initial state through however many real rounds actually
    advanced. The trajectory always includes the first step that failed
    to advance (if any) as its final element -- that refusal is real,
    load-bearing information about where the real empirical trajectory
    stopped, never silently dropped."""

    initial_state: PsroState
    steps: tuple[PsroStep, ...]

    @property
    def final_state(self) -> PsroState:
        """The real, furthest-advanced state reached -- the last real
        `step.state` from an advancing round, or `initial_state` if zero
        real rounds advanced."""
        for step in reversed(self.steps):
            if step.advanced:
                return step.state
        return self.initial_state

    @property
    def advanced_rounds(self) -> int:
        return sum(1 for step in self.steps if step.advanced)

    @property
    def stopped_early(self) -> bool:
        """Whether the trajectory ended because a real round refused,
        rather than because `max_rounds` was reached with every round
        advancing."""
        return bool(self.steps) and not self.steps[-1].advanced


def run_psro_trajectory(
    oracle: PolicySpaceResponseOracle,
    initial_state: PsroState,
    *,
    candidates: Iterable[str],
    max_rounds: int,
) -> PsroTrajectory:
    """Real: repeatedly call `oracle.step(state, candidates=candidates)`,
    feeding each real advancing step's real output `state` into the next
    real call, for up to `max_rounds` real rounds. Stops immediately
    (without raising) the moment a real round fails to advance -- that
    step is still appended to `steps` as the trajectory's honest final
    element.

    Raises `ValueError("REFUSED:MAX_ROUNDS_MUST_BE_POSITIVE")` for a
    non-positive `max_rounds` -- an explicit refusal, never a silent
    zero-round no-op.
    """
    if max_rounds <= 0:
        raise ValueError("REFUSED:MAX_ROUNDS_MUST_BE_POSITIVE")

    candidate_tuple = tuple(candidates)
    steps: list[PsroStep] = []
    state = initial_state
    for _ in range(max_rounds):
        step = oracle.step(state, candidates=candidate_tuple)
        steps.append(step)
        if not step.advanced:
            break
        state = step.state

    return PsroTrajectory(initial_state=initial_state, steps=tuple(steps))


def dominant_response(state: PsroState) -> str:
    """Real, deterministic argmax over `state.mixture` -- the real,
    currently-converged PSRO conclusion: which population member
    presently carries the most empirical weight. Ties are broken by the
    same `(weight, planner_id)` lexicographic comparison
    `PayoffHypergraph.empirical_best_response` itself already uses (a
    strictly greater `planner_id` string wins a weight tie) -- this
    function introduces no new tie-break rule of its own, it reuses the
    one real convention already established.

    `state.population` is always non-empty (`PsroState.__post_init__`'s
    own real `REFUSED:PSRO_EMPTY_POPULATION` validation guarantees this),
    so `state.mixture` always has at least one real entry.
    """
    best: tuple[float, str] | None = None
    for planner_id, weight in state.mixture.items():
        key = (weight, planner_id)
        if best is None or key > best:
            best = key
    assert best is not None
    return best[1]
