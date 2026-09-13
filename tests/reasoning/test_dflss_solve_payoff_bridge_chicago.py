# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `dflss_solve_payoff_bridge` -- the real join
between `dflss_planner_solve.attempt_solve_dflss_curriculum`'s real,
per-planner DMEDI-curriculum solve outcomes and a real
`planner_league.PayoffHypergraph`.

Real collaborators throughout: real on-disk per-planner PDDL problem
files, a real `PDDLDomain`, the real, installed `Astar`/`LRTAstar`/`CIDual`
solver entry points' real `check_domain()`/`solve()`, and a real
`PayoffHypergraph`/`PayoffObservation`. No `unittest.mock` / `Mock` /
`MagicMock` / `patch` / `monkeypatch` anywhere in this file.

`Astar`/`LRTAstar` are confirmed live elsewhere this session to both really
solve the DMEDI curriculum to the goal in 52 actions; `CIDual` is confirmed
live to be domain-contract-incompatible with this PDDL domain.
"""

from __future__ import annotations

from autofde_lab.planner_league import PayoffHypergraph
from autofde_lab.planner_league.catalog import NOVELTY_ORACLES
from autofde_lab.reasoning.dflss_solve_payoff_bridge import (
    DflssSolvePayoffOutcome,
    admit_dflss_solve_payoff,
)


def test_admits_a_real_tie_between_two_real_alive_planners() -> None:
    hypergraph = PayoffHypergraph()
    result = admit_dflss_solve_payoff("Astar", "LRTAstar", hypergraph=hypergraph)

    assert isinstance(result, DflssSolvePayoffOutcome)
    assert result.standing == "ALIVE"
    assert result.admitted
    assert result.left_outcome.standing == "ALIVE"
    assert result.right_outcome.standing == "ALIVE"
    assert result.left_outcome.plan_length == 52
    assert result.right_outcome.plan_length == 52

    assert result.observation is not None
    assert result.observation.left_score == 1.0
    assert result.observation.right_score == 1.0
    assert result.observation.match.left_policy.planner_id == "Astar"
    assert result.observation.match.right_policy.planner_id == "LRTAstar"
    assert result.observation.match.left_role_id == "plan_constructor"
    assert result.observation.match.right_role_id == "plan_constructor"
    assert result.observation.match.world_id == "generic_enterprise"
    assert result.observation.receipt_id  # real, non-empty digest
    assert hypergraph.observations == [result.observation]


def test_admits_a_real_win_for_the_domain_compatible_planner() -> None:
    hypergraph = PayoffHypergraph()
    result = admit_dflss_solve_payoff("Astar", "CIDual", hypergraph=hypergraph)

    assert result.standing == "ALIVE"
    assert result.left_outcome.standing == "ALIVE"
    assert result.right_outcome.standing == "REFUSED"
    assert result.right_outcome.reason == "REFUSED:DOMAIN_CONTRACT_MISMATCH"

    assert result.observation.left_score == 1.0
    assert result.observation.right_score == 0.0
    assert len(hypergraph.observations) == 1


def test_refuses_llm_novelty_boundary_for_either_side() -> None:
    assert "DSPyPolicy" in NOVELTY_ORACLES
    hypergraph = PayoffHypergraph()

    result = admit_dflss_solve_payoff("DSPyPolicy", "Astar", hypergraph=hypergraph)
    assert not result.admitted
    assert result.standing == "REFUSED"
    assert result.reason == "REFUSED:LLM_NOVELTY_BOUNDARY:DSPyPolicy"
    assert result.observation is None
    assert hypergraph.observations == []

    result2 = admit_dflss_solve_payoff("Astar", "DSPyPolicy", hypergraph=hypergraph)
    assert not result2.admitted
    assert result2.reason == "REFUSED:LLM_NOVELTY_BOUNDARY:DSPyPolicy"
    assert hypergraph.observations == []


def test_refuses_unknown_planner_and_never_mutates_hypergraph() -> None:
    hypergraph = PayoffHypergraph()
    result = admit_dflss_solve_payoff("Astar", "NotARealPlanner", hypergraph=hypergraph)

    assert not result.admitted
    assert result.standing == "REFUSED"
    assert result.reason == "REFUSED:UNKNOWN_PLANNER:NotARealPlanner"
    assert result.right_outcome.reason == "REFUSED:UNKNOWN_PLANNER:NotARealPlanner"
    assert hypergraph.observations == []


def test_receipt_id_is_a_real_deterministic_digest_over_the_real_outcomes() -> None:
    hypergraph_a = PayoffHypergraph()
    hypergraph_b = PayoffHypergraph()

    result_a = admit_dflss_solve_payoff("Astar", "CIDual", hypergraph=hypergraph_a)
    result_b = admit_dflss_solve_payoff("Astar", "CIDual", hypergraph=hypergraph_b)

    assert result_a.observation is not None
    assert result_b.observation is not None
    assert result_a.observation.receipt_id == result_b.observation.receipt_id
