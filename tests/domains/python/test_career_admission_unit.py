# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): prerequisite-ordered
admission solved by Astar over a local in-memory domain.

SCOPE WARNING -- read before citing this test as evidence of anything:

    This test exercises ONE solver against ONE locally-defined domain whose
    facts are hard-coded in this repository. It does NOT touch mfw, ggen,
    ggen-create, or ggen-legacy. It manufactures nothing, admits nothing,
    receipts nothing, and verifies nothing independently. It is an ANALOGY
    to the Chatman manufacturing law, not an exercise of it.

    Passing here supports exactly one claim: autofde_lab's Astar computes a
    cost-optimal, prerequisite-respecting order over this domain. It is not
    evidence for any cross-repository or ecosystem standing claim.

    The ecosystem-level test is tests/ecosystem/test_chatman_chain_chicago.py
    and per-stage standing is recorded in docs/ecosystem-standing.md.

What is actually verified below: real domain
(autofde_lab.hub.domain.career_admission.CareerAdmission), real registered
solver (Astar via autofde_lab.utils), real rollout, no mocks -- an action
admitting a fact is inapplicable until that fact's prerequisites are
admitted, and the solver finds the cost-optimal order, not merely a
feasible one.
"""

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.career_admission import CareerAdmission
from autofde_lab.hub.domain.career_admission.career_admission import DEFAULT_FACTS


@pytest.fixture
def career_domain():
    return CareerAdmission()


def test_astar_computes_cost_optimal_prerequisite_order(career_domain):
    """A* must reach a goal state admitting all required categories."""
    Astar = utils.load_registered_solver("Astar")
    domain = career_domain
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan = []
        for _ in range(20):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            outcome = domain.step(action)
            obs = outcome.observation

        # (a) goal reached
        assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"

        # (b) no fact admitted before its prerequisite -- the actual
        # chicken-and-egg invariant under test.
        facts_by_id = {f.id: f for f in DEFAULT_FACTS}
        admitted_so_far: set[str] = set()
        for fact_id in plan:
            fact = facts_by_id[fact_id]
            assert set(fact.prerequisite_ids).issubset(admitted_so_far), (
                f"Fact {fact_id!r} admitted before its prerequisites {fact.prerequisite_ids}. "
                f"Plan so far: {plan}"
            )
            admitted_so_far.add(fact_id)

        # (c) cost-optimality: Astar must prefer the cheap governance fact
        # (intuit_ml_governance, cost=1.0) over the reachable-but-redundant
        # expensive alternative (redundant_expensive_governance, cost=5.0)
        # for the same "governance" category requirement.
        assert "redundant_expensive_governance" not in plan, (
            f"A* chose the suboptimal (cost=5.0) governance fact instead of the "
            f"cheaper (cost=1.0) equivalent. Plan: {plan}"
        )
        total_cost = sum(facts_by_id[fact_id].cost for fact_id in plan)
        known_optimal_cost = 1.0 + 1.0 + 1.0  # intuit_automl + agentic_orchestration + intuit_ml_governance
        assert total_cost == pytest.approx(known_optimal_cost), (
            f"Plan cost {total_cost} != known-optimal cost {known_optimal_cost}. Plan: {plan}"
        )
