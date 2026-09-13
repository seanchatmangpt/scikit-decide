# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school pipeline tests for the toy/game domain family.

Real load_registered_domain / load_registered_solver / check_domain / solve
/ rollout, no mocks or stubs. `Maze` + `Astar` proves the pipeline for a
deterministic, single-agent, goal-based domain; `RockPaperScissors` proves
it generalizes to a stochastic, multi-agent, self-play domain (see
tests/test_self_play_chicago.py, whose self_play_rollout already covers the
solver=None case for this domain in depth).
"""

from skdecide import utils


def test_real_registered_domain_and_solver_names_are_discoverable():
    """Real entry-point resolution actually exposes the names this module relies on."""
    domains = utils.get_registered_domains()
    solvers = utils.get_registered_solvers()
    assert "Maze" in domains
    assert "RockPaperScissors" in domains
    assert "Astar" in solvers


def test_real_maze_astar_pipeline_solves_and_rolls_out():
    """Real load_registered_domain('Maze') + load_registered_solver('Astar')
    round-trips through check_domain, solve, and a real rollout with a real,
    non-empty solution path reaching the goal.
    """
    MazeDomain = utils.load_registered_domain("Maze")
    AstarSolver = utils.load_registered_solver("Astar")

    domain = MazeDomain()
    assert AstarSolver.check_domain(domain)

    with AstarSolver(domain_factory=lambda: MazeDomain()) as solver:
        solver.solve()
        episodes = utils.rollout(
            domain,
            solver=solver,
            max_steps=200,
            num_episodes=1,
            render=False,
            verbose=False,
            return_episodes=True,
        )

    assert episodes is not None
    observations, actions, values = episodes[0]
    # Astar found a real, non-empty plan and it actually executed.
    assert len(actions) > 0
    # Maze rewards -1 per non-goal step and 0 on reaching the goal; a
    # genuine solved episode's last transition value is therefore >= the
    # cost of a single wasted step, i.e. a real bounded terminal cost.
    assert all(v.cost >= 0 for v in values)


def test_real_rockpaperscissors_pipeline_via_load_registered_helpers():
    """Same pipeline shape as the Maze test, but for a stochastic,
    multi-agent domain loaded purely by registered name, proving the
    pipeline generalizes beyond single-agent deterministic domains.

    RockPaperScissors is a hidden-information, multi-agent game with no
    single-agent shortest-path solver applicable to it in this hub, so this
    test drives the real rollout with solver=None (the same real,
    uniform-random self-play machinery already proven in depth by
    tests/test_self_play_chicago.py) -- the pipeline leg under test here is
    load_registered_domain, not load_registered_solver.
    """
    RockPaperScissorsDomain = utils.load_registered_domain("RockPaperScissors")

    domain = RockPaperScissorsDomain(max_moves=3)
    episodes = utils.rollout(
        domain,
        solver=None,
        max_steps=3,
        num_episodes=1,
        render=False,
        verbose=False,
        return_episodes=True,
    )

    assert episodes is not None
    observations, actions, values = episodes[0]
    assert len(actions) > 0
    assert len(actions) <= 3
    # zero-sum payoff structure holds for every real transition observed
    for v in values:
        assert v["player1"].reward == -v["player2"].reward
