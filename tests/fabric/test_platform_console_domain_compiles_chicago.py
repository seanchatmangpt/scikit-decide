# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style: real ``ontology/platform-console-domain.ttl`` (all ~30
platform-console fabric capabilities, encoded as pd:Action individuals) ->
real compiled PDDL -> real scikit-decide Astar solve, through the existing,
UNMODIFIED ``compile_rdf_to_pddl_files`` / ``pddl_engine.solve_to_plan_file``
pipeline.

No mock/patch/monkeypatch anywhere. rdflib parses the real Turtle fixture on
disk, ``pddl_engine.solve_to_plan_file`` runs the real registered Astar
solver against the real compiled PDDL text. Assertions are state-based: the
real parsed graph, the real compiled PDDL text, the real plan file contents
and exit codes -- never "was X called".

Three real goal states, per the task's own reversible/gated/irreversible
distinction:

1. ``test_reversible_capability_quota_override_solves`` -- a reversible
   capability (quota.override) with a real Astar plan found.
2. ``test_approval_gated_capability_castle_schedule_solves`` -- an
   approval-gated capability (castle.verb.schedule) reachable only because
   the fixture's init state asserts ``approved``.
3. ``test_irreversible_capability_org_delete_is_correctly_refused`` -- an
   IRREVERSIBLE capability (org.delete) whose goal is deliberately
   unreachable because ``approved`` is never true for the target object in
   this problem's init state, so Astar must return EXIT_NO_PLAN. This is
   the correct test for an irreversible action per this session's own
   SELECT!=DO/CONSTRUCT!=DO doctrine: it proves the precondition gate
   BLOCKS the destructive action, never that the action was performed.
"""

from __future__ import annotations

import os

import rdflib

from autofde_lab.fabric import pddl_engine
from autofde_lab.fabric.rdf_domain import PD, compile_rdf_to_pddl, compile_rdf_to_pddl_files

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ontology",
    "platform-console-domain.ttl",
)

DOMAIN_IRI = "urn:autofde-lab:planning-domain:platform-console:domain"


def test_fixture_is_valid_turtle_with_all_capability_actions_present():
    graph = rdflib.Graph()
    graph.parse(FIXTURE, format="turtle")

    domains = list(graph.subjects(rdflib.RDF.type, PD.Domain))
    assert len(domains) == 1

    problems = list(graph.subjects(rdflib.RDF.type, PD.Problem))
    assert len(problems) == 3

    action_names = {
        str(graph.value(a, PD.actionName))
        for a in graph.objects(domains[0], PD.hasAction)
    }
    # Representative sample across all three capability tiers named in the
    # task: CASTLE (reversible), approval-gated, capability-intrinsic.
    expected_present = {
        "castle-inventory-components",
        "castle-fortune5-requirements",
        "org-delete",
        "quota-override",
        "dr-failover",
        "dsar-erasure",
        "sla-credit-apply",
        "patch-sla-credit-apply",
        "castle-schedule",
        "freeze-override",
        "create-namespace",
        "create-project",
        "delete-project",
        "create-secret",
        "delete-secret",
        "create-backup-job",
        "create-restore-job",
        "delete-job",
        "patch-resource-quota-hard",
        "patch-deployment-replicas",
        "patch-namespace-annotations",
        "create-org",
        "delete-org",
        "set-org-branding",
        "set-org-region",
        "set-org-custom-domain",
        "set-org-sla",
        "set-org-auto-remediate-critical",
        "create-reservation",
        "cancel-reservation",
        "create-partner",
        "update-partner",
        "delete-partner",
    }
    assert expected_present <= action_names
    # At least the ~30 named capabilities, plus the two support actions
    # (deploy/freeze) that make deployment-/freeze-dependent preconditions
    # reachable at all.
    assert len(action_names) >= 30


def test_compile_rdf_to_pddl_produces_parseable_pddl_for_each_problem():
    for problem_iri in (
        "urn:autofde-lab:planning-domain:platform-console:problem-reversible",
        "urn:autofde-lab:planning-domain:platform-console:problem-gated",
        "urn:autofde-lab:planning-domain:platform-console:problem-irreversible-refused",
    ):
        domain_text, problem_text = compile_rdf_to_pddl(
            FIXTURE, domain_iri=DOMAIN_IRI, problem_iri=problem_iri
        )
        assert domain_text.startswith("(define (domain platform-console)")
        assert ":requirements :strips" in domain_text
        assert problem_text.startswith("(define (problem ")
        assert "(:domain platform-console)" in problem_text


def _compile_and_solve(tmp_path, problem_iri, tag):
    domain_p = str(tmp_path / f"{tag}-domain.pddl")
    problem_p = str(tmp_path / f"{tag}-problem.pddl")
    plan_p = str(tmp_path / f"{tag}-plan.txt")

    compile_rdf_to_pddl_files(
        FIXTURE, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=problem_iri
    )

    # Real pre-flight gate: no unimplemented PDDL requirement declared.
    assert pddl_engine.unsupported_requirements(domain_p, problem_p) == []

    rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)
    return rc, plan_p


def test_reversible_capability_quota_override_solves(tmp_path):
    rc, plan_p = _compile_and_solve(
        tmp_path,
        "urn:autofde-lab:planning-domain:platform-console:problem-reversible",
        "reversible",
    )
    assert rc == pddl_engine.EXIT_PLAN_FOUND
    plan_text = open(plan_p, encoding="utf-8").read()
    # Both quota-override and patch-resource-quota-hard achieve
    # quota-hard-set(res1); either is a valid real Astar plan for this
    # goal, so accept whichever the real solver found.
    assert "quota-override res1" in plan_text or "patch-resource-quota-hard res1" in plan_text


def test_approval_gated_capability_castle_schedule_solves(tmp_path):
    rc, plan_p = _compile_and_solve(
        tmp_path,
        "urn:autofde-lab:planning-domain:platform-console:problem-gated",
        "gated",
    )
    assert rc == pddl_engine.EXIT_PLAN_FOUND
    plan_text = open(plan_p, encoding="utf-8").read()
    assert "(castle-schedule res2)" in plan_text


def test_irreversible_capability_org_delete_is_correctly_refused(tmp_path):
    """org.delete requires ``approved``, which is never asserted for res3
    in this problem's init state -- so no ground action can ever fire, and
    the real Astar solve must correctly report EXIT_NO_PLAN rather than
    finding a plan that deletes the org. Proves the gate BLOCKS the
    destructive action; this test never actuates org.delete."""
    rc, plan_p = _compile_and_solve(
        tmp_path,
        "urn:autofde-lab:planning-domain:platform-console:problem-irreversible-refused",
        "irreversible",
    )
    assert rc == pddl_engine.EXIT_NO_PLAN
    assert not os.path.exists(plan_p)
