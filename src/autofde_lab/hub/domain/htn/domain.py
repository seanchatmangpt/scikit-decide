# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""HTNDomain: this repo's own HTN planning domain.

Not a wrapped external solver -- up-siadex is BLOCKED (real import failures
against pinned unified-planning 1.2.0: missing ``pkg_resources`` compensating
dependency, and ``unified_planning.io.hpdl`` does not exist in 1.2.0's real
submodule list). See ``autofde_lab.hub.domain.htn.planner`` for the
from-scratch total-order HTN decomposition algorithm this domain runs.

``HTNDomain`` parses an HDDL domain (and optional problem) file with
``unified_planning.io.PDDLReader().parse_problem`` -- the exact call
confirmed working against real bundled unified-planning HTN fixtures and
against a hand-authored ``verify-and-commit`` HDDL problem in this module's
tests -- and wraps the returned ``HierarchicalProblem`` directly. The
``HierarchicalProblem`` object is the single source of truth for static
domain structure (tasks, methods, actions, objects, initial state); this
class does not re-declare that structure in a second schema (no dual
bookkeeping).

Because a *total-order* HTN network has, by definition, exactly one intended
execution schedule once resolved, this domain resolves the whole schedule up
front via ``HTNTotalOrderPlanner.solve()`` and exposes it as a deterministic
sequence of primitive-action transitions through the standard
``DeterministicPlanningDomain`` protocol (mirroring the same protocol
methods ``autofde_lab.hub.domain.pddl.domain.PDDLDomain`` implements):
``_get_initial_state_``, ``_get_next_state``, ``_get_applicable_actions_from``,
``_get_goals_``, ``_is_terminal``, ``_get_action_space_``,
``_get_observation_space_``. There is no C++ HTN backend in this repo
(confirmed absence) -- state here is pure Python (a frozenset of ground
atoms plus a plan cursor), not a C++-backed state object.
"""

from __future__ import annotations

from typing import Optional

from unified_planning.io import PDDLReader

from autofde_lab import (
    DeterministicPlanningDomain,
    ImplicitSpace,
    Space,
    Value,
)
from autofde_lab.builders.domain import UnrestrictedActions
from autofde_lab.core import D
from autofde_lab.hub.domain.htn.planner import GroundAction, HTNTotalOrderPlanner
from autofde_lab.hub.space.gym import ListSpace


class HTNState:
    """Immutable, hashable HTN domain state: the real ground-atom set after
    executing `step` primitive actions of the pre-solved total-order plan."""

    __slots__ = ("atoms", "step")

    def __init__(self, atoms: frozenset, step: int):
        self.atoms = atoms
        self.step = step

    def __hash__(self):
        return hash((self.atoms, self.step))

    def __eq__(self, other):
        return (
            isinstance(other, HTNState)
            and self.atoms == other.atoms
            and self.step == other.step
        )

    def __repr__(self):  # pragma: no cover - cosmetic
        return f"HTNState(step={self.step}, atoms={sorted(self.atoms)})"


class HTNDomain(DeterministicPlanningDomain, UnrestrictedActions):
    """Deterministic total-order HTN planning domain, backed by this repo's
    own ``HTNTotalOrderPlanner`` (not up-siadex, not any wrapped external
    HTN solver).

    # Parameters
    domain_path: Path to the HDDL domain file.
    problem_path: Optional path to the HDDL problem file (initial state +
        initial task network). If omitted, `domain_path` must itself parse
        to a full problem (matching `PDDLReader.parse_problem`'s own
        single-argument behavior).
    """

    T_state = HTNState
    T_observation = T_state
    T_event = GroundAction

    def __init__(self, domain_path: str, problem_path: Optional[str] = None):
        reader = PDDLReader()
        if problem_path is not None:
            self._problem = reader.parse_problem(domain_path, problem_path)
        else:
            self._problem = reader.parse_problem(domain_path)
        self._planner = HTNTotalOrderPlanner(self._problem)
        self._initial_atoms = self._planner.initial_state()
        # Real solve, run once at construction time -- this is the actual
        # from-scratch HTN decomposition search, not a stub.
        self._plan = self._planner.solve()

    @property
    def problem(self):
        return self._problem

    @property
    def plan(self) -> list:
        """The full flattened total-order primitive-action plan computed by
        HTNTotalOrderPlanner.solve() at construction time."""
        return list(self._plan)

    def _get_initial_state_(self) -> D.T_state:
        return HTNState(self._initial_atoms, 0)

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        expected = self._plan[memory.step]
        assert action == expected, (
            f"HTNDomain is a resolved total-order schedule: expected "
            f"{expected!r} at step {memory.step}, got {action!r}"
        )
        act_def = self._problem.action(action.name)
        from autofde_lab.hub.domain.htn.planner import _apply_effects

        bindings = {p.name: arg for p, arg in zip(act_def.parameters, action.args)}
        next_atoms = _apply_effects(act_def, bindings, memory.atoms)
        return HTNState(next_atoms, memory.step + 1)

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=1.0)

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        if memory.step >= len(self._plan):
            return ListSpace([])
        return ListSpace([self._plan[memory.step]])

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(lambda s: s.step >= len(self._plan))

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return state.step >= len(self._plan)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ImplicitSpace(lambda a: isinstance(a, GroundAction))

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(lambda s: isinstance(s, HTNState))
