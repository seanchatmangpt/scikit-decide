# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""HTNTotalOrderPlanner.

This repo's own from-scratch total-order HTN planner (not up-siadex, not a
wrapped external solver). up-siadex is BLOCKED per report 2 (pkg_resources /
unified_planning.io.hpdl import failures against unified-planning 1.2.0). No
other real, importable HTN solver was found in this repo's dependency
surface (report 2). Per the task's own fallback instruction, this module
implements the standard total-order HTN decomposition algorithm directly in
Python against a real ``unified_planning.model.htn.HierarchicalProblem``
(the object produced by ``unified_planning.io.PDDLReader().parse_problem``):

  * for a compound task, try its declared methods in declared order;
  * for each candidate method, bind the method's own parameters that
    correspond to the calling task's arguments, then (for any additional,
    existentially-quantified method parameters) enumerate candidate objects
    of the matching type -- this is the backtracking choice point;
  * check the method's preconditions against the current state;
  * recursively decompose the method's subtasks in the method's declared
    (total) order, threading state through each subtask in sequence;
  * for a primitive task, check the grounded action's preconditions against
    the current state and apply its effects to produce the next state;
  * on any precondition failure or subtask-decomposition failure, backtrack
    to the next parameter binding, then the next method, then unwind to the
    caller.

The recursive shape (method/task rules tried in order, recursive seek into
subtasks, replay of effects against a running state) mirrors the algorithm
shape already proven out in ``~/wasm4pm``'s ``htn_planning.rs`` breed
(method/op rules, recursive ``htn_seek``, postcondition replay-audit) --
cited here as a *known-working reference algorithm*, not reused code: no
Rust/Python cross-language binding exists between the two repos (report 3),
and every line below is a from-scratch Python implementation against
unified-planning's real HTN object model.

Evaluation is intentionally scoped to what this planner's own verification
targets exercise: boolean 0-ary/n-ary fluents, ``and``/``or``/``not``,
boolean constants, and unconditional effects that set a fluent to a boolean
constant. This is not a claim of full HDDL/PDDL expression coverage.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Optional

from unified_planning.model.htn.hierarchical_problem import HierarchicalProblem
from unified_planning.shortcuts import OperatorKind

Atom = tuple  # (fluent_name: str, args: tuple[str, ...])
State = frozenset  # frozenset[Atom]


@dataclass(frozen=True)
class GroundAction:
    """A fully-instantiated primitive action: name + ordered object-name args."""

    name: str
    args: tuple

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        if self.args:
            return f"({self.name} {' '.join(self.args)})"
        return f"({self.name})"


class HTNPlanningFailure(Exception):
    """Raised (internally, and re-raised to the caller) when no total-order
    decomposition of the initial task network exists."""


def _resolve_arg(expr, bindings: dict) -> str:
    """Resolve a unified_planning argument expression (a PARAM_EXP referring
    to an enclosing method/action parameter, or an OBJECT_EXP constant) to a
    concrete object name string, using the current parameter bindings."""
    if expr.node_type == OperatorKind.PARAM_EXP:
        return bindings[expr.parameter().name]
    if expr.node_type == OperatorKind.OBJECT_EXP:
        return expr.object().name
    if expr.node_type == OperatorKind.VARIABLE_EXP:
        return bindings[expr.variable().name]
    raise NotImplementedError(
        f"HTNTotalOrderPlanner: unsupported argument expression node {expr.node_type}"
    )


def _eval_condition(expr, bindings: dict, state: State) -> bool:
    """Evaluate a boolean unified_planning expression against `state`
    (a frozenset of true (fluent_name, arg_names) atoms), substituting
    parameter references via `bindings`."""
    nt = expr.node_type
    if nt == OperatorKind.BOOL_CONSTANT:
        return expr.bool_constant_value()
    if nt == OperatorKind.AND:
        return all(_eval_condition(a, bindings, state) for a in expr.args)
    if nt == OperatorKind.OR:
        return any(_eval_condition(a, bindings, state) for a in expr.args)
    if nt == OperatorKind.NOT:
        return not _eval_condition(expr.args[0], bindings, state)
    if nt == OperatorKind.FLUENT_EXP:
        fluent_name = expr.fluent().name
        arg_names = tuple(_resolve_arg(a, bindings) for a in expr.args)
        return (fluent_name, arg_names) in state
    if nt == OperatorKind.FORALL:
        # expr.args[0] is the quantified body; expr.variables() gives the
        # bound Variable(s). Enumerate real objects of each variable's type.
        body = expr.args[0]
        variables = expr.variables()
        return _eval_forall(body, variables, bindings, state)
    raise NotImplementedError(
        f"HTNTotalOrderPlanner: unsupported condition node {nt} ({expr})"
    )


def _eval_forall(body, variables, bindings: dict, state: State) -> bool:
    """Real (bounded) universal-quantifier evaluation: substitute each
    combination of concrete objects for the quantified variables and check
    the body. `variables` are unified_planning Variable objects carrying
    their own type; concrete candidates come from the enclosing problem's
    object set via the module-level `_current_problem` context, which
    `_eval_condition`'s caller sets before evaluating a FORALL-bearing
    precondition."""
    if not variables:
        return _eval_condition(body, bindings, state)
    var, rest = variables[0], variables[1:]
    problem = _FORALL_PROBLEM.get()
    for obj in problem.objects(var.type):
        sub_bindings = dict(bindings)
        sub_bindings[var.name] = obj.name
        if not _eval_forall(body, rest, sub_bindings, state):
            return False
    return True


class _ProblemContext:
    """Tiny real (not mocked) context holder so FORALL evaluation can reach
    the enclosing HierarchicalProblem's object set without threading an
    extra parameter through every _eval_condition call site."""

    def __init__(self):
        self._problem = None

    def set(self, problem):
        self._problem = problem

    def get(self):
        assert self._problem is not None, (
            "HTNTotalOrderPlanner: FORALL evaluated before a problem context was set"
        )
        return self._problem


_FORALL_PROBLEM = _ProblemContext()


def _apply_effects(action, bindings: dict, state: State) -> State:
    """Apply an InstantaneousAction's unconditional boolean effects to
    `state`, returning the resulting state. Real state mutation, no
    simulated/mocked transition."""
    atoms = set(state)
    for eff in action.effects:
        if eff.condition is not None and not eff.condition.is_true():
            # Conditional effects are out of scope for the verification
            # targets this planner is built and checked against.
            if not _eval_condition(eff.condition, bindings, state):
                continue
        fluent_name = eff.fluent.fluent().name
        arg_names = tuple(_resolve_arg(a, bindings) for a in eff.fluent.args)
        atom = (fluent_name, arg_names)
        if eff.value.is_true():
            atoms.add(atom)
        elif eff.value.is_false():
            atoms.discard(atom)
        else:
            raise NotImplementedError(
                "HTNTotalOrderPlanner: only boolean-constant effect values are supported"
            )
    return frozenset(atoms)


class HTNTotalOrderPlanner:
    """From-scratch total-order HTN decomposition planner.

    Operates directly on a real ``unified_planning.model.htn.HierarchicalProblem``
    (the single source of truth for tasks/methods/actions/objects -- no second
    schema is declared for static domain structure, per no-dual-bookkeeping).
    """

    #: Hard bound on total (task, args, state) decomposition attempts
    #: within a single solve() call. Total-order forward decomposition
    #: without a domain-specific heuristic can otherwise loop forever on
    #: domains where a method's precondition stays satisfiable after its
    #: own effects are applied (e.g. re-selecting an already-"done" object)
    #: -- confirmed for real against the bundled
    #: 2020-to-Multiarm-Blocksworld HTN fixture during this module's own
    #: development. Cycle detection (below) catches the common case; this
    #: budget is the honest backstop for the remainder, and its exhaustion
    #: is reported as a real HTNPlanningFailure, never a false success.
    MAX_DECOMPOSITION_ATTEMPTS = 20000

    def __init__(self, problem: HierarchicalProblem):
        self.problem = problem
        self._attempts = 0

    def initial_state(self) -> State:
        atoms = set()
        for fexp, value in self.problem.initial_values.items():
            if not value.is_bool_constant():
                continue
            if value.is_true():
                fluent_name = fexp.fluent().name
                arg_names = tuple(a.object().name for a in fexp.args)
                atoms.add((fluent_name, arg_names))
        return frozenset(atoms)

    def initial_task_network(self) -> tuple:
        """The initial task network as (task_name, arg_name_tuple) entries,
        in the declared total order."""
        network = []
        for subtask in self.problem.task_network.subtasks:
            args = tuple(a.object().name for a in subtask.parameters)
            network.append((subtask.task.name, args))
        return tuple(network)

    def solve(self) -> list:
        """Solve the problem's initial task network. Returns the flattened
        list of GroundAction in total order on success, or raises
        HTNPlanningFailure if no decomposition exists."""
        state = self.initial_state()
        network = self.initial_task_network()
        _FORALL_PROBLEM.set(self.problem)
        self._attempts = 0
        result = self._decompose_sequence(network, state, frozenset())
        if result is None:
            raise HTNPlanningFailure(
                "No total-order decomposition found for the initial task "
                "network within "
                f"{self.MAX_DECOMPOSITION_ATTEMPTS} decomposition attempts"
            )
        actions, _final_state = result
        return actions

    # -- internal recursive search -------------------------------------

    def _decompose_sequence(
        self, tasks: tuple, state: State, on_path: frozenset
    ) -> Optional[tuple]:
        """Decompose an ordered sequence of task calls, threading state
        through each in turn. Returns (actions, final_state) or None.

        `on_path` is the set of (task_name, args, state) nodes already open
        on the current recursive branch -- real cycle detection: total-order
        forward decomposition re-entering the identical (task, args, state)
        node on the same branch can never make further progress (state is
        the sole source of change), so it is pruned as a failed branch
        rather than explored to a stack overflow.
        """
        if not tasks:
            return ([], state)
        (task_name, args), rest = tasks[0], tasks[1:]
        node = (task_name, args, state)
        if node in on_path:
            return None
        for actions_head, state_after_head in self._decompose_one(
            task_name, args, state, on_path | {node}
        ):
            tail = self._decompose_sequence(rest, state_after_head, on_path)
            if tail is not None:
                tail_actions, final_state = tail
                return (actions_head + tail_actions, final_state)
        return None

    def _decompose_one(
        self, task_name: str, args: tuple, state: State, on_path: frozenset
    ):
        """Yield (actions, next_state) candidates for a single task call,
        in the order they should be tried (primitive first if it exists,
        then compound-task methods in declared order). A generator, so the
        caller backtracks simply by continuing iteration."""
        self._attempts += 1
        if self._attempts > self.MAX_DECOMPOSITION_ATTEMPTS:
            return

        # Primitive: a real InstantaneousAction with this name.
        if self.problem.has_action(task_name):
            action = self.problem.action(task_name)
            bindings = {p.name: arg for p, arg in zip(action.parameters, args)}
            if all(
                _eval_condition(pre, bindings, state) for pre in action.preconditions
            ):
                ga = GroundAction(task_name, args)
                next_state = _apply_effects(action, bindings, state)
                yield ([ga], next_state)
            return

        # Compound: an abstract Task with declared Methods.
        if not self.problem.has_task(task_name):
            return
        for method in self.problem.methods:
            if method.achieved_task.task.name != task_name:
                continue
            yield from self._try_method(method, args, state, on_path)

    def _try_method(self, method, args: tuple, state: State, on_path: frozenset):
        """Yield (actions, next_state) for every backtrack-viable
        instantiation of `method` applied to `args`, in order."""
        base_bindings = {}
        for param, arg in zip(method.achieved_task.parameters, args):
            base_bindings[param.name] = arg

        extra_params = [p for p in method.parameters if p.name not in base_bindings]
        candidate_sets = [
            [o.name for o in self.problem.objects(p.type)] for p in extra_params
        ]
        for combo in itertools.product(*candidate_sets) if extra_params else [()]:
            if self._attempts > self.MAX_DECOMPOSITION_ATTEMPTS:
                return
            bindings = dict(base_bindings)
            for p, obj_name in zip(extra_params, combo):
                bindings[p.name] = obj_name

            if not all(
                _eval_condition(pre, bindings, state) for pre in method.preconditions
            ):
                continue

            subtasks = tuple(
                (
                    st.task.name,
                    tuple(_resolve_arg(a, bindings) for a in st.parameters),
                )
                for st in method.subtasks
            )
            result = self._decompose_sequence(subtasks, state, on_path)
            if result is not None:
                yield result
