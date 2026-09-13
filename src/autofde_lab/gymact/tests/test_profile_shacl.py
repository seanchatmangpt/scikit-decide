"""Chicago-style TDD prep: real rdflib graphs + real pyshacl validation.

No mocking of the RDF/SHACL engine -- both `rdflib` and `pyshacl` are real,
already-declared dependencies (the `ofmf` extra in pyproject.toml). This file
is expected to pass as-is (it exercises rdflib/pyshacl directly against real
fixture files, not any not-yet-written GymAct module) and therefore anchors
the rest of the TDD-prep suite: if this file is red, the environment itself
(not GymAct code) is the problem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

rdflib = pytest.importorskip("rdflib")
pyshacl = pytest.importorskip("pyshacl")

FIXTURES = Path(__file__).parent / "fixtures"


def _load(path: Path) -> Any:
    graph = rdflib.Graph()
    graph.parse(path, format="turtle")
    return graph


def test_profile_fixture_contains_real_prov_activity_triple() -> None:
    graph = _load(FIXTURES / "profile.ttl")

    rows = list(
        graph.query(
            """
            PREFIX prov: <http://www.w3.org/ns/prov#>
            PREFIX dct:  <http://purl.org/dc/terms/>
            SELECT ?identifier WHERE {
                ?episode a prov:Activity ;
                         dct:identifier ?identifier .
            }
            """
        )
    )
    assert [str(row.identifier) for row in rows] == ["episode-fixture-1"]


def test_conforming_instance_satisfies_episode_shape() -> None:
    data_graph = _load(FIXTURES / "instance_conforming.ttl")
    shapes_graph = _load(FIXTURES / "shapes.ttl")

    conforms, _report_graph, report_text = pyshacl.validate(
        data_graph, shacl_graph=shapes_graph
    )

    assert conforms is True, report_text


def test_violating_instance_fails_episode_shape_with_named_violation() -> None:
    data_graph = _load(FIXTURES / "instance_violating.ttl")
    shapes_graph = _load(FIXTURES / "shapes.ttl")

    conforms, _report_graph, report_text = pyshacl.validate(
        data_graph, shacl_graph=shapes_graph
    )

    assert conforms is False
    assert "dct:identifier" in report_text or "identifier" in report_text
