"""ERRC planning control plane: candidate-side only, never admission or actuation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from itertools import product
from typing import Any, Iterable, Protocol, Sequence


def _digest(value: Any) -> str:
    def default(obj: Any) -> Any:
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        if isinstance(obj, (set, frozenset)):
            return sorted(obj)
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(type(obj).__name__)

    raw = json.dumps(
        value, default=default, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class CapabilitySnapshot:
    snapshot_id: str
    features: frozenset[str] = frozenset()
    evidence_refs: frozenset[str] = frozenset()
    available_planners: frozenset[str] = frozenset()

    @property
    def digest(self) -> str:
        return _digest(self)


@dataclass(frozen=True)
class ProcessHypothesis:
    hypothesis_id: str
    domain_id: str
    problem_id: str
    required_features: frozenset[str] = frozenset()
    required_evidence: frozenset[str] = frozenset()
    contradicted_by_features: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ProcessInference:
    compatible: tuple[ProcessHypothesis, ...]
    excluded: tuple[tuple[str, tuple[str, ...]], ...]


def infer_processes(
    snapshot: CapabilitySnapshot, hypotheses: Iterable[ProcessHypothesis]
) -> ProcessInference:
    compatible, excluded = [], []
    for h in sorted(hypotheses, key=lambda x: x.hypothesis_id):
        reasons = []
        missing_features = h.required_features - snapshot.features
        missing_evidence = h.required_evidence - snapshot.evidence_refs
        contradictions = h.contradicted_by_features & snapshot.features
        if missing_features:
            reasons.append("missing_features:" + ",".join(sorted(missing_features)))
        if missing_evidence:
            reasons.append("missing_evidence:" + ",".join(sorted(missing_evidence)))
        if contradictions:
            reasons.append("contradicted_by:" + ",".join(sorted(contradictions)))
        (excluded if reasons else compatible).append(
            (h.hypothesis_id, tuple(reasons)) if reasons else h
        )
    return ProcessInference(tuple(compatible), tuple(excluded))


@dataclass(frozen=True)
class DomainSpec:
    domain_id: str
    formalism: str
    required_features: frozenset[str] = frozenset()
    required_evidence: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ProblemSpec:
    problem_id: str
    domain_ids: frozenset[str]
    required_features: frozenset[str] = frozenset()
    required_evidence: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PlannerSpec:
    planner_id: str
    formalisms: frozenset[str]
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PlannerProfile:
    profile_id: str
    planner_id: str
    required_capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ObjectiveSpec:
    objective_id: str
    problem_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PlanningRoute:
    route_id: str
    domain_id: str
    problem_id: str
    formalism: str
    planner_id: str
    profile_id: str
    objective_id: str


@dataclass(frozen=True)
class CandidateAssessment:
    route: PlanningRoute
    eligible: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateGraph:
    assessments: tuple[CandidateAssessment, ...]
    digest: str

    @property
    def eligible(self) -> tuple[PlanningRoute, ...]:
        return tuple(a.route for a in self.assessments if a.eligible)

    @property
    def excluded(self) -> tuple[CandidateAssessment, ...]:
        return tuple(a for a in self.assessments if not a.eligible)

    def eligible_by_id(self) -> dict[str, PlanningRoute]:
        return {r.route_id: r for r in self.eligible}


def _route_id(
    domain: DomainSpec,
    problem: ProblemSpec,
    planner: PlannerSpec,
    profile: PlannerProfile,
    objective: ObjectiveSpec,
) -> str:
    value = (
        domain.domain_id,
        problem.problem_id,
        domain.formalism,
        planner.planner_id,
        profile.profile_id,
        objective.objective_id,
    )
    return "route:" + _digest(value)[:24]


def compile_candidate_graph(
    snapshot: CapabilitySnapshot,
    *,
    domains: Sequence[DomainSpec],
    problems: Sequence[ProblemSpec],
    planners: Sequence[PlannerSpec],
    profiles: Sequence[PlannerProfile],
    objectives: Sequence[ObjectiveSpec],
) -> CandidateGraph:
    """Enumerate full Domain x Problem x Planner x Profile x Objective before pruning."""
    items = []
    for domain, problem, planner, profile, objective in product(
        domains, problems, planners, profiles, objectives
    ):
        route = PlanningRoute(
            _route_id(domain, problem, planner, profile, objective),
            domain.domain_id,
            problem.problem_id,
            domain.formalism,
            planner.planner_id,
            profile.profile_id,
            objective.objective_id,
        )
        reasons = []
        if domain.domain_id not in problem.domain_ids:
            reasons.append("problem_domain_incompatible")
        if domain.formalism not in planner.formalisms:
            reasons.append("planner_formalism_incompatible")
        if profile.planner_id != planner.planner_id:
            reasons.append("profile_planner_incompatible")
        if objective.problem_ids and problem.problem_id not in objective.problem_ids:
            reasons.append("objective_problem_incompatible")
        if planner.planner_id not in snapshot.available_planners:
            reasons.append("planner_unavailable")
        missing_features = (
            domain.required_features
            | problem.required_features
            | profile.required_capabilities
        ) - (snapshot.features | planner.capabilities)
        missing_evidence = (
            domain.required_evidence | problem.required_evidence
        ) - snapshot.evidence_refs
        if missing_features:
            reasons.append("missing_features:" + ",".join(sorted(missing_features)))
        if missing_evidence:
            reasons.append("missing_evidence:" + ",".join(sorted(missing_evidence)))
        items.append(CandidateAssessment(route, not reasons, tuple(reasons)))
    items.sort(key=lambda a: a.route.route_id)
    return CandidateGraph(tuple(items), _digest(items))


@dataclass(frozen=True)
class PlanningRouteProposal:
    route_id: str | None
    confidence: float
    evidence_refs: tuple[str, ...] = ()
    information_gaps: tuple[str, ...] = ()
    abstain_reason: str | None = None
    selector: str = "adaptive"


@dataclass(frozen=True)
class ProjectedPlanningRoute:
    route: PlanningRoute
    confidence: float
    evidence_refs: tuple[str, ...]
    selector: str


def project_proposal(
    proposal: PlanningRouteProposal, graph: CandidateGraph
) -> ProjectedPlanningRoute | None:
    route = graph.eligible_by_id().get(proposal.route_id) if proposal.route_id else None
    if route is None:
        return None
    return ProjectedPlanningRoute(
        route,
        max(0.0, min(1.0, float(proposal.confidence))),
        tuple(sorted(set(proposal.evidence_refs))),
        proposal.selector,
    )


class Predictor(Protocol):
    def __call__(self, **kwargs: Any) -> Any: ...


def _seq(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = [x.strip() for x in value.split(",") if x.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(x) for x in value)
    return (str(value),)


def select_with_dspy(
    *,
    task: str,
    snapshot: CapabilitySnapshot,
    graph: CandidateGraph,
    predictor: Predictor | None = None,
) -> PlanningRouteProposal:
    """DSPy may select only a supplied eligible route id or abstain."""
    candidates = [asdict(r) for r in graph.eligible]
    if not candidates:
        return PlanningRouteProposal(
            None,
            1.0,
            information_gaps=("no_eligible_routes",),
            abstain_reason="no_eligible_routes",
        )
    if predictor is None:
        try:
            import dspy
        except ImportError as exc:
            raise RuntimeError(
                "DSPy selection requires the optional 'dspy' extra"
            ) from exc

        class SelectPlanningRoute(dspy.Signature):
            """Select exactly one supplied route_id or abstain."""

            task = dspy.InputField()
            snapshot = dspy.InputField()
            candidates = dspy.InputField(
                desc="Eligible canonical routes; never invent an id"
            )
            route_id = dspy.OutputField(
                desc="One supplied route_id, or empty to abstain"
            )
            confidence = dspy.OutputField(desc="0..1")
            evidence_refs = dspy.OutputField(desc="JSON list")
            information_gaps = dspy.OutputField(desc="JSON list")
            abstain_reason = dspy.OutputField()

        predictor = dspy.Predict(SelectPlanningRoute)
    prediction = predictor(
        task=task,
        snapshot=json.dumps(asdict(snapshot), default=sorted, sort_keys=True),
        candidates=json.dumps(candidates, sort_keys=True),
    )
    route_id = str(getattr(prediction, "route_id", "") or "").strip() or None
    if route_id is not None and route_id not in graph.eligible_by_id():
        return PlanningRouteProposal(
            None,
            0.0,
            information_gaps=("selector_returned_unknown_route",),
            abstain_reason="selector_returned_unknown_route",
            selector="dspy-invalid",
        )
    try:
        confidence = float(getattr(prediction, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return PlanningRouteProposal(
        route_id,
        max(0.0, min(1.0, confidence)),
        _seq(getattr(prediction, "evidence_refs", ())),
        _seq(getattr(prediction, "information_gaps", ())),
        str(getattr(prediction, "abstain_reason", "") or "").strip() or None,
        "dspy",
    )


@dataclass(frozen=True)
class KnowledgeHook:
    hook_id: str
    route_id: str
    required_features: frozenset[str] = frozenset()
    required_evidence: frozenset[str] = frozenset()
    forbidden_features: frozenset[str] = frozenset()

    def matches(self, snapshot: CapabilitySnapshot) -> bool:
        return (
            self.required_features <= snapshot.features
            and self.required_evidence <= snapshot.evidence_refs
            and not (self.forbidden_features & snapshot.features)
        )


@dataclass(frozen=True)
class HookSelection:
    proposal: PlanningRouteProposal | None
    matched_hook_ids: tuple[str, ...] = ()
    stale_hook_ids: tuple[str, ...] = ()


def select_hook(
    snapshot: CapabilitySnapshot, graph: CandidateGraph, hooks: Iterable[KnowledgeHook]
) -> HookSelection:
    hooks = tuple(sorted(hooks, key=lambda h: h.hook_id))
    eligible = graph.eligible_by_id()
    matched, stale = [], []
    by_id = {h.hook_id: h for h in hooks}
    for hook in hooks:
        if not hook.matches(snapshot):
            continue
        (matched if hook.route_id in eligible else stale).append(hook.hook_id)
    if not matched:
        return HookSelection(None, (), tuple(stale))
    if len(matched) > 1:
        return HookSelection(
            PlanningRouteProposal(
                None,
                1.0,
                information_gaps=("ambiguous_knowledge_hooks",),
                abstain_reason="ambiguous_knowledge_hooks",
                selector="knowledge-hook",
            ),
            tuple(matched),
            tuple(stale),
        )
    hook = by_id[matched[0]]
    return HookSelection(
        PlanningRouteProposal(
            hook.route_id,
            1.0,
            tuple(sorted(hook.required_evidence)),
            selector="knowledge-hook",
        ),
        tuple(matched),
        tuple(stale),
    )


@dataclass(frozen=True)
class VerifiedOutcomeEvidence:
    verification_ref: str
    route_id: str
    successful: bool
    verified: bool
    observed_features: frozenset[str]
    evidence_refs: frozenset[str] = frozenset()


@dataclass(frozen=True)
class HookProposal:
    hook_id: str
    route_id: str
    required_features: frozenset[str]
    required_evidence: frozenset[str]
    source_verification_ref: str


def compile_hook_proposal(
    outcome: VerifiedOutcomeEvidence, graph: CandidateGraph
) -> HookProposal | None:
    """Compile verified downstream evidence into an inert hook proposal only."""
    if (
        not outcome.verified
        or not outcome.successful
        or not outcome.verification_ref.strip()
    ):
        return None
    if outcome.route_id not in graph.eligible_by_id():
        return None
    identity = (
        outcome.route_id,
        sorted(outcome.observed_features),
        sorted(outcome.evidence_refs),
        outcome.verification_ref,
    )
    return HookProposal(
        "hook:" + _digest(identity)[:24],
        outcome.route_id,
        outcome.observed_features,
        outcome.evidence_refs,
        outcome.verification_ref,
    )


@dataclass(frozen=True)
class PlanningEvidenceNode:
    """Planning-call replay binding; explicitly not an execution receipt."""

    node_id: str
    parent_ids: tuple[str, ...]
    input_digest: str
    snapshot_digest: str
    candidate_graph_digest: str
    output_digest: str
    selector: str


@dataclass
class PlanningEvidenceDAG:
    nodes: dict[str, PlanningEvidenceNode] = field(default_factory=dict)

    def append(
        self,
        *,
        parents: Sequence[str],
        task: str,
        snapshot: CapabilitySnapshot,
        graph: CandidateGraph,
        proposal: PlanningRouteProposal,
    ) -> PlanningEvidenceNode:
        unknown = sorted(set(parents) - self.nodes.keys())
        if unknown:
            raise ValueError("unknown parent nodes: " + ",".join(unknown))
        body = {
            "parents": sorted(parents),
            "input": _digest(task),
            "snapshot": snapshot.digest,
            "graph": graph.digest,
            "output": _digest(proposal),
            "selector": proposal.selector,
        }
        node = PlanningEvidenceNode(
            "planning-call:" + _digest(body)[:32],
            tuple(sorted(parents)),
            body["input"],
            body["snapshot"],
            body["graph"],
            body["output"],
            proposal.selector,
        )
        self.nodes[node.node_id] = node
        return node


@dataclass(frozen=True)
class CoverageReport:
    enumerated_routes: int
    eligible_routes: int
    excluded_routes: int
    compatible_hypotheses: int
    excluded_hypotheses: int
    hook_matches: int
    stale_hooks: int
    selection_mode: str
    route_accounting_complete: bool
    hypothesis_accounting_complete: bool


def coverage_report(
    *,
    graph: CandidateGraph,
    inference: ProcessInference,
    hook_selection: HookSelection,
    proposal: PlanningRouteProposal,
) -> CoverageReport:
    total, eligible, excluded = (
        len(graph.assessments),
        len(graph.eligible),
        len(graph.excluded),
    )
    h_total = len(inference.compatible) + len(inference.excluded)
    return CoverageReport(
        total,
        eligible,
        excluded,
        len(inference.compatible),
        len(inference.excluded),
        len(hook_selection.matched_hook_ids),
        len(hook_selection.stale_hook_ids),
        proposal.selector,
        total == eligible + excluded,
        h_total > 0,
    )


@dataclass(frozen=True)
class PlanningDecision:
    inference: ProcessInference
    graph: CandidateGraph
    proposal: PlanningRouteProposal
    projected: ProjectedPlanningRoute | None
    coverage: CoverageReport
    evidence_node: PlanningEvidenceNode


def choose_planning_route(
    *,
    task: str,
    snapshot: CapabilitySnapshot,
    hypotheses: Sequence[ProcessHypothesis],
    domains: Sequence[DomainSpec],
    problems: Sequence[ProblemSpec],
    planners: Sequence[PlannerSpec],
    profiles: Sequence[PlannerProfile],
    objectives: Sequence[ObjectiveSpec],
    hooks: Sequence[KnowledgeHook] = (),
    predictor: Predictor | None = None,
    evidence_dag: PlanningEvidenceDAG | None = None,
    parents: Sequence[str] = (),
) -> PlanningDecision:
    """Known hook first, otherwise DSPy; return inert candidate-side projection."""
    inference = infer_processes(snapshot, hypotheses)
    graph = compile_candidate_graph(
        snapshot,
        domains=domains,
        problems=problems,
        planners=planners,
        profiles=profiles,
        objectives=objectives,
    )
    hook_selection = select_hook(snapshot, graph, hooks)
    proposal = hook_selection.proposal or select_with_dspy(
        task=task, snapshot=snapshot, graph=graph, predictor=predictor
    )
    projected = project_proposal(proposal, graph)
    coverage = coverage_report(
        graph=graph,
        inference=inference,
        hook_selection=hook_selection,
        proposal=proposal,
    )
    dag = evidence_dag if evidence_dag is not None else PlanningEvidenceDAG()
    node = dag.append(
        parents=parents, task=task, snapshot=snapshot, graph=graph, proposal=proposal
    )
    return PlanningDecision(inference, graph, proposal, projected, coverage, node)
