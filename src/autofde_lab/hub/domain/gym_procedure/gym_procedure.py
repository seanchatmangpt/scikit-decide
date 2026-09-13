# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Generic STRIPS-lite planning domain factory over a gym's own documented procedure.

The five gym domains added earlier this session (``terragoat``,
``k8s_goat_rbac_escalation``, ``azuregoat_privesc``, ``cloudgoat_iam_privesc``,
``fix_git``) independently converged on the same shape: state = frozenset of
facts held, action = one documented step from the gym's own walkthrough,
gated on a precondition fact-set and establishing one new fact, goal = a
target fact (or fact-set) reached. That convergence is itself evidence the
reduction is mechanical, not bespoke per gym.

``GymProcedureDomain`` makes that reduction reusable: instead of writing a
new ``DeterministicPlanningDomain`` subclass per gym, a gym is reduced to a
small **recipe** — a list of ``Step`` records (id, description,
preconditions, establishes, optional cost) plus an initial fact-set and a
goal fact-set — expressed as plain Python or loaded from JSON via
:func:`load_recipe`. The domain itself is generic; only the recipe is
gym-specific, and the recipe is exactly the content a human (or an agent)
transcribes directly from a gym's own README/walkthrough/solve-script — no
planning-domain boilerplate to author per gym.

This does not weaken the "real domain, real solve()" standard: the same
``Astar`` solver runs against the same precondition-gated fact-set search
space as the five bespoke domains before it. What changes is only how much
code a new gym costs to add.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Optional

from autofde_lab import D, DeterministicPlanningDomain, Space, Value
from autofde_lab.core import ImplicitSpace
from autofde_lab.hub.space.gym import ListSpace


@dataclass(frozen=True)
class Step:
    """One documented step transcribed from a real gym walkthrough/solve script."""

    id: str
    description: str
    preconditions: frozenset[str] = field(default_factory=frozenset)
    establishes: frozenset[str] = field(default_factory=frozenset)
    removes: frozenset[str] = field(default_factory=frozenset)
    cost: float = 1.0
    source: str = ""  # e.g. "README.md step 3" / "solve.sh line 12" — provenance, not behavior


@dataclass(frozen=True)
class Recipe:
    """A gym reduced to facts + steps: exactly what a human transcribes by hand."""

    gym: str
    task: str
    source_ref: str  # path/URL to the real walkthrough this was transcribed from
    initial_facts: frozenset[str]
    goal_facts: frozenset[str]
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        if not self.steps and not (self.goal_facts <= self.initial_facts):
            # A genuinely empty procedure is only valid when the goal is
            # ALREADY, verifiably true at the initial state (e.g. a task
            # whose real success condition is established by passive
            # environment/infrastructure behavior, not by any agent
            # action -- confirmed real case: Harbor's environment-env-multi
            # task, whose own instruction.md is literally "Do nothing").
            # This is not a loophole: an empty-steps Recipe whose
            # goal_facts is NOT already a subset of initial_facts is still
            # rejected here, and would anyway fail to solve (no action
            # exists to reach an unmet goal), so this cannot be used to
            # fake success on a task that actually requires real steps.
            raise ValueError(
                f"Recipe {self.gym!r}/{self.task!r} has no steps and goal_facts "
                f"is not already satisfied by initial_facts -- an empty procedure "
                f"is only valid when the goal genuinely holds without any agent action"
            )
        if not self.goal_facts:
            raise ValueError(f"Recipe {self.gym!r}/{self.task!r} has no goal_facts")
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Recipe {self.gym!r}/{self.task!r} has duplicate step ids: {ids}")


def load_recipe(path: Path) -> Recipe:
    """Load a :class:`Recipe` from a JSON file with the shape::

        {
          "gym": "...", "task": "...", "source_ref": "...",
          "initial_facts": ["..."], "goal_facts": ["..."],
          "steps": [
            {"id": "...", "description": "...", "preconditions": ["..."],
             "establishes": ["..."], "removes": [], "cost": 1.0, "source": "..."}
          ]
        }
    """
    data = json.loads(Path(path).read_text())
    steps = tuple(
        Step(
            id=s["id"],
            description=s["description"],
            preconditions=frozenset(s.get("preconditions", [])),
            establishes=frozenset(s.get("establishes", [])),
            removes=frozenset(s.get("removes", [])),
            cost=float(s.get("cost", 1.0)),
            source=s.get("source", ""),
        )
        for s in data["steps"]
    )
    return Recipe(
        gym=data["gym"],
        task=data["task"],
        source_ref=data["source_ref"],
        initial_facts=frozenset(data.get("initial_facts", [])),
        goal_facts=frozenset(data["goal_facts"]),
        steps=steps,
    )


class State(NamedTuple):
    facts: frozenset[str]


class D_(
    DeterministicPlanningDomain,
):
    T_state = State
    T_observation = T_state
    T_event = str  # step id
    T_value = float
    T_predicate = bool
    T_info = None


class GymProcedureDomain(D_):
    """A precondition-gated fact-set planning problem built from a :class:`Recipe`.

    Generic over any gym reducible to "facts held -> facts reached via gated
    steps" — the shape every prior gym domain in this repo already used.
    """

    def __init__(self, recipe: Recipe) -> None:
        self.recipe = recipe
        self._by_id = {s.id: s for s in recipe.steps}

    @classmethod
    def from_json(cls, path: Path) -> "GymProcedureDomain":
        return cls(load_recipe(path))

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        step = self._by_id[action]
        return State(facts=(memory.facts - step.removes) | step.establishes)

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=self._by_id[action].cost)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(sorted(self._by_id))

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(
            sorted(
                step.id
                for step in self.recipe.steps
                if step.preconditions <= memory.facts
                and not step.establishes <= memory.facts
            )
        )

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        goal_facts = self.recipe.goal_facts
        return ImplicitSpace(lambda s: goal_facts <= s.facts)

    def _get_initial_state_(self) -> D.T_state:
        return State(facts=self.recipe.initial_facts)

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace([State(facts=self.recipe.goal_facts)])

    def describe_step(self, step_id: str) -> Step:
        """Look up the real transcribed Step (description + provenance) behind an action id."""
        return self._by_id[step_id]
