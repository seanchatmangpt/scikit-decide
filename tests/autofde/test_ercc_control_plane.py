from dataclasses import fields
from types import SimpleNamespace

from autofde_lab.autofde.ercc_control_plane import (
    CapabilitySnapshot,
    DomainSpec,
    HookProposal,
    KnowledgeHook,
    ObjectiveSpec,
    PlannerProfile,
    PlannerSpec,
    PlanningEvidenceDAG,
    PlanningRouteProposal,
    ProblemSpec,
    ProcessHypothesis,
    VerifiedOutcomeEvidence,
    choose_planning_route,
    compile_candidate_graph,
    compile_hook_proposal,
    infer_processes,
    project_proposal,
    select_hook,
    select_with_dspy,
)


def fixture_space():
    snapshot = CapabilitySnapshot(
        "snap-1",
        features=frozenset({"k8s", "rollback", "lama"}),
        evidence_refs=frozenset({"deploy-event", "pod-state"}),
        available_planners=frozenset({"fast-downward", "graph"}),
    )
    domains = [
        DomainSpec(
            "k8s-remediation", "pddl", frozenset({"k8s"}), frozenset({"pod-state"})
        ),
        DomainSpec("dependency-diagnosis", "graph", frozenset({"k8s"})),
    ]
    problems = [
        ProblemSpec(
            "rollback",
            frozenset({"k8s-remediation"}),
            frozenset({"rollback"}),
            frozenset({"deploy-event"}),
        ),
        ProblemSpec("dependency", frozenset({"dependency-diagnosis"})),
    ]
    planners = [
        PlannerSpec("fast-downward", frozenset({"pddl"}), frozenset({"lama"})),
        PlannerSpec("graph", frozenset({"graph"})),
    ]
    profiles = [
        PlannerProfile("lama-first", "fast-downward", frozenset({"lama"})),
        PlannerProfile("bounded", "graph"),
    ]
    objectives = [
        ObjectiveSpec("restore", frozenset({"rollback"})),
        ObjectiveSpec("explain", frozenset({"dependency"})),
    ]
    return snapshot, domains, problems, planners, profiles, objectives


def test_candidate_graph_enumerates_before_pruning_and_accounts_for_every_route():
    snapshot, domains, problems, planners, profiles, objectives = fixture_space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    assert len(graph.assessments) == 2 * 2 * 2 * 2 * 2
    assert len(graph.eligible) == 2
    assert len(graph.assessments) == len(graph.eligible) + len(graph.excluded)
    assert {r.problem_id for r in graph.eligible} == {"rollback", "dependency"}


def test_process_inference_preserves_multiple_hypotheses_and_explains_exclusions():
    snapshot, *_ = fixture_space()
    inference = infer_processes(
        snapshot,
        [
            ProcessHypothesis("h1", "k8s-remediation", "rollback", frozenset({"k8s"})),
            ProcessHypothesis(
                "h2", "dependency-diagnosis", "dependency", frozenset({"k8s"})
            ),
            ProcessHypothesis("h3", "quota", "quota", frozenset({"quota-signal"})),
        ],
    )
    assert [h.hypothesis_id for h in inference.compatible] == ["h1", "h2"]
    assert inference.excluded[0][0] == "h3"
    assert inference.excluded[0][1] == ("missing_features:quota-signal",)


def test_dspy_is_bounded_to_canonical_route_ids_and_cannot_smuggle_commands():
    snapshot, domains, problems, planners, profiles, objectives = fixture_space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    malicious = SimpleNamespace(
        route_id="$(kubectl delete namespace prod)",
        confidence="1",
        evidence_refs="[]",
        information_gaps="[]",
        abstain_reason="",
    )
    proposal = select_with_dspy(
        task="repair", snapshot=snapshot, graph=graph, predictor=lambda **_: malicious
    )
    assert proposal.route_id is None
    assert proposal.abstain_reason == "selector_returned_unknown_route"
    assert project_proposal(proposal, graph) is None
    forbidden = {
        "command",
        "args",
        "executable",
        "callable",
        "url",
        "authority",
        "actuate",
        "execute",
    }
    assert forbidden.isdisjoint({f.name for f in fields(PlanningRouteProposal)})


def test_dspy_selection_projects_from_canonical_graph_not_model_details():
    snapshot, domains, problems, planners, profiles, objectives = fixture_space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    route = graph.eligible[0]
    prediction = SimpleNamespace(
        route_id=route.route_id,
        confidence="0.91",
        evidence_refs='["pod-state"]',
        information_gaps="[]",
        abstain_reason="",
        command="rm -rf /",
    )
    proposal = select_with_dspy(
        task="repair", snapshot=snapshot, graph=graph, predictor=lambda **_: prediction
    )
    projected = project_proposal(proposal, graph)
    assert projected is not None
    assert projected.route == route
    assert not hasattr(projected.route, "command")


def test_known_hook_is_fast_path_and_stale_or_ambiguous_hooks_do_not_silently_select():
    snapshot, domains, problems, planners, profiles, objectives = fixture_space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    route = next(r for r in graph.eligible if r.problem_id == "rollback")
    hook = KnowledgeHook(
        "known-rollback",
        route.route_id,
        frozenset({"k8s", "rollback"}),
        frozenset({"deploy-event"}),
    )
    hit = select_hook(snapshot, graph, [hook])
    assert hit.proposal is not None and hit.proposal.route_id == route.route_id
    assert hit.proposal.selector == "knowledge-hook"
    stale = select_hook(
        snapshot, graph, [KnowledgeHook("stale", "route:missing", frozenset({"k8s"}))]
    )
    assert stale.proposal is None and stale.stale_hook_ids == ("stale",)
    ambiguous = select_hook(
        snapshot,
        graph,
        [
            hook,
            KnowledgeHook(
                "same-pattern",
                route.route_id,
                frozenset({"k8s", "rollback"}),
                frozenset({"deploy-event"}),
            ),
        ],
    )
    assert ambiguous.proposal is not None and ambiguous.proposal.route_id is None
    assert ambiguous.proposal.abstain_reason == "ambiguous_knowledge_hooks"


def test_verified_outcome_compiles_inert_hook_proposal_only():
    snapshot, domains, problems, planners, profiles, objectives = fixture_space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    route = graph.eligible[0]
    failed = VerifiedOutcomeEvidence(
        "ggen-receipt:1", route.route_id, False, True, frozenset({"k8s"})
    )
    unverified = VerifiedOutcomeEvidence(
        "ggen-receipt:2", route.route_id, True, False, frozenset({"k8s"})
    )
    assert compile_hook_proposal(failed, graph) is None
    assert compile_hook_proposal(unverified, graph) is None
    verified = VerifiedOutcomeEvidence(
        "ggen-receipt:3",
        route.route_id,
        True,
        True,
        frozenset({"k8s"}),
        frozenset({"pod-state"}),
    )
    proposal = compile_hook_proposal(verified, graph)
    assert isinstance(proposal, HookProposal)
    assert proposal.source_verification_ref == "ggen-receipt:3"
    forbidden = {"execute", "actuate", "authority", "command"}
    assert forbidden.isdisjoint({f.name for f in fields(HookProposal)})


def test_planning_evidence_dag_is_deterministic_and_parent_checked():
    snapshot, domains, problems, planners, profiles, objectives = fixture_space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    proposal = PlanningRouteProposal(graph.eligible[0].route_id, 1.0)
    dag = PlanningEvidenceDAG()
    first = dag.append(
        parents=(), task="repair", snapshot=snapshot, graph=graph, proposal=proposal
    )
    replay = dag.append(
        parents=(), task="repair", snapshot=snapshot, graph=graph, proposal=proposal
    )
    assert first == replay and len(dag.nodes) == 1
    second = dag.append(
        parents=(first.node_id,),
        task="verify",
        snapshot=snapshot,
        graph=graph,
        proposal=proposal,
    )
    assert second.parent_ids == (first.node_id,)
    try:
        dag.append(
            parents=("missing",),
            task="x",
            snapshot=snapshot,
            graph=graph,
            proposal=proposal,
        )
    except ValueError as exc:
        assert "unknown parent" in str(exc)
    else:
        raise AssertionError("unknown planning-evidence parent must fail")


def test_end_to_end_control_plane_bypasses_dspy_on_known_pattern_and_reports_coverage():
    snapshot, domains, problems, planners, profiles, objectives = fixture_space()
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    route = next(r for r in graph.eligible if r.problem_id == "rollback")
    calls = []

    def predictor(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            route_id=route.route_id,
            confidence=1,
            evidence_refs="[]",
            information_gaps="[]",
            abstain_reason="",
        )

    decision = choose_planning_route(
        task="restore checkout",
        snapshot=snapshot,
        hypotheses=[
            ProcessHypothesis("h1", "k8s-remediation", "rollback", frozenset({"k8s"}))
        ],
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
        hooks=[KnowledgeHook("known", route.route_id, frozenset({"rollback"}))],
        predictor=predictor,
    )
    assert calls == []
    assert decision.projected is not None and decision.projected.route == route
    assert decision.coverage.selection_mode == "knowledge-hook"
    assert decision.coverage.route_accounting_complete
    assert decision.coverage.hypothesis_accounting_complete
    assert decision.evidence_node.selector == "knowledge-hook"
