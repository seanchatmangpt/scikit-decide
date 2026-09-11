# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import importlib.util

import pytest

pytest.importorskip("unified_planning")
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("up_aries") is None,
    reason="up-aries is an optional HDDL execution dependency",
)

from unified_planning.model.htn import HierarchicalProblem

from autofde_lab.hub.domain.hddl import HDDLDomain
from autofde_lab.hub.solver.hddl import HDDLSolver
from autofde_lab.utils import (
    get_registered_domains,
    get_registered_solvers,
    load_registered_domain,
    load_registered_solver,
)

HDDL_DOMAIN = """
(define (domain delivery-htn)
  (:requirements :typing :hierarchy :negative-preconditions)
  (:types location)
  (:predicates (at ?l - location))

  (:task relocate
    :parameters (?from - location ?to - location))

  (:method relocate-direct
    :parameters (?from - location ?to - location)
    :task (relocate ?from ?to)
    :ordered-subtasks
      (and
        (move ?from ?to)))

  (:action move
    :parameters (?from - location ?to - location)
    :precondition (at ?from)
    :effect
      (and
        (not (at ?from))
        (at ?to)))
)
"""

HDDL_PROBLEM = """
(define (problem delivery-htn-p01)
  (:domain delivery-htn)
  (:objects depot destination - location)
  (:htn
    :ordered-subtasks
      (and
        (relocate depot destination)))
  (:init
    (at depot))
  (:goal
    (at destination))
)
"""


def test_hddl_plugins_are_discoverable_through_runtime_entry_points():
    assert "HDDLDomain" in get_registered_domains()
    assert "HDDLSolver" in get_registered_solvers()
    assert load_registered_domain("HDDLDomain") is HDDLDomain
    assert load_registered_solver("HDDLSolver") is HDDLSolver


def test_hddl_parse_solve_decompose_and_execute_real_plan(tmp_path):
    domain_file = tmp_path / "domain.hddl"
    problem_file = tmp_path / "problem.hddl"
    domain_file.write_text(HDDL_DOMAIN, encoding="utf-8")
    problem_file.write_text(HDDL_PROBLEM, encoding="utf-8")

    domain_factory = lambda: HDDLDomain.from_files(domain_file, problem_file)
    parsed = domain_factory()

    assert isinstance(parsed.hierarchical_problem, HierarchicalProblem)
    assert [task.name for task in parsed.hierarchical_problem.tasks] == ["relocate"]
    assert [method.name for method in parsed.hierarchical_problem.methods] == [
        "relocate-direct"
    ]

    with HDDLSolver(domain_factory=domain_factory) as solver:
        assert HDDLSolver.check_domain(parsed)
        solver.solve()

        hierarchical = solver.get_hierarchical_plan()
        primitive = solver.get_plan()

        assert len(hierarchical.methods()) == 1
        assert len(hierarchical.actions()) == 1
        assert [action.up_action.name for action in primitive] == ["move"]

        execution = domain_factory()
        state = execution.get_initial_state()
        for action in primitive:
            state = execution.get_next_state(state, action)

        assert execution.is_goal(state)


def test_hddl_domain_refuses_flat_problem():
    from unified_planning.shortcuts import Problem

    with pytest.raises(TypeError, match="HierarchicalProblem"):
        HDDLDomain(Problem("flat"))
