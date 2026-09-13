# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style round trip: real RDF Turtle -> compiled PDDL -> real
scikit-decide Astar solve -> real POWL2 Turtle projection.

No mock/patch/monkeypatch anywhere. Every collaborator is real: rdflib
parses a real Turtle file on disk, ``pddl_engine.solve_to_plan_file`` runs
the real registered Astar solver against the real compiled PDDL text, and
``powl.py`` computes real blake3 digests (via the real ``b3sum``/``blake3``
path) over the real compiled PDDL files. Assertions are state-based: the
real plan file contents and the real POWL Turtle graph, not "was X called".
"""

from __future__ import annotations

import os

import pytest
import rdflib

from autofde_lab.fabric import pddl_engine
from autofde_lab.fabric.rdf_domain import (
    PD,
    RdfDomainError,
    compile_rdf_to_pddl,
    compile_rdf_to_pddl_files,
)

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "blocks_rdf_domain.ttl"
)


def test_fixture_is_valid_turtle_conforming_to_the_ontology():
    graph = rdflib.Graph()
    graph.parse(FIXTURE, format="turtle")
    domains = list(graph.subjects(rdflib.RDF.type, PD.Domain))
    problems = list(graph.subjects(rdflib.RDF.type, PD.Problem))
    assert len(domains) == 1
    assert len(problems) == 1


def test_compile_rdf_to_pddl_produces_the_real_blocks_domain_text():
    domain_text, problem_text = compile_rdf_to_pddl(FIXTURE)

    assert domain_text == (
        "(define (domain blocks)\n"
        "  (:requirements :strips)\n"
        "  (:predicates (on ?x ?y) (ontable ?x) (clear ?x) (handempty) (holding ?x))\n"
        "  (:action pick-up\n"
        "    :parameters (?x)\n"
        "    :precondition (and (clear ?x) (ontable ?x) (handempty))\n"
        "    :effect (and (not (ontable ?x)) (not (clear ?x)) (not (handempty)) (holding ?x)))\n"
        "  (:action put-down\n"
        "    :parameters (?x)\n"
        "    :precondition (holding ?x)\n"
        "    :effect (and (not (holding ?x)) (clear ?x) (handempty) (ontable ?x))))\n"
    )
    assert problem_text == (
        "(define (problem blocks-1)\n"
        "  (:domain blocks)\n"
        "  (:objects a)\n"
        "  (:init (ontable a) (clear a) (handempty))\n"
        "  (:goal (holding a)))\n"
    )


def test_compiled_pddl_is_accepted_unmodified_by_the_real_pddl_engine(tmp_path):
    domain_p = str(tmp_path / "domain.pddl")
    problem_p = str(tmp_path / "problem.pddl")
    plan_p = str(tmp_path / "plan.txt")

    compile_rdf_to_pddl_files(FIXTURE, domain_p, problem_p)

    # Real scikit-decide PDDL parser must accept the compiled text with no
    # unimplemented requirements -- this is the untyped :strips subset.
    assert pddl_engine.unsupported_requirements(domain_p, problem_p) == []

    rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)

    assert rc == pddl_engine.EXIT_PLAN_FOUND
    plan_text = open(plan_p, encoding="utf-8").read()
    assert plan_text.splitlines()[0] == "(pick-up a)"


def test_full_round_trip_rdf_to_pddl_to_plan_to_powl_turtle(tmp_path):
    domain_p = str(tmp_path / "domain.pddl")
    problem_p = str(tmp_path / "problem.pddl")
    plan_p = str(tmp_path / "plan.txt")
    powl_p = str(tmp_path / "plan.powl.ttl")

    compile_rdf_to_pddl_files(FIXTURE, domain_p, problem_p)

    rc = pddl_engine.solve_to_plan_file(
        domain_p,
        problem_p,
        plan_p,
        powl_path=powl_p,
        powl_base_iri="urn:autofde-lab:rdf-roundtrip:blocks",
    )
    assert rc == pddl_engine.EXIT_PLAN_FOUND

    turtle_text = open(powl_p, encoding="utf-8").read()
    powl_graph = rdflib.Graph()
    powl_graph.parse(data=turtle_text, format="turtle")

    powl2 = rdflib.Namespace("https://truex.io/ontology/powl2#")
    mfwp = rdflib.Namespace("urn:mfw:powl-trace:")

    models = list(powl_graph.subjects(rdflib.RDF.type, powl2.Model))
    assert len(models) == 1

    leaves = list(powl_graph.subjects(rdflib.RDF.type, powl2.ActivityLeaf))
    assert len(leaves) == 1
    labels = list(powl_graph.objects(leaves[0], powl2.activityLabel))
    assert [str(l) for l in labels] == ["pick-up"]

    digests = list(powl_graph.objects(models[0], mfwp.domainDigest))
    assert len(digests) == 1
    assert str(digests[0]).startswith("blake3:")


def test_missing_required_field_raises_named_rdf_domain_error(tmp_path):
    broken_ttl = tmp_path / "broken.ttl"
    broken_ttl.write_text(
        "@prefix pd: <urn:autofde-lab:planning-domain:> .\n"
        "@prefix ex: <urn:autofde-lab:planning-domain:broken:> .\n"
        "ex:domain a pd:Domain .\n"  # missing pd:domainName
        "ex:problem a pd:Problem ; pd:problemName \"broken\" ; pd:forDomain ex:domain .\n"
    )
    with pytest.raises(RdfDomainError):
        compile_rdf_to_pddl(str(broken_ttl))
