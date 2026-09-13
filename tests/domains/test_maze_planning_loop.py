# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school (classicist) test for a real planning solve loop.

Drives the real, shipped `Maze` domain (skdecide.hub.domain.maze.maze.Maze)
through a real `Astar` solver (the pure-Python `pAstar` entry point) end to
end: `solve()` followed by a manual reset/sample_action/step loop until the
goal is reached. No mocks or hand-rolled domain doubles are used anywhere in
this file -- every object is a real skdecide domain/solver collaborator, and
assertions are made on the actual resulting state, plan and cost, per this
repo's Chicago-school test convention (see
tests/solvers/python/test_python_solvers.py and
tests/test_self_play_dspy_all_domains_chicago.py).
"""

from __future__ import annotations

from skdecide.hub.domain.maze.maze import Maze
from skdecide.hub.solver.p_astar import Astar

MAX_STEPS = 200  # generous upper bound; Maze's DEFAULT_MAZE solves well under this


def get_plan(domain, solver, max_steps=MAX_STEPS):
    """Run a real solve loop: reset, then repeatedly ask the solver for an
    action and step the domain until the goal is reached or max_steps is hit.

    Mirrors the get_plan() helper duplicated across this repo's other solver
    tests (tests/solvers/python/test_python_solvers.py,
    tests/solvers/cpp/test_lrtdp.py, tests/solvers/cpp/test_cpp_solvers.py).
    """
    plan = []
    cost = 0
    observation = domain.reset()
    nb_steps = 0
    while (not domain.is_goal(observation)) and nb_steps < max_steps:
        plan.append(solver.sample_action(observation, domain=domain))
        outcome = domain.step(plan[-1])
        cost += outcome.value.cost
        observation = outcome.observation
        nb_steps += 1
    return plan, cost, observation


def test_solve_maze_reaches_goal():
    """Real Maze domain + real Astar solver, solved end to end.

    Astar with the default zero heuristic is uniform-cost search, so for a
    deterministic, positive-cost domain like Maze it returns a genuinely
    optimal plan. The test asserts on real, observed outcomes: the domain's
    own goal check, a bounded plan length, and a positive real cost -- not on
    hardcoded/guessed numeric constants.
    """
    domain = Maze()

    assert Astar.check_domain(domain)

    with Astar(domain_factory=Maze, verbose=False) as solver:
        solver.solve()
        plan, cost, final_observation = get_plan(domain, solver)

    # Reached the actual goal state, not just "loop exhausted".
    assert domain.is_goal(final_observation)

    # Real, observed plan/cost bounds (not internal solver state).
    assert 0 < len(plan) <= MAX_STEPS
    assert cost > 0
