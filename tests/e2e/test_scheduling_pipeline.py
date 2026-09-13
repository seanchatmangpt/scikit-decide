# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school pipeline tests for the scheduling (RCPSP) domain family.

Real load_registered_domain('RCPSP') + load_registered_solver(...) +
check_domain + solve + rollout, no mocks or stubs. tests/scheduling/ already
owns deep domain-internal correctness (precedence, resources, time windows,
...); this file only proves the registration-mechanism pipeline for a
representative scheduling instance, paired first with the lightweight, pure
-Python PilePolicy solver and then with DOSolver (backed by
discrete-optimization).
"""

from skdecide.builders.domain.scheduling.scheduling_domains_modelling import (
    rebuild_tasks_complete_details_dict,
)
from skdecide.hub.solver.do_solver.do_solver_scheduling import DOSolver, SolvingMethod
from skdecide.hub.solver.do_solver.sgs_policies import (
    BasePolicyMethod,
    PolicyMethodParams,
)

from skdecide import rollout, utils

from .conftest import requires_discrete_optimization

pytestmark = requires_discrete_optimization

# A small, real 5-task precedence graph (start -> {2,3} -> 4 -> end, 3 -> end)
# with a known-solvable resource profile -- the same toy instance shape used
# by tests/scheduling/test_scheduling.py's ToyRCPSPDomain, expressed in the
# constructor format the registered RCPSP domain expects.
_TASKS_MODE = {
    1: {1: {"duration": 0, "r1": 0, "r2": 0}},
    2: {1: {"duration": 5, "r1": 1, "r2": 1}},
    3: {1: {"duration": 6, "r1": 1, "r2": 0}},
    4: {1: {"duration": 4, "r1": 2, "r2": 1}},
    5: {1: {"duration": 0, "r1": 0, "r2": 0}},
}
_SUCCESSORS = {1: [2, 3], 2: [4], 3: [5], 4: [5], 5: []}
_RESOURCE_NAMES = ["r1", "r2"]
_RESOURCE_AVAILABILITY = {"r1": 2, "r2": 1}
_RESOURCE_RENEWABLE = {"r1": True, "r2": True}
_MAX_HORIZON = 50


def _make_rcpsp_domain():
    RCPSPDomain = utils.load_registered_domain("RCPSP")
    domain = RCPSPDomain(
        tasks_mode=_TASKS_MODE,
        max_horizon=_MAX_HORIZON,
        successors=_SUCCESSORS,
        resource_names=_RESOURCE_NAMES,
        resource_availability=_RESOURCE_AVAILABILITY,
        resource_renewable=_RESOURCE_RENEWABLE,
    )
    domain.set_inplace_environment(False)
    return domain


def _assert_real_schedule_completes_every_task(domain, states):
    tasks_complete_dict = rebuild_tasks_complete_details_dict(states[-1])
    assert set(tasks_complete_dict) == set(domain.get_tasks_ids())
    makespan = max(tasks_complete_dict[t].end for t in tasks_complete_dict)
    # a real, finite, non-trivial schedule -- not an immediately-terminated
    # rollout, and not exceeding the declared horizon
    assert 0 < makespan <= _MAX_HORIZON


def test_real_rcpsp_pilepolicy_pipeline_smoke():
    """Lightweight: PilePolicy is pure Python, no MiniZinc/CP backend
    required -- safe to run wherever discrete-optimization is installed.
    """
    PilePolicySolver = utils.load_registered_solver("PilePolicy")
    domain = _make_rcpsp_domain()
    state = domain.get_initial_state()

    assert PilePolicySolver.check_domain(domain)

    solver = PilePolicySolver(domain_factory=lambda: domain)
    solver.solve()
    states, actions, values = rollout(
        domain=domain,
        max_steps=1000,
        solver=solver,
        from_memory=state,
        action_formatter=None,
        outcome_formatter=None,
        verbose=False,
        return_episodes=True,
    )[0]

    assert len(actions) > 0
    _assert_real_schedule_completes_every_task(domain, states)


def test_real_rcpsp_dosolver_pipeline():
    """Full DOSolver pipeline: representative of the heavier
    discrete-optimization-backed solve path already exercised at the
    domain-internal level by tests/scheduling/test_scheduling.py, here
    proven through the real load_registered_domain/load_registered_solver
    pipeline instead of hand-imported classes.
    """
    DOSolverSolver = utils.load_registered_solver("DOSolver")
    assert DOSolverSolver is DOSolver

    domain = _make_rcpsp_domain()
    state = domain.get_initial_state()

    solver = DOSolverSolver(
        domain_factory=lambda: domain,
        policy_method_params=PolicyMethodParams(
            base_policy_method=BasePolicyMethod.SGS_PRECEDENCE,
            delta_index_freedom=0,
            delta_time_freedom=0,
        ),
        method=SolvingMethod.PILE,
    )
    assert solver.check_domain(domain)
    solver.solve()
    states, actions, values = rollout(
        domain=domain,
        max_steps=1000,
        solver=solver,
        from_memory=state,
        action_formatter=None,
        outcome_formatter=None,
        verbose=False,
        return_episodes=True,
    )[0]

    assert len(actions) > 0
    _assert_real_schedule_completes_every_task(domain, states)
