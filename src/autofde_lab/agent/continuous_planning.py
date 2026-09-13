# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Continuous, cache-aware planning over POWL candidate plans.

This module is SELECT/CONSTRUCT only. It retrieves candidate plans, checks
applicability, computes delta-local repair cones, and guards promotion against
historical regressions. It never actuates, grants authority, brokers execution,
or manufactures an execution receipt.

Similarity/retrieval is deliberately weaker than admission:
``retrieve_candidates(context)`` may return plans that ``admit_plan`` refuses.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Protocol

from autofde_lab.agent.replan import ReplanningMode
from autofde_lab.fabric.canonical import sha256
from autofde_lab.powl.algebra import PowlNode
from autofde_lab.powl.executor import NodePath
from autofde_lab.powl.identity import node_id

__all__ = [
    "AdmissionCode",
    "AnchorVerdict",
    "ContinuousPlanDecision",
    "ContinuousPlanner",
    "ObservationDelta",
    "PlanAdmission",
    "PlanApplicability",
    "PlanArtifact",
    "PlanCache",
    "PlanDisposition",
    "PlanRepository",
    "PlanningContext",
    "PromotionDecision",
    "PromotionPolicy",
    "admit_plan",
    "affected_paths",
    "evaluate_promotion",
]


def _path_key(path: NodePath) -> str:
    return "/".join(str(i) for i in path)


@dataclass(frozen=True, slots=True)
class PlanApplicability:
    """Symbolic applicability envelope; never an authority grant."""

    goal: str
    required_facts: frozenset[str] = frozenset()
    forbidden_facts: frozenset[str] = frozenset()
    required_capabilities: frozenset[str] = frozenset()
    constraint_digest: str = ""
    semantic_revision: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "required_facts": sorted(self.required_facts),
            "forbidden_facts": sorted(self.forbidden_facts),
            "required_capabilities": sorted(self.required_capabilities),
            "constraint_digest": self.constraint_digest,
            "semantic_revision": self.semantic_revision,
        }

    @property
    def retrieval_signature(self) -> str:
        """Coarse candidate-retrieval identity, explicitly not an admission proof."""
        return sha256(
            {
                "goal": self.goal,
                "constraint_digest": self.constraint_digest,
                "semantic_revision": self.semantic_revision,
            }
        )


@dataclass(frozen=True, slots=True)
class PlanArtifact:
    """Content-addressed candidate plan plus its declared dependency topology."""

    model: PowlNode
    applicability: PlanApplicability
    planner: str
    planner_parameters: Mapping[str, object] = field(default_factory=dict)
    dependency_keys: Mapping[NodePath, frozenset[str]] = field(default_factory=dict)
    downstream: Mapping[NodePath, frozenset[NodePath]] = field(default_factory=dict)
    family_id: str | None = None
    version: int = 1
    # Describes the authority classes an eventual executor may need. These
    # strings never represent a grant and are not inspected by admission.
    required_authority_classes: tuple[str, ...] = ()

    @property
    def model_sha256(self) -> str:
        return node_id(self.model)

    @property
    def exact_key(self) -> str:
        dependencies = {
            _path_key(path): sorted(values)
            for path, values in sorted(self.dependency_keys.items())
        }
        downstream = {
            _path_key(path): sorted(_path_key(p) for p in values)
            for path, values in sorted(self.downstream.items())
        }
        return sha256(
            {
                "schema": "urn:autofde-lab:plan-artifact:1",
                "model_sha256": self.model_sha256,
                "applicability": self.applicability.as_dict(),
                "planner": self.planner,
                "planner_parameters": dict(self.planner_parameters),
                "dependency_keys": dependencies,
                "downstream": downstream,
                "family_id": self.family_id,
                "version": self.version,
                "required_authority_classes": list(self.required_authority_classes),
            }
        )


@dataclass(frozen=True, slots=True)
class PlanningContext:
    """Admitted planning facts available to SELECT; no ambient DO authority."""

    goal: str
    facts: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    constraint_digest: str = ""
    semantic_revision: str = ""


class PlanRepository(Protocol):
    """Powerless candidate-memory boundary consumed by ``ContinuousPlanner``.

    Implementations may be in-memory, SQLite, or an external HA store. The
    contract intentionally contains no admission, authority, broker, actuation,
    or receipt method: persistence can widen availability but never execution
    power.
    """

    def remember(self, plan: PlanArtifact) -> str: ...

    def exact(self, key: str) -> PlanArtifact | None: ...

    def retrieve_candidates(
        self, context: PlanningContext
    ) -> tuple[PlanArtifact, ...]: ...


class AdmissionCode(StrEnum):
    ADMITTED = "ADMITTED"
    GOAL_MISMATCH = "GOAL_MISMATCH"
    REQUIRED_FACT_MISSING = "REQUIRED_FACT_MISSING"
    FORBIDDEN_FACT_PRESENT = "FORBIDDEN_FACT_PRESENT"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    CONSTRAINT_MISMATCH = "CONSTRAINT_MISMATCH"
    SEMANTIC_REVISION_MISMATCH = "SEMANTIC_REVISION_MISMATCH"


@dataclass(frozen=True, slots=True)
class PlanAdmission:
    admitted: bool
    codes: tuple[AdmissionCode, ...]


def admit_plan(plan: PlanArtifact, context: PlanningContext) -> PlanAdmission:
    """Check symbolic applicability. This does not authorize execution."""
    a = plan.applicability
    codes: list[AdmissionCode] = []
    if a.goal != context.goal:
        codes.append(AdmissionCode.GOAL_MISMATCH)
    if not a.required_facts.issubset(context.facts):
        codes.append(AdmissionCode.REQUIRED_FACT_MISSING)
    if a.forbidden_facts.intersection(context.facts):
        codes.append(AdmissionCode.FORBIDDEN_FACT_PRESENT)
    if not a.required_capabilities.issubset(context.capabilities):
        codes.append(AdmissionCode.CAPABILITY_MISSING)
    if a.constraint_digest and a.constraint_digest != context.constraint_digest:
        codes.append(AdmissionCode.CONSTRAINT_MISMATCH)
    if a.semantic_revision and a.semantic_revision != context.semantic_revision:
        codes.append(AdmissionCode.SEMANTIC_REVISION_MISMATCH)
    return PlanAdmission(
        not codes, tuple(codes) if codes else (AdmissionCode.ADMITTED,)
    )


@dataclass(frozen=True, slots=True)
class ObservationDelta:
    """Typed keys whose admitted planning view changed between observations."""

    changed_keys: frozenset[str] = frozenset()

    @classmethod
    def between(
        cls, before: PlanningContext, after: PlanningContext
    ) -> "ObservationDelta":
        changed: set[str] = set()
        changed.update(f"fact:{item}" for item in before.facts ^ after.facts)
        changed.update(
            f"capability:{item}" for item in before.capabilities ^ after.capabilities
        )
        if before.goal != after.goal:
            changed.add("goal")
        if before.constraint_digest != after.constraint_digest:
            changed.add("constraint")
        if before.semantic_revision != after.semantic_revision:
            changed.add("semantic_revision")
        return cls(frozenset(changed))


def affected_paths(plan: PlanArtifact, delta: ObservationDelta) -> frozenset[NodePath]:
    """Return only the transitive downstream closure touched by ``delta``."""
    seeds = {
        path
        for path, dependencies in plan.dependency_keys.items()
        if dependencies.intersection(delta.changed_keys)
    }
    affected = set(seeds)
    queue = deque(seeds)
    while queue:
        path = queue.popleft()
        for dependent in plan.downstream.get(path, frozenset()):
            if dependent not in affected:
                affected.add(dependent)
                queue.append(dependent)
    return frozenset(affected)


@dataclass(slots=True)
class PlanCache:
    """In-memory candidate index; cache presence is never admission."""

    _by_exact: dict[str, PlanArtifact] = field(default_factory=dict)
    _by_signature: dict[str, dict[str, PlanArtifact]] = field(default_factory=dict)

    def remember(self, plan: PlanArtifact) -> str:
        key = plan.exact_key
        self._by_exact[key] = plan
        bucket = self._by_signature.setdefault(
            plan.applicability.retrieval_signature, {}
        )
        bucket[key] = plan
        return key

    def exact(self, key: str) -> PlanArtifact | None:
        return self._by_exact.get(key)

    def retrieve_candidates(self, context: PlanningContext) -> tuple[PlanArtifact, ...]:
        signature = sha256(
            {
                "goal": context.goal,
                "constraint_digest": context.constraint_digest,
                "semantic_revision": context.semantic_revision,
            }
        )
        bucket = self._by_signature.get(signature, {})
        return tuple(bucket[key] for key in sorted(bucket))


class PlanDisposition(StrEnum):
    CONTINUE = "CONTINUE"
    EXACT_REUSE = "EXACT_REUSE"
    CACHED_REUSE = "CACHED_REUSE"
    REPAIR = "REPAIR"
    FRESH_PLAN = "FRESH_PLAN"


@dataclass(frozen=True, slots=True)
class ContinuousPlanDecision:
    disposition: PlanDisposition
    mode: ReplanningMode
    plan: PlanArtifact | None
    admission: PlanAdmission | None
    affected: frozenset[NodePath] = frozenset()


@dataclass(slots=True)
class ContinuousPlanner:
    """Route over current plans, candidate memory, repair, and fresh planning."""

    cache: PlanRepository = field(default_factory=PlanCache)

    def decide(
        self,
        context: PlanningContext,
        *,
        active_plan: PlanArtifact | None = None,
        previous_context: PlanningContext | None = None,
        exact_key: str | None = None,
    ) -> ContinuousPlanDecision:
        if active_plan is not None:
            admission = admit_plan(active_plan, context)
            delta = (
                ObservationDelta.between(previous_context, context)
                if previous_context is not None
                else ObservationDelta()
            )
            affected = affected_paths(active_plan, delta)
            if admission.admitted and not affected:
                return ContinuousPlanDecision(
                    PlanDisposition.CONTINUE,
                    ReplanningMode.CONTINUE,
                    active_plan,
                    admission,
                )
            if affected:
                return ContinuousPlanDecision(
                    PlanDisposition.REPAIR,
                    ReplanningMode.REPAIR,
                    active_plan,
                    admission,
                    affected,
                )

        if exact_key is not None:
            exact = self.cache.exact(exact_key)
            if exact is not None:
                admission = admit_plan(exact, context)
                if admission.admitted:
                    return ContinuousPlanDecision(
                        PlanDisposition.EXACT_REUSE,
                        ReplanningMode.CONTINUE,
                        exact,
                        admission,
                    )

        for candidate in self.cache.retrieve_candidates(context):
            admission = admit_plan(candidate, context)
            if admission.admitted:
                return ContinuousPlanDecision(
                    PlanDisposition.CACHED_REUSE,
                    ReplanningMode.CONTINUE,
                    candidate,
                    admission,
                )

        return ContinuousPlanDecision(
            PlanDisposition.FRESH_PLAN,
            ReplanningMode.REPLAN,
            None,
            None,
        )


@dataclass(frozen=True, slots=True)
class AnchorVerdict:
    """Historical retention observation for one anchor case."""

    anchor_id: str
    current_passed: bool
    candidate_passed: bool


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    """Guardrail for promoting a new cached-plan family/version."""

    max_retention_regressions: int = 0
    require_current_improvement: bool = True


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    promoted: bool
    regressions: tuple[str, ...]
    reason: str


def evaluate_promotion(
    *,
    current_score: float,
    candidate_score: float,
    validity_passed: bool,
    anchors: tuple[AnchorVerdict, ...],
    policy: PromotionPolicy = PromotionPolicy(),
) -> PromotionDecision:
    """HCL-style promote only if validity and historical retention stay within policy."""
    regressions = tuple(
        item.anchor_id
        for item in anchors
        if item.current_passed and not item.candidate_passed
    )
    if not validity_passed:
        return PromotionDecision(False, regressions, "VALIDITY_FAILED")
    if policy.require_current_improvement and candidate_score <= current_score:
        return PromotionDecision(False, regressions, "CURRENT_SCORE_NOT_IMPROVED")
    if len(regressions) > policy.max_retention_regressions:
        return PromotionDecision(False, regressions, "RETENTION_BUDGET_EXCEEDED")
    return PromotionDecision(True, regressions, "PROMOTED")
