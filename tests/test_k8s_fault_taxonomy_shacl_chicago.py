# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: real `pyshacl.validate()` of
`ontology/k8s-fault-taxonomy.ttl` against
`packs/k8s-fault-taxonomy-pack/shapes/k8s-fault-taxonomy.shacl.ttl`.

Real collaborators: real `rdflib` graphs loaded from real files on disk,
real `pyshacl` validation. No `unittest.mock` / `Mock` / `MagicMock` /
`patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import pyshacl
except ModuleNotFoundError:
    pyshacl = None

REPO_ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = REPO_ROOT / "ontology" / "k8s-fault-taxonomy.ttl"
SHAPES = REPO_ROOT / "packs" / "k8s-fault-taxonomy-pack" / "shapes" / "k8s-fault-taxonomy.shacl.ttl"

requires_pyshacl = pytest.mark.skipif(
    pyshacl is None,
    reason="pyshacl is not installed in this environment -- UNSUPPORTED, not silently skipped.",
)


@requires_pyshacl
def test_k8s_fault_taxonomy_conforms_to_its_real_shacl_shape() -> None:
    conforms, results_graph, results_text = pyshacl.validate(
        data_graph=str(ONTOLOGY),
        shacl_graph=str(SHAPES),
        data_graph_format="turtle",
        shacl_graph_format="turtle",
    )

    assert conforms, f"real SHACL violations found:\n{results_text}"


@requires_pyshacl
def test_a_mutated_individual_missing_preflabel_is_caught_by_the_real_shape() -> None:
    """Falsifiability check: the shape must actually be capable of failing,
    not merely happen to pass -- construct a real, deliberately-broken
    graph (one Component individual with skos:inScheme but no
    skos:prefLabel) and assert pyshacl reports non-conformance."""
    broken_ontology = ONTOLOGY.read_text(encoding="utf-8").replace(
        'afl:Pod a afl:Component ; skos:inScheme afl:ComponentScheme ; skos:prefLabel "Pod" .',
        "afl:Pod a afl:Component ; skos:inScheme afl:ComponentScheme .",
    )
    assert "prefLabel" not in broken_ontology.split("afl:Pod a afl:Component")[1].split("\n")[0]

    conforms, _, _ = pyshacl.validate(
        data_graph=broken_ontology,
        shacl_graph=str(SHAPES),
        data_graph_format="turtle",
        shacl_graph_format="turtle",
    )

    assert conforms is False
