from __future__ import annotations

import inspect

import pytest

from autofde_lab.reasoning import awesome_ai_gyms as subject

HEADER = "name\tcanonical_url\tcategory\tkind\tmodes\ttags\tprovenance\n"
CATALOG = HEADER + (
    "WebArena\thttps://github.com/web-arena-x/webarena\tweb\tenvironment\t"
    "eval\tweb-agent\taarle\n"
    "SWE-Gym\thttps://github.com/SWE-Gym/SWE-Gym\tcoding\tenvironment\t"
    "train,eval\tsoftware-engineering\taarle\n"
)


def test_registry_identity_is_preserved_as_public_uri() -> None:
    candidate = subject.parse_awesome_ai_gyms_tsv(CATALOG)[0]

    assert candidate.gym_ref == candidate.canonical_url
    assert candidate.source_authority == "NONE"
    assert candidate.standing == "UNKNOWN"


def test_dfcm_frontier_preserves_full_cross_product() -> None:
    candidates = subject.parse_awesome_ai_gyms_tsv(CATALOG)
    frontier = subject.build_planner_gym_frontier(candidates, ("p1", "p2", "p3"))

    assert len(frontier) == 6
    assert all(edge.compatibility == "UNKNOWN" for edge in frontier)
    assert all(edge.authority == "SELECT_ONLY" for edge in frontier)


def test_one_refused_edge_is_topology_not_graph_failure() -> None:
    candidates = subject.parse_awesome_ai_gyms_tsv(CATALOG)
    frontier = subject.build_planner_gym_frontier(candidates, ("p1", "p2", "p3"))
    classified = subject.classify_edge(
        frontier,
        planner_ref="p2",
        gym_ref="https://github.com/web-arena-x/webarena",
        compatibility="REFUSED",
        reason="planner action vocabulary is incompatible",
    )

    assert len(classified) == len(frontier)
    assert sum(edge.compatibility == "REFUSED" for edge in classified) == 1
    assert sum(edge.compatibility == "UNKNOWN" for edge in classified) == 5


def test_handoff_is_inert_and_requires_compatible_edge() -> None:
    candidate = subject.parse_awesome_ai_gyms_tsv(CATALOG)[0]
    edge = subject.build_planner_gym_frontier((candidate,), ("p1",))[0]

    with pytest.raises(ValueError, match="REQUIRES_COMPATIBLE_EDGE:UNKNOWN"):
        subject.manufacture_gymact_handoff(edge)

    compatible = subject.classify_edge(
        (edge,),
        planner_ref="p1",
        gym_ref=candidate.gym_ref,
        compatibility="COMPATIBLE",
        reason="declared planner contract matches candidate interface",
    )[0]
    handoff = subject.manufacture_gymact_handoff(compatible)

    assert handoff.gym_ref == candidate.canonical_url
    assert handoff.authority == "NONE"
    assert handoff.requested_stage == "CANDIDATE_ADMISSION"


def test_selection_module_has_no_gym_execution_path() -> None:
    source = inspect.getsource(subject)

    assert "import gymact" not in source
    assert "subprocess" not in source
    assert "EnvironmentProvider" not in source
    assert ".act(" not in source


def test_repo_planner_frontier_reads_entry_points_without_importing_solvers() -> None:
    candidates = subject.parse_awesome_ai_gyms_tsv(CATALOG)
    pyproject = """
[project.entry-points."autofde_lab.solvers"]
AOstar = "autofde_lab.hub.solver.aostar:AOstar [solvers]"
MCTS = "autofde_lab.hub.solver.mcts:MCTS [solvers]"
DSPyPolicy = "autofde_lab.hub.solver.dspy_policy:DSPyPolicy [dspy]"
"""

    refs = subject.planner_refs_from_pyproject(pyproject)
    frontier = subject.build_repo_planner_gym_frontier(candidates, pyproject)

    assert refs == ("AOstar", "DSPyPolicy", "MCTS")
    assert len(frontier) == 6
    assert {edge.planner_ref for edge in frontier} == set(refs)


def test_missing_planner_entry_points_are_refused() -> None:
    with pytest.raises(ValueError, match="AUTOFDE_PLANNER_ENTRY_POINTS_MISSING"):
        subject.planner_refs_from_pyproject("[project]\nname='autofde-lab'\n")
