# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real planner federation over PDDL domains.

Runs several *actually registered* scikit-decide solvers against the same
real :class:`~autofde_lab.hub.domain.pddl.PDDLDomain`, each under a real
wall-clock timeout, and converts each surviving plan into a real POWL 2.0
:class:`~autofde_lab.powl.algebra.PartialOrder` -- admitted only if
:func:`autofde_lab.powl.validate.validate_model` accepts it.

This module computes candidate plans. It does not actuate, admit, or issue
receipts -- see ``src/autofde_lab/CLAUDE.md``.

``SOLVER_NAMES`` selection, empirically justified this session against
``tests/domains/python/pddl_domains/blocks/{domain.pddl,probBLOCKS-3-0.pddl}``
and ``tests/reasoning/fixtures/blocks6-problem.pddl`` (both real PDDL STRIPS
blocksworld instances, solved with the real, registered ``Astar``/``FF``/etc.
solvers via ``autofde_lab.utils.load_registered_solver``, plain
``domain_factory=lambda: domain`` construction, no special config):

* ``Astar`` -- solved both fixtures with defaults (4-step and 20-step plans,
  goal reached both times).
* ``FF`` -- also solved both fixtures with defaults, plans identical in
  length to Astar's.
* ``BFWS``, ``IW`` -- rejected: both raise
  ``TypeError: __init__() missing 1 required positional argument:
  'state_features'`` when constructed the same way Astar/FF are (no defaults
  exist for this parameter), so they are not runnable without solver-specific
  configuration this federation does not have a principled way to supply.
* ``LazyAstar`` -- rejected: not registered in the ``autofde_lab.solvers``
  entry-point group at all (``load_registered_solver`` logs
  ``"/!\\ LazyAstar could not be loaded because it is not registered"`` and
  returns ``None``).
* ``AOstar`` -- rejected: solved the 1-step and 4-step fixtures instantly,
  but on ``probBLOCKS-3-0`` widened to a 6-block, 20-step reversed-tower goal
  (``tests/reasoning/fixtures/blocks6-problem.pddl``) it never returned from
  ``solve()`` within 60 real wall-clock seconds (confirmed by a real,
  separately-timed probe run this session) -- exactly the failure mode this
  module's per-solver timeout exists to catch, so it is excluded from the
  federation's defaults rather than trusted to always finish in time.
"""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Optional

from autofde_lab import utils
from autofde_lab.hub.domain.pddl.domain import PDDLDomain
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder, PowlNode, Silent
from autofde_lab.powl.refusals import PowlError
from autofde_lab.powl.validate import validate_model

_LOGGER = logging.getLogger(__name__)

#: Wall-clock bound applied to every rollout, mirroring
#: ``fabric/coverage.py``'s ``MAX_ROLLOUT_STEPS`` guard against a solver
#: whose policy never reaches the goal (or oscillates) from cycling forever.
MAX_ROLLOUT_STEPS = 200

#: Solvers kept in the default federation -- see the module docstring for the
#: real, this-session run output that justifies each inclusion/exclusion.
SOLVER_NAMES: tuple[str, ...] = ("Astar", "FF")


def _rollout_plan(domain: PDDLDomain, solver) -> tuple[list, object]:
    """Roll out ``solver``'s policy on ``domain`` from a fresh reset.

    Real ``reset()``/``sample_action()``/``step()`` loop, the same shape as
    ``tests/domains/python/test_pddl_domain.py::test_astar_solve_blocks``.
    Returns ``(plan_actions, final_observation)``.
    """
    obs = domain.reset()
    plan: list = []
    for _ in range(MAX_ROLLOUT_STEPS):
        if domain._is_terminal(obs):
            break
        action = solver.sample_action(obs)
        plan.append(action)
        outcome = domain.step(action)
        obs = outcome.observation
    return plan, obs


def _plan_to_partial_order(plan_actions: list) -> Optional[PartialOrder]:
    """Convert a real, ordered action sequence into a real POWL PartialOrder.

    Each plan step becomes an :class:`~autofde_lab.powl.algebra.Atom` whose
    ``label`` is ``str(action)`` (the PDDL action's own ``repr``, e.g.
    ``"(unstack a b)"``) and whose ``consequence`` is the literal string
    ``"DO"`` -- this federation only ever proposes *doing* the ground action
    a solver selected; it never proposes an ``UNDO`` or other consequence
    kind, so ``"DO"`` is the sole value this module emits.

    A total precedence chain ``atoms[i] -> atoms[i+1]`` is added for every
    consecutive pair, i.e. the *observed rollout order* is preserved exactly
    as a real partial order (deterministic-domain rollouts are already
    totally ordered; nothing here reorders or parallelizes the plan).

    ``PartialOrder`` requires at least 2 children
    (``PowlRefusal.INVALID_PARTIAL_ORDER_ARITY``), so a single-action plan is
    padded with one trailing :class:`~autofde_lab.powl.algebra.Silent` (tau)
    node and a single precedence edge into it -- this keeps the shape legal
    without inventing a second real action that was never actually taken.
    An empty plan (goal already true at reset -- never observed for any
    fixture used by this session's tests, but not excluded by the domain)
    cannot be represented as a >=2-child PartialOrder at all and returns
    ``None``.
    """
    if not plan_actions:
        return None
    atoms: list[PowlNode] = [
        Atom(label=str(action), action=None, bindings={}, consequence="DO")
        for action in plan_actions
    ]
    if len(atoms) == 1:
        children: tuple[PowlNode, ...] = (atoms[0], Silent())
    else:
        children = tuple(atoms)
    n = len(children)
    order = frozenset(OrderEdge(i, i + 1) for i in range(n - 1))
    return PartialOrder(children=children, order=order)


def solve_with_one_solver(
    *,
    solver_name: str,
    domain_path: str,
    problem_path: str,
    timeout_s: float = 30.0,
) -> Optional[PartialOrder]:
    """Solve one real PDDL domain with one real, named registered solver.

    Never raises. Returns ``None`` on: the solver not being registered/
    loadable, domain construction failure, a `solve()` that exceeds
    ``timeout_s`` real wall-clock seconds, a rollout/solve runtime error, or
    a rollout that finishes without reaching the domain's real goal. A
    ``None`` here is a refusal to claim success, never a silently-swallowed
    wrong answer.
    """
    try:
        solver_cls = utils.load_registered_solver(solver_name)
    except Exception:
        _LOGGER.warning("solver %r failed to load", solver_name, exc_info=True)
        return None
    if solver_cls is None:
        return None

    try:
        domain = PDDLDomain(domain_path, problem_path)
    except Exception:
        _LOGGER.warning(
            "domain construction failed for %r/%r", domain_path, problem_path,
            exc_info=True,
        )
        return None

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        with solver_cls(domain_factory=lambda: domain) as solver:
            future = executor.submit(solver.solve)
            try:
                future.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError:
                _LOGGER.warning(
                    "solver %r exceeded timeout_s=%s on %r",
                    solver_name, timeout_s, problem_path,
                )
                return None
            except Exception:
                _LOGGER.warning(
                    "solver %r raised during solve()", solver_name, exc_info=True
                )
                return None

            try:
                plan_actions, final_obs = _rollout_plan(domain, solver)
            except Exception:
                _LOGGER.warning(
                    "rollout failed for solver %r", solver_name, exc_info=True
                )
                return None

            if not domain._goal_checker.is_goal(final_obs.to_cpp()):
                _LOGGER.warning(
                    "solver %r did not reach the goal within %d rollout steps",
                    solver_name, MAX_ROLLOUT_STEPS,
                )
                return None
    except Exception:
        _LOGGER.warning(
            "solver %r construction/context failed", solver_name, exc_info=True
        )
        return None
    finally:
        # Non-blocking: a timed-out solve()'s worker thread may still be
        # running inside the C++ engine; we do not wait on it, since this
        # federation already decided (via the timeout above) not to trust
        # its result.
        executor.shutdown(wait=False)

    return _plan_to_partial_order(plan_actions)


def federate(
    *,
    domain_path: str,
    problem_path: str,
    solver_names: tuple[str, ...] = SOLVER_NAMES,
    timeout_s: float = 30.0,
) -> dict[str, Optional[PartialOrder]]:
    """Run every named solver sequentially against the same real domain.

    Every non-``None`` :func:`solve_with_one_solver` result is re-validated
    for real via :func:`autofde_lab.powl.validate.validate_model` before
    being included -- a result that fails validation is replaced with
    ``None`` rather than admitted, since an unvalidated ``PartialOrder``
    carries no standing (``.claude/rules/no-dual-bookkeeping.md``: a claim of
    validity may not live only in the fact that construction did not raise).
    In practice every ``PartialOrder`` this module builds already satisfies
    ``validate_model`` by construction (a linear precedence chain over >=2
    children is always transitively reduced, acyclic, and within
    ``MAX_POWL_DEPTH``); this second, independent check exists so a future
    change to ``_plan_to_partial_order`` cannot silently start emitting an
    invalid shape that gets admitted anyway.
    """
    results: dict[str, Optional[PartialOrder]] = {}
    for name in solver_names:
        candidate = solve_with_one_solver(
            solver_name=name,
            domain_path=domain_path,
            problem_path=problem_path,
            timeout_s=timeout_s,
        )
        if candidate is not None:
            try:
                validate_model(candidate)
            except PowlError:
                _LOGGER.warning(
                    "solver %r produced a PartialOrder that failed "
                    "validate_model; excluding it rather than admitting it",
                    name, exc_info=True,
                )
                candidate = None
        results[name] = candidate
    return results
