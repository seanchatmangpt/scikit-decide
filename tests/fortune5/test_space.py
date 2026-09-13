from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from math import prod

import pytest

import autofde_lab.fortune5.space as fortune5_space_module
from autofde_lab.fortune5 import (
    FORTUNE5_SPACE,
    Axis,
    CompatibilityLaw,
    Option,
    StateSpace,
    pairwise_token_count,
)


def test_fortune5_upper_bound_and_axis_contract() -> None:
    assert len(FORTUNE5_SPACE.axes) == 14
    assert [axis.name for axis in FORTUNE5_SPACE.axes] == [
        "enterprise",
        "cloud",
        "geography",
        "environment",
        "cluster_profile",
        "workload",
        "traffic",
        "data_class",
        "availability",
        "release",
        "identity",
        "policy",
        "runtime_ai",
        "fault",
    ]
    assert FORTUNE5_SPACE.raw_upper_bound == prod(
        len(axis.options) for axis in FORTUNE5_SPACE.axes
    )
    assert FORTUNE5_SPACE.raw_upper_bound == 1_327_104_000
    assert len(FORTUNE5_SPACE.digest) == 64


def test_mixed_radix_coordinate_access_round_trips_without_materialization() -> None:
    indexes = (0, 1, 73, 74_001, FORTUNE5_SPACE.raw_upper_bound - 1)
    for index in indexes:
        scenario = FORTUNE5_SPACE.raw_coordinate_at(index)
        assert FORTUNE5_SPACE.raw_index_of(scenario) == index
        assert scenario.digest == FORTUNE5_SPACE.raw_coordinate_at(index).digest

    first = FORTUNE5_SPACE.raw_coordinate_at(0)
    last = FORTUNE5_SPACE.raw_coordinate_at(FORTUNE5_SPACE.raw_upper_bound - 1)
    assert first.names()["enterprise"] == "enterprise-01"
    assert first.names()["fault"] == "healthy"
    assert last.names()["enterprise"] == "enterprise-05"
    assert last.names()["fault"] == "zone-loss"
    with pytest.raises(IndexError, match="REFUSED:COORDINATE_OUT_OF_RANGE"):
        FORTUNE5_SPACE.raw_coordinate_at(-1)
    with pytest.raises(IndexError, match="REFUSED:COORDINATE_OUT_OF_RANGE"):
        FORTUNE5_SPACE.raw_coordinate_at(FORTUNE5_SPACE.raw_upper_bound)


def test_scenario_identity_binds_the_exact_state_space_constitution() -> None:
    base = StateSpace((Axis("cloud", (Option("aws"), Option("azure"))),))
    changed = StateSpace(
        (Axis("cloud", (Option("aws"), Option("azure"))),),
        (CompatibilityLaw.from_mappings(forbid={"cloud": "azure"}),),
    )
    base_scenario = base.scenario({"cloud": "aws"})
    changed_scenario = changed.scenario({"cloud": "aws"})

    assert base.digest != changed.digest
    assert base_scenario.digest != changed_scenario.digest
    assert base_scenario.scenario_id != changed_scenario.scenario_id
    assert base.is_lawful(base_scenario)
    assert not changed.is_lawful(base_scenario)
    with pytest.raises(ValueError, match="REFUSED:SCENARIO_STATE_SPACE_MISMATCH"):
        changed.raw_index_of(base_scenario)


def test_pairwise_basis_covers_every_pair_without_cartesian_materialization() -> None:
    candidates = FORTUNE5_SPACE.pairwise_candidates(candidate_limit=5_000)
    assert len(candidates) == 1_605
    expected_tokens = sum(
        len(left.options) * len(right.options)
        for index, left in enumerate(FORTUNE5_SPACE.axes)
        for right in FORTUNE5_SPACE.axes[index + 1 :]
    )
    assert expected_tokens == 2_415
    assert pairwise_token_count(candidates) == expected_tokens
    assert FORTUNE5_SPACE.raw_upper_bound / len(candidates) > 800_000
    assert all(
        candidate.space_digest == FORTUNE5_SPACE.digest for candidate in candidates
    )


def test_pairwise_cover_is_deterministic_and_refuses_false_coverage() -> None:
    first = FORTUNE5_SPACE.pairwise_covering(candidate_limit=5_000)
    second = FORTUNE5_SPACE.pairwise_covering(candidate_limit=5_000)
    assert [scenario.digest for scenario in first] == [
        scenario.digest for scenario in second
    ]
    candidates = FORTUNE5_SPACE.pairwise_candidates(candidate_limit=5_000)
    assert pairwise_token_count(first) == pairwise_token_count(candidates)
    with pytest.raises(ValueError, match="REFUSED:PAIRWISE_COVERAGE_INCOMPLETE"):
        FORTUNE5_SPACE.pairwise_covering(candidate_limit=5_000, max_scenarios=2)
    with pytest.raises(ValueError, match="REFUSED:PAIRWISE_DESIGN_TOO_LARGE"):
        FORTUNE5_SPACE.pairwise_candidates(candidate_limit=100)


def test_same_name_parameter_smuggling_is_not_admitted() -> None:
    axis = Axis("cloud", (Option("aws"), Option("azure")))
    space = StateSpace((axis,))
    admitted = space.scenario({"cloud": "aws"})
    smuggled = replace(
        admitted,
        choices=(("cloud", Option.from_mapping("aws", {"region": "hidden"})),),
    )
    assert space.is_lawful(admitted)
    assert not space.is_lawful(smuggled)
    with pytest.raises(ValueError, match="REFUSED:OPTION_IDENTITY_NOT_ADMITTED"):
        space.scenario({"cloud": Option.from_mapping("aws", {"region": "hidden"})})
    with pytest.raises(ValueError, match="REFUSED:OPTION_ATTRS_NOT_CANONICAL"):
        Option("aws", (("z", "1"), ("a", "2")))


def test_compatibility_laws_fail_closed_at_admission() -> None:
    axes = (
        Axis("data", (Option("public"), Option("restricted"))),
        Axis("policy", (Option("baseline"), Option("zero-trust"))),
    )
    law = CompatibilityLaw.from_mappings(
        when={"data": "restricted"},
        require={"policy": "zero-trust"},
        reason="restricted data requires zero-trust in this bounded fixture",
    )
    space = StateSpace(axes, (law,))
    assert space.is_lawful(
        space.scenario({"data": "restricted", "policy": "zero-trust"})
    )
    assert not space.is_lawful(
        space.scenario({"data": "restricted", "policy": "baseline"})
    )

    unknown_axis = CompatibilityLaw.from_mappings(when={"ambient_authority": "yes"})
    with pytest.raises(ValueError, match="REFUSED:UNKNOWN_COMPATIBILITY_AXIS"):
        StateSpace(axes, (unknown_axis,))

    unknown_option = CompatibilityLaw.from_mappings(when={"policy": "root"})
    with pytest.raises(ValueError, match="REFUSED:UNKNOWN_COMPATIBILITY_OPTION"):
        StateSpace(axes, (unknown_option,))

    contradictory = CompatibilityLaw.from_mappings(
        require={"policy": "zero-trust"}, forbid={"policy": "zero-trust"}
    )
    with pytest.raises(ValueError, match="REFUSED:CONTRADICTORY_COMPATIBILITY_LAW"):
        StateSpace(axes, (contradictory,))


def test_runtime_surface_has_no_ambient_actuation_authority() -> None:
    scenario = FORTUNE5_SPACE.raw_coordinate_at(7)
    assert scenario.authority == "NONE"
    assert scenario.standing == "CANDIDATE"
    assert not hasattr(scenario, "execute")
    assert not hasattr(scenario, "actuate")
    assert not hasattr(FORTUNE5_SPACE, "execute")
    assert not hasattr(FORTUNE5_SPACE, "actuate")

    tree = ast.parse(inspect.getsource(fortune5_space_module))
    banned_import_roots = {
        "boto3",
        "google.cloud",
        "httpx",
        "kubernetes",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    imported_roots: set[str] = set()
    declared_callables: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            declared_callables.add(node.name)
    assert not any(
        imported == banned or imported.startswith(f"{banned}.")
        for imported in imported_roots
        for banned in banned_import_roots
    )
    assert not ({"actuate", "execute", "deploy", "mutate"} & declared_callables)
