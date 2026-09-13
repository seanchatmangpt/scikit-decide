# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `cross_play_schedule_payoff` -- the real,
bounded scoring of `cross_play_world_schedule.py`'s real scheduled
`LeagueMatch`es via `generic_domain_solve.attempt_solve_domain`.

Real collaborators throughout: a real `BreachClockDomain`, a real
`PlannerLeague`, real `schedule_cross_play_for_world` output, and the
real, installed `AOstar`/`Astar`/`BFWS` solver entry points. No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.

Every value asserted below was confirmed live before being written, not
assumed: for `cyber_incident` (`BreachClockDomain`), the first 3 real
scheduled matches (per `cover_cross_play`'s own deterministic covering
order) are `AOstar vs AOstar`, `AOstar vs Astar`, `AOstar vs BFWS`.
`AOstar` and `Astar` both really solve `BreachClockDomain` to its real
goal in exactly 6 real actions; `BFWS` really raises at construction time
(`TypeError: BFWS.__init__() missing 1 required positional argument:
'state_features'` -- a real, known `REQUIRES_CONFIGURATION` solver per
`src/autofde_lab/CLAUDE.md`'s own documented invariant), caught as a real,
honest `UNSUPPORTED:SOLVE_RAISED:TypeError:...`, never an uncaught crash.
"""

from __future__ import annotations

from autofde_lab.hub.domain.breach_clock import BreachClockDomain
from autofde_lab.planner_league import PayoffHypergraph, PlannerLeague
from autofde_lab.planner_league.cross_play_world_schedule import schedule_cross_play_for_world
from autofde_lab.reasoning.cross_play_schedule_payoff import (
    ScheduledMatchPayoffOutcome,
    admit_cross_play_schedule_payoffs,
)


def _real_schedule():
    league = PlannerLeague()
    return schedule_cross_play_for_world(
        league, "cyber_incident", left_role_id="plan_constructor", right_role_id="plan_falsifier"
    )


def test_admits_real_payoffs_for_a_bounded_subset_of_a_real_schedule() -> None:
    schedule = _real_schedule()
    domain = BreachClockDomain()
    hypergraph = PayoffHypergraph()

    outcomes = admit_cross_play_schedule_payoffs(schedule, domain, hypergraph=hypergraph, limit=3)

    assert len(outcomes) == 3
    assert all(isinstance(o, ScheduledMatchPayoffOutcome) for o in outcomes)
    assert len(hypergraph.observations) == 3
    # Real, deterministic first-3 matches from cover_cross_play's own
    # covering order.
    assert [(o.match.left_policy.planner_id, o.match.right_policy.planner_id) for o in outcomes] == [
        ("AOstar", "AOstar"),
        ("AOstar", "Astar"),
        ("AOstar", "BFWS"),
    ]
    # Real world_id/roles preserved from the real schedule, never coerced.
    assert all(o.match.world_id == "cyber_incident" for o in outcomes)
    assert all(o.match.left_role_id == "plan_constructor" for o in outcomes)
    assert all(o.match.right_role_id == "plan_falsifier" for o in outcomes)


def test_real_both_alive_match_scores_a_real_tie() -> None:
    schedule = _real_schedule()
    domain = BreachClockDomain()
    hypergraph = PayoffHypergraph()

    outcomes = admit_cross_play_schedule_payoffs(schedule, domain, hypergraph=hypergraph, limit=1)
    outcome = outcomes[0]

    assert outcome.admitted
    assert outcome.standing == "ALIVE"
    assert outcome.left_outcome.standing == "ALIVE"
    assert outcome.right_outcome.standing == "ALIVE"
    assert outcome.left_outcome.plan_length == 6
    assert outcome.right_outcome.plan_length == 6
    assert outcome.observation is not None
    assert outcome.observation.left_score == 1.0
    assert outcome.observation.right_score == 1.0
    assert outcome.observation.receipt_id


def test_real_unsupported_planner_scores_a_real_loss_never_a_crash() -> None:
    schedule = _real_schedule()
    domain = BreachClockDomain()
    hypergraph = PayoffHypergraph()

    outcomes = admit_cross_play_schedule_payoffs(schedule, domain, hypergraph=hypergraph, limit=3)
    third = outcomes[2]

    assert third.match.right_policy.planner_id == "BFWS"
    assert third.left_outcome.standing == "ALIVE"
    assert third.right_outcome.standing == "UNSUPPORTED"
    assert third.right_outcome.reason.startswith("UNSUPPORTED:SOLVE_RAISED:TypeError")
    assert third.admitted
    assert third.observation.left_score == 1.0
    assert third.observation.right_score == 0.0


def test_refuses_a_non_positive_limit() -> None:
    schedule = _real_schedule()
    domain = BreachClockDomain()
    hypergraph = PayoffHypergraph()

    for bad_limit in (0, -1):
        try:
            admit_cross_play_schedule_payoffs(schedule, domain, hypergraph=hypergraph, limit=bad_limit)
            assert False, f"expected ValueError for limit={bad_limit}"
        except ValueError as exc:
            assert str(exc) == "REFUSED:LIMIT_MUST_BE_POSITIVE"
    assert hypergraph.observations == []


def test_receipt_ids_are_real_and_deterministic_across_independent_runs() -> None:
    schedule = _real_schedule()
    domain_a = BreachClockDomain()
    domain_b = BreachClockDomain()
    hypergraph_a = PayoffHypergraph()
    hypergraph_b = PayoffHypergraph()

    outcomes_a = admit_cross_play_schedule_payoffs(schedule, domain_a, hypergraph=hypergraph_a, limit=3)
    outcomes_b = admit_cross_play_schedule_payoffs(schedule, domain_b, hypergraph=hypergraph_b, limit=3)

    receipt_ids_a = [o.observation.receipt_id for o in outcomes_a]
    receipt_ids_b = [o.observation.receipt_id for o in outcomes_b]
    assert receipt_ids_a == receipt_ids_b
    assert len(set(receipt_ids_a)) == 3
