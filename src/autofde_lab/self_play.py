# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Self-play rollout utility for the real, registered RockPaperScissors domain.

This module runs actual episodes of the multi-agent, symmetric
`autofde_lab.hub.domain.rock_paper_scissors.RockPaperScissors` domain against
itself. By default it uses the built-in uniform-random policy provided by
`autofde_lab.utils.rollout` (solver=None); pass any real solver instance (e.g.
`autofde_lab.hub.solver.dspy_policy.DSPyPolicy`) to drive self-play with that
policy instead. All numbers returned by `self_play_rollout` are derived from
the real rewards produced by those rollouts -- nothing here is mocked,
stubbed, or fabricated.
"""

from __future__ import annotations

import random
from typing import Any, Optional

from autofde_lab.hub.domain.rock_paper_scissors import RockPaperScissors
from autofde_lab.utils import rollout

__all__ = ["self_play_rollout"]


def self_play_rollout(
    num_episodes: int = 20,
    max_steps: int = 1,
    seed: Optional[int] = None,
    solver: Optional[Any] = None,
) -> dict:
    """Run real self-play episodes of RockPaperScissors and summarize outcomes.

    Instantiates the real `RockPaperScissors` domain (two agents,
    "player1" and "player2") and rolls it out against itself using the
    uniform-random policy built into `autofde_lab.utils.rollout` (solver=None).

    # Parameters
    num_episodes: number of real episodes to actually run.
    max_steps: maximum number of steps allowed per episode (also used as the
        domain's `max_moves`, so terminal conditions from the domain itself
        and from the rollout step cap agree).
    seed: optional seed passed to Python's global `random` module before
        rollout starts. NOTE: the domain's action spaces are gymnasium
        `Discrete` spaces sampled through their own lazily-created internal
        RNG, which is *not* driven by `random.seed()`/`numpy.random.seed()`.
        Passing the same `seed` twice is therefore NOT guaranteed to
        reproduce identical action sequences -- this has been verified
        empirically, not assumed. The seed is accepted and applied on a
        best-effort basis (it does affect any tie-break/bookkeeping code
        that does use the global `random` module), but no determinism claim
        is made about the resulting episode outcomes.
    solver: an already-constructed real solver instance to drive both agents'
        moves (e.g. a `DSPyPolicy` solver already `.solve()`-d against a
        domain factory for this domain). If None (default), rollout's
        built-in uniform-random policy is used, matching prior behavior.

    # Returns
    A dict with only real, observable data:
        - "num_episodes_run": int, number of episodes actually executed.
        - "total_steps": int, sum of real steps taken across all episodes.
        - "max_steps": the max_steps bound that was enforced.
        - "outcomes": {agent: {"win": int, "loss": int, "draw": int}} real
          per-agent tallies, computed from the actual cumulative reward each
          agent received in each episode (RockPaperScissors emits
          `Value(reward=..., cost=...)` per agent per step; the per-episode
          outcome is decided by the sign of the summed real reward).
        - "episode_returns": list of {agent: int} real cumulative rewards,
          one dict per episode actually run.
    """
    if seed is not None:
        random.seed(seed)

    domain = RockPaperScissors(max_moves=max_steps)
    agents = sorted(domain.get_agents())

    episodes = rollout(
        domain,
        solver=solver,
        num_episodes=num_episodes,
        max_steps=max_steps,
        render=False,
        verbose=False,
        return_episodes=True,
    )
    if episodes is None:
        # rollout() only returns None when return_episodes=False; guard this
        # real invariant explicitly rather than assuming it for the type checker.
        raise RuntimeError(
            "rollout() returned None despite return_episodes=True; "
            "autofde_lab.utils.rollout's contract must have changed."
        )

    outcomes = {agent: {"win": 0, "loss": 0, "draw": 0} for agent in agents}
    episode_returns = []
    total_steps = 0

    for _observations, actions, values in episodes:
        num_steps = len(actions)
        total_steps += num_steps

        cumulative_reward = {agent: 0 for agent in agents}
        for step_values in values:
            for agent in agents:
                cumulative_reward[agent] += step_values[agent].reward

        episode_returns.append(dict(cumulative_reward))

        # Two-agent zero-sum-ish game: classify each agent's outcome from
        # the sign of its own real cumulative reward for this episode.
        for agent in agents:
            r = cumulative_reward[agent]
            if r > 0:
                outcomes[agent]["win"] += 1
            elif r < 0:
                outcomes[agent]["loss"] += 1
            else:
                outcomes[agent]["draw"] += 1

    return {
        "num_episodes_run": len(episodes),
        "total_steps": total_steps,
        "max_steps": max_steps,
        "outcomes": outcomes,
        "episode_returns": episode_returns,
    }
