"""Exact-head composition court for the AutoFDE Lab planning surface.

Branch-local evidence does not transfer through a merge. This file binds the
merged ERRC planning control plane to the Lab's constitutional boundary:
planning may infer/select/construct inert route projections and evidence, but
it cannot acquire execution or authority surfaces.
"""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

from autofde_lab.autofde.ercc_control_plane import (
    CapabilitySnapshot,
    DomainSpec,
    HookProposal,
    KnowledgeHook,
    ObjectiveSpec,
    PlannerProfile,
    PlannerSpec,
    PlanningDecision,
    PlanningRouteProposal,
    ProblemSpec,
    ProcessHypothesis,
    ProjectedPlanningRoute,
    VerifiedOutcomeEvidence,
    choose_planning_route,
    compile_candidate_graph,
    compile_hook_proposal,
)

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE = ROOT / "src" / "autofde_lab" / "autofde" / "ercc_control_plane.py"


def _space():
    snapshot = CapabilitySnapshot(
        "composition-snapshot",
        features=frozenset({"k8s", "rollback", "lama"}),
        evidence_refs=frozenset({"pod-state", "deploy-event"}),
        available_planners=frozenset({"fast-downward", "graph"}),
    )
    domains = [
        DomainSpec("k8s", "pddl", frozenset({"k8s"}), frozenset({"pod-state"})),
        DomainSpec("dependency", "graph", frozenset({"k8s"})),
    ]
    problems = [
        ProblemSpec(
            "rollback",
            frozenset({"k8s"}),
            frozenset({"rollback"}),
            frozenset({"deploy-event"}),
        ),
        ProblemSpec("explain", frozenset({"dependency"})),
    ]
    planners = [
        PlannerSpec("fast-downward", frozenset({"pddl"}), frozenset({"lama"})),
        PlannerSpec("graph", frozenset({"graph"})),
    ]
    profiles = [
        PlannerProfile("lama", "fast-downward", frozenset({"lama"})),
        PlannerProfile("bounded", "graph"),
    ]
    objectives = [
        ObjectiveSpec("restore", frozenset({"rollback"})),
        ObjectiveSpec("explain", frozenset({"explain"})),
    ]
    return snapshot, domains, problems, planners, profiles, objectives


def test_exact_composition_keeps_planning_projection_inert() -> None:
    snapshot, domains, problems, planners, profiles, objectives = _space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    rollback = next(route for route in graph.eligible if route.problem_id == "rollback")

    calls: list[dict[str, object]] = []

    def predictor(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            route_id=rollback.route_id,
            confidence="0.99",
            evidence_refs='["pod-state","deploy-event"]',
            information_gaps="[]",
            abstain_reason="",
            # This is deliberate adversarial narration. The projection must
            # have no field through which it can survive into execution.
            command="kubectl delete namespace prod",
            authority_ref="ambient-admin",
        )

    decision = choose_planning_route(
        task="restore the deployment",
        snapshot=snapshot,
        hypotheses=(
            ProcessHypothesis("h-rollback", "k8s", "rollback", frozenset({"k8s"})),
        ),
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
        predictor=predictor,
    )

    assert isinstance(decision, PlanningDecision)
    assert len(calls) == 1
    assert isinstance(decision.projected, ProjectedPlanningRoute)
    assert decision.projected.route == rollback
    assert decision.coverage.route_accounting_complete is True
    assert decision.coverage.hypothesis_accounting_complete is True

    forbidden = {
        "command",
        "args",
        "executable",
        "authority",
        "authority_ref",
        "grant",
        "token",
        "actuate",
        "execute",
        "url",
    }
    assert forbidden.isdisjoint({field.name for field in fields(PlanningRouteProposal)})
    assert forbidden.isdisjoint(
        {field.name for field in fields(ProjectedPlanningRoute)}
    )
    assert forbidden.isdisjoint({field.name for field in fields(HookProposal)})


def test_verified_outcome_only_compiles_an_inert_hook_after_real_verification_reference() -> (
    None
):
    snapshot, domains, problems, planners, profiles, objectives = _space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    route = next(route for route in graph.eligible if route.problem_id == "rollback")

    assert (
        compile_hook_proposal(
            VerifiedOutcomeEvidence(
                "",
                route.route_id,
                successful=True,
                verified=True,
                observed_features=frozenset({"k8s", "rollback"}),
            ),
            graph,
        )
        is None
    )
    assert (
        compile_hook_proposal(
            VerifiedOutcomeEvidence(
                "verify:failed",
                route.route_id,
                successful=False,
                verified=True,
                observed_features=frozenset({"k8s", "rollback"}),
            ),
            graph,
        )
        is None
    )

    proposal = compile_hook_proposal(
        VerifiedOutcomeEvidence(
            "verify:exact-subject:composition",
            route.route_id,
            successful=True,
            verified=True,
            observed_features=frozenset({"k8s", "rollback"}),
            evidence_refs=frozenset({"pod-state", "deploy-event"}),
        ),
        graph,
    )
    assert isinstance(proposal, HookProposal)
    assert proposal.source_verification_ref == "verify:exact-subject:composition"


def test_known_hook_fast_path_is_selection_only_not_actuation() -> None:
    snapshot, domains, problems, planners, profiles, objectives = _space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    route = next(route for route in graph.eligible if route.problem_id == "rollback")

    called = False

    def predictor(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "known lawful pattern should compile out repeated cognition"
        )

    decision = choose_planning_route(
        task="restore the deployment",
        snapshot=snapshot,
        hypotheses=(ProcessHypothesis("h", "k8s", "rollback"),),
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
        hooks=(
            KnowledgeHook(
                "known-rollback",
                route.route_id,
                required_features=frozenset({"k8s", "rollback"}),
                required_evidence=frozenset({"deploy-event"}),
            ),
        ),
        predictor=predictor,
    )
    assert called is False
    assert decision.projected is not None
    assert decision.proposal.selector == "knowledge-hook"
    assert decision.evidence_node.selector == "knowledge-hook"


def test_control_plane_source_has_no_direct_io_or_actuation_import_surface() -> None:
    """A merge cannot quietly turn the planning control plane into a second DO path."""
    tree = ast.parse(
        CONTROL_PLANE.read_text(encoding="utf-8"), filename=str(CONTROL_PLANE)
    )
    imported: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)

    forbidden_import_roots = {
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "boto3",
        "azure",
        "google.cloud",
        "kubernetes",
        "terraform",
    }
    assert not any(
        name == root or name.startswith(root + ".")
        for name in imported
        for root in forbidden_import_roots
    )
    assert {"system", "popen", "Popen", "exec", "eval"}.isdisjoint(calls)
