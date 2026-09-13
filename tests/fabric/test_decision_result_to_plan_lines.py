# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for ``fabric.powl.decision_result_to_plan_lines``.

Real ``DecisionFabric``, real PDDL domain (``blocks``), real ``solve()`` --
no mocked backend, no fabricated ``DecisionResult``. Confirms the
plan_lines produced from a real classical-PDDL ``DecisionResult`` feed
``project_plan_to_powl`` into Turtle that ``parse_powl_turtle`` accepts, and
that a real non-PDDL result (Maze + Astar) is refused by name rather than
silently mishandled.
"""

from __future__ import annotations

import os

import pytest

from autofde_lab.fabric.models import DecisionRequest, DecisionStanding
from autofde_lab.fabric.powl import (
    PowlProjectionUnsupported,
    decision_result_to_plan_lines,
    parse_powl_turtle,
    project_plan_to_powl,
)
from autofde_lab.fabric.service import DecisionFabric

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_BLOCKS_DOMAIN = os.path.join(
    _REPO_ROOT, "tests/domains/python/pddl_domains/blocks/domain.pddl"
)
_BLOCKS_PROBLEM = os.path.join(
    _REPO_ROOT, "tests/domains/python/pddl_domains/blocks/probBLOCKS-3-0.pddl"
)


def test_pddl_decision_result_converts_and_projects_to_valid_turtle() -> None:
    fabric = DecisionFabric()
    request = DecisionRequest(
        domain="PDDLDomain",
        solver="Astar",
        domain_arguments={
            "domain_path": _BLOCKS_DOMAIN,
            "problem_path": _BLOCKS_PROBLEM,
        },
        max_steps=100,
        use_cache=False,
    )

    result = fabric.solve(request)

    assert result.standing == DecisionStanding.SOLVED
    assert len(result.steps) > 0
    # Ground truth for the shape this converter depends on: verified this
    # session that DecisionStep.action is NOT VAL-format text by the time it
    # reaches a DecisionResult -- fabric/service.py serializes it through
    # canonical.to_jsonable, which for a PDDLAction takes the generic
    # __dict__-publicization branch, losing the human-readable repr.
    for step in result.steps:
        assert set(step.action) == {"action_id", "arguments"}
        assert isinstance(step.action["action_id"], int)
        assert isinstance(step.action["arguments"], list)

    plan_lines = decision_result_to_plan_lines(result)

    assert len(plan_lines) == len(result.steps)
    for line in plan_lines:
        assert line.startswith("(")
        assert line.endswith(")")
    # Real, name-resolved actions -- not a placeholder/echo of the ids.
    assert any("unstack" in line or "pick-up" in line for line in plan_lines)

    turtle = project_plan_to_powl(
        plan_lines,
        base_iri="urn:test:decision-result-to-plan-lines",
        domain_path=None,
        problem_path=None,
    )

    model = parse_powl_turtle(turtle)

    assert model.activity_count == len(plan_lines)
    ordered = model.ordered_children()
    assert len(ordered) == len(plan_lines)
    for index, (child, line) in enumerate(zip(ordered, plan_lines)):
        leaf = model.leaves[child.child_model]
        expected_name = line.strip("()").split()[0]
        assert leaf.activity_label == expected_name
        assert leaf.plan_ordinal == index


def test_non_pddl_decision_result_raises_named_exception() -> None:
    fabric = DecisionFabric()
    request = DecisionRequest(
        domain="Maze",
        solver="Astar",
        max_steps=200,
        use_cache=False,
    )

    result = fabric.solve(request)

    assert result.standing == DecisionStanding.SOLVED
    assert result.request.domain == "Maze"
    assert len(result.steps) > 0

    with pytest.raises(PowlProjectionUnsupported, match="UNSUPPORTED_DOMAIN_FAMILY"):
        decision_result_to_plan_lines(result)


def test_pddl_domain_missing_path_arguments_raises_named_exception() -> None:
    fabric = DecisionFabric()
    request = DecisionRequest(
        domain="PDDLDomain",
        solver="Astar",
        domain_arguments={
            "domain_path": _BLOCKS_DOMAIN,
            "problem_path": _BLOCKS_PROBLEM,
        },
        max_steps=100,
        use_cache=False,
    )
    result = fabric.solve(request)

    # Simulate a PDDL-family result whose request lost its path arguments
    # (e.g. rehydrated from a stripped-down cache payload) -- must be
    # refused, not guessed at.
    from dataclasses import replace

    stripped_request = replace(result.request, domain_arguments={})
    stripped_result = replace(result, request=stripped_request)

    with pytest.raises(PowlProjectionUnsupported, match="UNSUPPORTED_DOMAIN_FAMILY"):
        decision_result_to_plan_lines(stripped_result)
