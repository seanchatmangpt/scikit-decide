# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style round trip for the real chatman-ecosystem platform-console
capability slice: real RDF Turtle
(``ontology/platform-console-freeze-override-domain.ttl``) -> compiled PDDL
-> real scikit-decide Astar solve -> real POWL2 Turtle projection.

RECONCILIATION NOTE: this fixture is a deliberately separate file from the
committed ``ontology/platform-console-domain.ttl`` (the ~30-action,
3-pd:Problem capability-suite fixture that
``test_platform_console_domain_compiles_chicago.py`` /
``test_platform_console_full_capability_suite_chicago.py`` /
``test_platform_console_domain_mutation_chicago.py`` depend on verbatim).
``autofde_lab.fabric.rdf_domain.compile_rdf_to_pddl`` requires the graph to
contain exactly one ``pd:Problem`` when called with no ``problem_iri`` (as
this file's own tests below do) -- a real, structural constraint in
``rdf_domain.py``, not a stylistic choice -- so the two fixture shapes
cannot share one physical Turtle file without breaking one of the two call
conventions. See ``ontology/platform-console-freeze-override-domain.ttl``'s
own header comment for the full analysis.

Reuses autofde-lab's existing RDF->PDDL->plan pipeline UNMODIFIED (per
``~/.claude/plans/eager-forging-sparrow.md`` Phase 3): this test imports
``autofde_lab.fabric.rdf_domain`` and ``autofde_lab.fabric.pddl_engine`` as
they already exist, with no changes to either module -- exactly the same
pattern as ``test_rdf_domain_roundtrip_chicago.py``'s blocks-world fixture,
applied to a new fixture domain.

The fixture encodes the 3 in-scope real capabilities from Phase 1/2 of that
plan (``castle.verb.inventory-components``, ``castle.verb.inventory-goals``,
``approval.freeze-override``) over the ground-fact predicates the real,
live ``capability-state-snapshot`` route returns: ``(deployed castle)``,
``(frozen <org>)``, ``(freeze-override-approved <org>)``,
``(job-complete <verb>)``.

No mock/patch/monkeypatch anywhere. Every collaborator is real: rdflib
parses a real Turtle file on disk, ``pddl_engine.solve_to_plan_file`` runs
the real registered Astar solver against the real compiled PDDL text, and
``powl.py`` computes real blake3 digests over the real compiled PDDL files.
Assertions are state-based: the real plan file contents and the real POWL
Turtle graph, not "was X called".
"""

from __future__ import annotations

import os

import rdflib

from autofde_lab.fabric import pddl_engine
from autofde_lab.fabric.rdf_domain import (
    PD,
    compile_rdf_to_pddl,
    compile_rdf_to_pddl_files,
)

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ontology",
    "platform-console-freeze-override-domain.ttl",
)


def test_fixture_is_valid_turtle_conforming_to_the_ontology():
    graph = rdflib.Graph()
    graph.parse(FIXTURE, format="turtle")
    domains = list(graph.subjects(rdflib.RDF.type, PD.Domain))
    problems = list(graph.subjects(rdflib.RDF.type, PD.Problem))
    assert len(domains) == 1
    assert len(problems) == 1


def test_compile_rdf_to_pddl_produces_the_real_platform_console_domain_text():
    domain_text, problem_text = compile_rdf_to_pddl(FIXTURE)

    assert domain_text == (
        "(define (domain platform-console)\n"
        "  (:requirements :strips)\n"
        "  (:predicates (deployed ?c) (frozen ?o) (freeze-override-approved ?o) (job-complete ?v))\n"
        "  (:action freeze-override\n"
        "    :parameters (?o)\n"
        "    :precondition (frozen ?o)\n"
        "    :effect (freeze-override-approved ?o))\n"
        "  (:action run-verb\n"
        "    :parameters (?c ?o ?v)\n"
        "    :precondition (and (deployed ?c) (freeze-override-approved ?o))\n"
        "    :effect (job-complete ?v)))\n"
    )
    assert problem_text == (
        "(define (problem platform-console-1)\n"
        "  (:domain platform-console)\n"
        "  (:objects castle org1 v-inventory-components v-inventory-goals)\n"
        "  (:init (deployed castle) (frozen org1))\n"
        "  (:goal (and (job-complete v-inventory-components) (job-complete v-inventory-goals))))\n"
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
    plan_lines = open(plan_p, encoding="utf-8").read().splitlines()
    # A real Astar solve must gate both castle verbs behind the maker-checker
    # freeze-override action -- (frozen org1) is the only initial fact
    # (freeze-override-approved org1) can come from, and run-verb's
    # precondition requires it. This is exactly the maker-checker ordering
    # constraint the plan's Phase 1 rationale named for choosing
    # approval.freeze-override into scope.
    assert plan_lines[0] == "(freeze-override org1)"
    assert set(plan_lines[1:3]) == {
        "(run-verb castle org1 v-inventory-components)",
        "(run-verb castle org1 v-inventory-goals)",
    }


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
        powl_base_iri="urn:autofde-lab:rdf-roundtrip:platform-console",
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
    assert len(leaves) == 3
    labels = sorted(
        str(l) for leaf in leaves for l in powl_graph.objects(leaf, powl2.activityLabel)
    )
    assert labels == ["freeze-override", "run-verb", "run-verb"]

    digests = list(powl_graph.objects(models[0], mfwp.domainDigest))
    assert len(digests) == 1
    assert str(digests[0]).startswith("blake3:")

    activity_counts = list(powl_graph.objects(models[0], mfwp.activityCount))
    assert [int(c) for c in activity_counts] == [3]
