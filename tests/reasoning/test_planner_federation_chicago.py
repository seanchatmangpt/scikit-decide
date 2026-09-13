# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for ``autofde_lab.reasoning.planner_federation``.

Every test here constructs a real ``PDDLDomain``, runs a real registered
solver's real ``solve()``, and asserts on the real resulting
``PartialOrder``/``dict`` -- no mocking, no stubs, no interaction assertions.
``tests/reasoning/conftest.py`` explains why this worktree needs a
``__path__`` extension to make ``planner_federation.py`` importable at all
under the shared venv; that is a real-discovery fix, not a test double.
"""

from __future__ import annotations

import os

import pytest

from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.planner_federation import (
    SOLVER_NAMES,
    federate,
    solve_with_one_solver,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))

# The toy 2-action/1-object blocksworld fixture named in this task's context.
BLOCKS1_DOMAIN = os.path.join(
    _REPO_ROOT, "src", "autofde_lab", "planning", "tests", "fixtures", "blocks-domain.pddl"
)
BLOCKS1_PROBLEM = os.path.join(
    _REPO_ROOT, "src", "autofde_lab", "planning", "tests", "fixtures", "blocks-problem.pddl"
)

# The richer, real 3-block blocksworld fixture already used by
# tests/domains/python/test_pddl_domain.py::test_astar_solve_blocks -- a
# 4-step plan, enough to carry a real dependency-order assertion. Read-only:
# this test never modifies it.
BLOCKS3_DOMAIN = os.path.join(
    _REPO_ROOT, "tests", "domains", "python", "pddl_domains", "blocks", "domain.pddl"
)
BLOCKS3_PROBLEM = os.path.join(
    _REPO_ROOT,
    "tests",
    "domains",
    "python",
    "pddl_domains",
    "blocks",
    "probBLOCKS-3-0.pddl",
)

# A new fixture (this task's own, not an edit of an existing one): a 6-block
# reversed-tower blocksworld problem against the same real domain.pddl above,
# picked because a real, this-session probe measured its real Astar/FF solve
# times at ~0.57s / ~1.18s -- comfortably over any millisecond-scale timeout,
# for a real (not artificial/sleep-based) timeout test.
BLOCKS6_PROBLEM = os.path.join(_HERE, "fixtures", "blocks6-problem.pddl")


def test_solve_with_one_solver_astar_admits_ordered_partial_order():
    """Astar on the real 3-block domain: a validate_model-admitted plan
    whose atom label order respects the real plan's dependency order."""
    result = solve_with_one_solver(
        solver_name="Astar",
        domain_path=BLOCKS3_DOMAIN,
        problem_path=BLOCKS3_PROBLEM,
        timeout_s=30.0,
    )
    assert result is not None

    # Independently re-validated -- this test does not merely trust that
    # construction did not raise.
    validate_model(result)

    labels = [atom.label for atom in result.children]
    # Goal is (ON B C); real dependency order requires B to be picked up
    # only after it is unstacked/put down, and stacked only after that.
    def index_of(fragment: str) -> int:
        matches = [i for i, label in enumerate(labels) if fragment in label]
        assert matches, f"{fragment!r} not found in plan labels {labels!r}"
        return matches[0]

    unstack_a_idx = index_of("unstack a b")
    put_down_a_idx = index_of("put-down a")
    pick_up_b_idx = index_of("pick-up b")
    stack_b_c_idx = index_of("stack b c")

    # A must be unstacked off B, and put down, before B can be picked up;
    # B must be picked up before it can be stacked on C.
    assert unstack_a_idx < put_down_a_idx < pick_up_b_idx < stack_b_c_idx

    # The order edges encode exactly this total precedence chain.
    n = len(result.children)
    assert n == 4
    closure_pairs = {(e.src, e.dst) for e in result.closure}
    for i in range(n):
        for j in range(i + 1, n):
            assert (i, j) in closure_pairs


def test_solve_with_one_solver_astar_trivial_fixture_pads_to_valid_partial_order():
    """The 1-object/2-action fixture yields a 1-step plan; PartialOrder's
    real >=2-child arity law forces a Silent-padded, still-admitted shape."""
    result = solve_with_one_solver(
        solver_name="Astar",
        domain_path=BLOCKS1_DOMAIN,
        problem_path=BLOCKS1_PROBLEM,
        timeout_s=30.0,
    )
    assert result is not None
    validate_model(result)
    assert len(result.children) == 2
    assert "pick-up a" in result.children[0].label


def test_federate_returns_every_solver_name_astar_entry_admitted():
    results = federate(
        domain_path=BLOCKS3_DOMAIN,
        problem_path=BLOCKS3_PROBLEM,
        timeout_s=30.0,
    )
    assert set(results.keys()) == set(SOLVER_NAMES)
    assert "Astar" in results
    assert results["Astar"] is not None
    validate_model(results["Astar"])
    for name, candidate in results.items():
        if candidate is not None:
            validate_model(candidate)


def test_solve_with_one_solver_timeout_returns_none_not_hang_or_raise():
    """A real, unreachably-tiny timeout against a real ~0.5s+ solve: must
    return None promptly, never hang and never raise."""
    result = solve_with_one_solver(
        solver_name="Astar",
        domain_path=BLOCKS3_DOMAIN,
        problem_path=BLOCKS6_PROBLEM,
        timeout_s=0.001,
    )
    assert result is None


def test_solve_with_one_solver_unregistered_solver_returns_none():
    """A solver name that plainly isn't registered must refuse, not raise."""
    result = solve_with_one_solver(
        solver_name="DefinitelyNotARegisteredSolverName",
        domain_path=BLOCKS3_DOMAIN,
        problem_path=BLOCKS3_PROBLEM,
        timeout_s=5.0,
    )
    assert result is None
