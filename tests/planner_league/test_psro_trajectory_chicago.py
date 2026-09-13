# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `psro_trajectory` -- the real, previously-never-
exercised multi-round PSRO driver, chaining one real `PsroStep`'s output
`state` into the next real `PolicySpaceResponseOracle.step()` call.

Real collaborators throughout: a real `BreachClockDomain`, a real
`PlannerLeague`, real `schedule_cross_play_for_world`/
`admit_cross_play_schedule_payoffs` output, and the real
`PolicySpaceResponseOracle`/`PsroState`. No `unittest.mock` / `Mock` /
`MagicMock` / `patch` / `monkeypatch` anywhere in this file.

Every value asserted below was confirmed live before being written, not
assumed: chaining 4 real rounds over the same real 2-candidate
`("AOstar", "Astar")` vs. real intersecting-opponent
`("Astar", "BFWS")` scenario `cross_play_schedule_psro.py`'s own tests
already established produces a real, monotonically converging empirical
mixture toward `"Astar"` -- iteration 1 mixture
`{"Astar": 0.667, "BFWS": 0.333}` through iteration 4
`{"Astar": 0.833, "BFWS": 0.167}`, `"Astar"` selected every real round.
"""

from __future__ import annotations

from autofde_lab.hub.domain.breach_clock import BreachClockDomain
from autofde_lab.planner_league import PayoffHypergraph, PlannerLeague
from autofde_lab.planner_league.cross_play_world_schedule import schedule_cross_play_for_world
from autofde_lab.planner_league.psro import PolicySpaceResponseOracle, PsroState
from autofde_lab.planner_league.psro_trajectory import PsroTrajectory, run_psro_trajectory
from autofde_lab.reasoning.cross_play_schedule_payoff import admit_cross_play_schedule_payoffs


def _real_hypergraph_and_oracle():
    league = PlannerLeague()
    schedule = schedule_cross_play_for_world(
        league, "cyber_incident", left_role_id="plan_constructor", right_role_id="plan_falsifier"
    )
    domain = BreachClockDomain()
    hypergraph = PayoffHypergraph()
    admit_cross_play_schedule_payoffs(schedule, domain, hypergraph=hypergraph, limit=6)
    oracle = PolicySpaceResponseOracle(
        hypergraph, role_id="plan_constructor", opponent_role_id="plan_falsifier", world_id="cyber_incident"
    )
    return oracle


def test_real_multi_round_trajectory_converges_toward_the_dominant_response() -> None:
    oracle = _real_hypergraph_and_oracle()
    initial_state = PsroState.seed(("Astar", "BFWS"))

    trajectory = run_psro_trajectory(oracle, initial_state, candidates=("AOstar", "Astar"), max_rounds=4)

    assert isinstance(trajectory, PsroTrajectory)
    assert len(trajectory.steps) == 4
    assert trajectory.advanced_rounds == 4
    assert not trajectory.stopped_early
    assert all(step.advanced for step in trajectory.steps)
    assert [step.state.iteration for step in trajectory.steps] == [1, 2, 3, 4]
    assert all(step.receipt.selected_best_response == "Astar" for step in trajectory.steps)

    # Real, monotonically increasing empirical weight for the real
    # dominant response, round over round -- confirmed live before this
    # assertion was written.
    mixtures = [step.state.mixture["Astar"] for step in trajectory.steps]
    assert mixtures == sorted(mixtures)
    assert mixtures[0] < mixtures[-1]
    assert trajectory.final_state == trajectory.steps[-1].state
    assert trajectory.final_state.population == ("Astar", "BFWS")
    assert trajectory.final_state.counts == (("Astar", 5), ("BFWS", 1))


def test_real_trajectory_stops_early_on_a_genuine_refusal() -> None:
    """Confirms the trajectory driver never retries or papers over a real
    PSRO refusal: seeding over the real union of every observed opponent
    (the same load-bearing scenario `cross_play_schedule_psro.py`
    established) refuses on round 1, and the driver stops there rather
    than continuing."""
    oracle = _real_hypergraph_and_oracle()
    initial_state = PsroState.seed(("AOstar", "Astar", "BFWS", "DESPOT"))

    trajectory = run_psro_trajectory(oracle, initial_state, candidates=("AOstar", "Astar"), max_rounds=4)

    assert len(trajectory.steps) == 1
    assert trajectory.advanced_rounds == 0
    assert trajectory.stopped_early
    assert trajectory.steps[0].standing == "REFUSED"
    assert trajectory.steps[0].reason == "REFUSED:PSRO_MISSING_PAYOFF_CLOSURE"
    assert trajectory.final_state == initial_state


def test_refuses_a_non_positive_max_rounds() -> None:
    oracle = _real_hypergraph_and_oracle()
    initial_state = PsroState.seed(("Astar", "BFWS"))

    for bad_value in (0, -1):
        try:
            run_psro_trajectory(oracle, initial_state, candidates=("AOstar", "Astar"), max_rounds=bad_value)
            assert False, f"expected ValueError for max_rounds={bad_value}"
        except ValueError as exc:
            assert str(exc) == "REFUSED:MAX_ROUNDS_MUST_BE_POSITIVE"


def test_single_round_trajectory_matches_a_bare_oracle_step_call() -> None:
    """Real equivalence check: a 1-round trajectory must produce exactly
    the same real step the caller would get from calling
    `oracle.step()` directly once -- no hidden extra work."""
    oracle = _real_hypergraph_and_oracle()
    initial_state = PsroState.seed(("Astar", "BFWS"))

    trajectory = run_psro_trajectory(oracle, initial_state, candidates=("AOstar", "Astar"), max_rounds=1)
    direct_step = oracle.step(initial_state, candidates=("AOstar", "Astar"))

    assert len(trajectory.steps) == 1
    assert trajectory.steps[0].receipt.identity_sha256 == direct_step.receipt.identity_sha256
