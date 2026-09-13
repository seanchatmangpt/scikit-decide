# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test, per this repo's test
taxonomy): prerequisite-ordered attacker knowledge, solved by Astar over a
local in-memory domain modelling `vendor/gyms/kubernetes-goat` scenario 16
("RBAC least privileges misconfiguration").

This is a real domain (`K8sGoatRBACEscalation`) constructed in-process and
a real registered `Astar` solver's real `solve()` call -- no
`unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`. Nothing here talks to a live
Kubernetes cluster or mounts a real ServiceAccount token; the domain models
the documented walkthrough
(`vendor/gyms/kubernetes-goat/guide/docs/scenarios/scenario-16/scenario-16.md`),
it does not actuate against one.
"""

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.k8s_goat_rbac_escalation import K8sGoatRBACEscalation
from autofde_lab.hub.domain.k8s_goat_rbac_escalation.k8s_goat_rbac_escalation import (
    DEFAULT_STEPS,
    GOAL_STEP_ID,
)


@pytest.fixture
def rbac_domain():
    return K8sGoatRBACEscalation()


def test_astar_recovers_documented_scenario16_flag_step_order(rbac_domain):
    """A* must reach a goal state that has performed the flag-recovering step."""
    Astar = utils.load_registered_solver("Astar")
    domain = rbac_domain
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

        # (a) goal reached -- the flag-recovering step was actually performed
        assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
        assert GOAL_STEP_ID in obs.known
        assert GOAL_STEP_ID == plan[-1], (
            f"expected the flag-recovering step to be the final action, got plan: {plan}"
        )

        # (b) no step performed before its documented prerequisite -- the
        # actual walkthrough-ordering invariant under test.
        steps_by_id = {s.id: s for s in DEFAULT_STEPS}
        performed_so_far: set[str] = set()
        for step_id in plan:
            step = steps_by_id[step_id]
            assert set(step.prerequisite_ids).issubset(performed_so_far), (
                f"step {step_id!r} performed before its prerequisites "
                f"{step.prerequisite_ids!r}; performed so far: {performed_so_far!r}"
            )
            performed_so_far.add(step_id)

        # (c) the exact documented walkthrough sequence, since every step
        # here is on the critical path to the flag except the pointless
        # `list_namespace_pods` distractor, which a cost-optimal solver
        # must never route through.
        assert plan == [
            "read_serviceaccount_files",
            "resolve_apiserver_env",
            "authenticate_to_apiserver",
            "list_namespace_secrets",
            "read_and_decode_k8svaultapikey",
        ]
        assert "list_namespace_pods" not in plan

        # (d) cost-optimality: 5 unit-cost steps, no wasted moves.
        total_cost = sum(steps_by_id[step_id].cost for step_id in plan)
        assert total_cost == pytest.approx(5.0)
