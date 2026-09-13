# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real-component checkpoint for the vendored :mod:`autofde_lab.ofmf` module.

Exercises the real, non-actuating ``RDFDelta``/``DialectSuite.sparql_ask``/
``DialectSuite.sparql_construct_to_delta`` against a real in-memory
``ConjunctiveGraph`` -- no mocks. Per ``tests/CLAUDE.md`` invariant 1, this is
a unit/integration checkpoint, not a Chicago-domain/solver claim, so it does
not carry "chicago" in its name.
"""

from rdflib import ConjunctiveGraph, Literal, Namespace, URIRef

from autofde_lab.ofmf import DialectSuite, RDFDelta
from autofde_lab.ofmf.kgc_ofmf_utils import KH

EX = Namespace("urn:example:")


def _dataset_with_query(query_text: str) -> tuple[ConjunctiveGraph, URIRef]:
    ds = ConjunctiveGraph()
    query_node = EX.myQuery
    ds.add((query_node, KH.text, Literal(query_text)))
    ds.add((EX.alice, EX.knows, EX.bob))
    ds.add((EX.bob, EX.knows, EX.carol))
    return ds, query_node


def test_sparql_ask_true_on_real_matching_triple():
    ds, query_node = _dataset_with_query(
        "PREFIX ex: <urn:example:> ASK { ex:alice ex:knows ex:bob }"
    )
    suite = DialectSuite(repo_dataset=ds)
    assert suite.sparql_ask(ds, query_node) is True


def test_sparql_ask_false_on_real_nonmatching_triple():
    ds, query_node = _dataset_with_query(
        "PREFIX ex: <urn:example:> ASK { ex:alice ex:knows ex:carol }"
    )
    suite = DialectSuite(repo_dataset=ds)
    assert suite.sparql_ask(ds, query_node) is False


def test_sparql_construct_to_delta_real_triples():
    ds, query_node = _dataset_with_query(
        "PREFIX ex: <urn:example:> "
        "CONSTRUCT { ?a ex:friendOf ?c } "
        "WHERE { ?a ex:knows ?b . ?b ex:knows ?c }"
    )
    suite = DialectSuite(repo_dataset=ds)
    delta = suite.sparql_construct_to_delta(ds, query_node)

    assert isinstance(delta, RDFDelta)
    assert delta.deletes == set()
    assert (EX.alice, EX.friendOf, EX.carol, None) in delta.adds
    assert len(delta.adds) == 1


def test_rdf_delta_turtle_round_trip():
    delta = RDFDelta(
        adds={(EX.alice, EX.friendOf, EX.carol, None)},
        deletes=set(),
    )
    turtle = delta.to_turtle()
    reconstructed = RDFDelta.from_turtle(turtle)

    assert reconstructed.adds == delta.adds
    assert reconstructed.deletes == delta.deletes
