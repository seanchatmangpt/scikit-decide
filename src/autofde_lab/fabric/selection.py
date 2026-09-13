"""Evidence-bounded empirical planner selection for AutoFDE Lab.

This module turns repeated solver observations into an index. It deliberately
keeps applicability, evidence standing, and empirical preference separate:

* structural applicability says whether a solver may be considered;
* receipts say what actually happened when it ran;
* Pareto selection says which measured alternatives remain non-dominated;
* HOT/WARM/COLD says how much exploration the next decision requires.

A candidate is never authority and no object in this module actuates anything.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class DecisionRegime(str, Enum):
    """How much experimental search a selection requires."""

    COLD = "COLD"
    WARM = "WARM"
    HOT = "HOT"


class EvidenceStanding(str, Enum):
    """Positive evidence ladder used by the selector.

    BLOCKED/REFUSED/UNSUPPORTED/UNCERTAIN are outcomes, not points on this
    positive ladder, and therefore are not represented as higher/lower crown.
    """

    UNKNOWN = "UNKNOWN"
    CANDIDATE = "CANDIDATE"
    STRUCTURAL = "STRUCTURAL"
    PARTIAL_ALIVE = "PARTIAL_ALIVE"
    ALIVE = "ALIVE"
    ADOPTED = "ADOPTED"


_STANDING_RANK = {standing: i for i, standing in enumerate(EvidenceStanding)}


class Observability(str, Enum):
    UNKNOWN = "unknown"
    FULL = "full"
    PARTIAL = "partial"


class StateSpace(str, Enum):
    UNKNOWN = "unknown"
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class ProblemSignature:
    """Structural signature used as the empirical-index lookup key.

    ``None`` means the property has not been admitted, rather than False.
    Unknown information therefore cannot accidentally satisfy a requirement.
    """

    deterministic: bool | None = None
    observability: Observability = Observability.UNKNOWN
    state_space: StateSpace = StateSpace.UNKNOWN
    temporal: bool | None = None
    concurrent: bool | None = None
    multi_agent: bool | None = None
    resource_constrained: bool | None = None
    numeric: bool | None = None
    probabilistic: bool | None = None
    reversible: bool | None = None
    safety_constrained: bool | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    def canonical_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["observability"] = self.observability.value
        data["state_space"] = self.state_space.value
        data["tags"] = sorted(self.tags)
        return data

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def key(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PlannerRequirements:
    """Admitted structural requirements for a planner."""

    planner_id: str
    equals: Mapping[str, object] = field(default_factory=dict)
    required_tags: frozenset[str] = field(default_factory=frozenset)

    def unmet(self, signature: ProblemSignature) -> tuple[str, ...]:
        unmet: list[str] = []
        for name, expected in sorted(self.equals.items()):
            if not hasattr(signature, name):
                unmet.append(f"{name}=<unknown-field>")
                continue
            actual = getattr(signature, name)
            if isinstance(actual, Enum):
                actual = actual.value
            if isinstance(expected, Enum):
                expected = expected.value
            if actual is None or actual == "unknown" or actual != expected:
                unmet.append(f"{name}={expected!r}")
        missing_tags = sorted(self.required_tags - signature.tags)
        unmet.extend(f"tag:{tag}" for tag in missing_tags)
        return tuple(unmet)

    def is_applicable(self, signature: ProblemSignature) -> bool:
        return not self.unmet(signature)


@dataclass(frozen=True, slots=True)
class PlannerReceipt:
    """Observed result of one planner experiment.

    Lower is better for wall time, monetary cost, memory, interventions and
    frontier tokens. Higher is better for quality. Only ``verified``
    successful receipts with sufficient standing may influence routing.
    """

    signature_key: str
    planner_id: str
    objective: str = "default"
    environment: str = "default"
    hardware: str = "default"
    success: bool = False
    verified: bool = False
    standing: EvidenceStanding = EvidenceStanding.CANDIDATE
    wall_time_s: float = 0.0
    cost_usd: float = 0.0
    memory_bytes: int = 0
    quality: float = 0.0
    human_interventions: int = 0
    frontier_tokens: int = 0

    def __post_init__(self) -> None:
        for name in ("wall_time_s", "cost_usd"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if not math.isfinite(self.quality):
            raise ValueError("quality must be finite")
        for name in ("memory_bytes", "human_interventions", "frontier_tokens"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class PlannerAggregate:
    planner_id: str
    observations: int
    wall_time_s: float
    cost_usd: float
    memory_bytes: float
    quality: float
    human_interventions: float
    frontier_tokens: float
    standing: EvidenceStanding

    @property
    def minimization_vector(self) -> tuple[float, ...]:
        return (
            self.wall_time_s,
            self.cost_usd,
            self.memory_bytes,
            -self.quality,
            self.human_interventions,
            self.frontier_tokens,
        )


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    signature_key: str
    regime: DecisionRegime
    candidates: tuple[str, ...]
    evidence_count: int
    reason: str


class EmpiricalPlannerIndex:
    """In-memory empirical planner index with fail-closed routing semantics."""

    def __init__(self, *, min_hot_receipts: int = 3) -> None:
        if min_hot_receipts < 2:
            raise ValueError("min_hot_receipts must be >= 2")
        self._requirements: dict[str, PlannerRequirements] = {}
        self._receipts: list[PlannerReceipt] = []
        self.min_hot_receipts = min_hot_receipts

    def register(self, requirements: PlannerRequirements) -> None:
        self._requirements[requirements.planner_id] = requirements

    def record(self, receipt: PlannerReceipt) -> None:
        self._receipts.append(receipt)

    def applicable(self, signature: ProblemSignature) -> tuple[str, ...]:
        return tuple(
            planner_id
            for planner_id, req in sorted(self._requirements.items())
            if req.is_applicable(signature)
        )

    @staticmethod
    def _standing_at_least(
        standing: EvidenceStanding, minimum: EvidenceStanding
    ) -> bool:
        return _STANDING_RANK[standing] >= _STANDING_RANK[minimum]

    def _eligible_receipts(
        self,
        signature: ProblemSignature,
        *,
        objective: str,
        environment: str,
        hardware: str,
        minimum_standing: EvidenceStanding,
    ) -> list[PlannerReceipt]:
        applicable = set(self.applicable(signature))
        return [
            r
            for r in self._receipts
            if r.signature_key == signature.key
            and r.planner_id in applicable
            and r.objective == objective
            and r.environment == environment
            and r.hardware == hardware
            and r.success
            and r.verified
            and self._standing_at_least(r.standing, minimum_standing)
        ]

    @staticmethod
    def _mean(values: Sequence[float]) -> float:
        return sum(values) / len(values)

    def aggregates(
        self,
        signature: ProblemSignature,
        *,
        objective: str = "default",
        environment: str = "default",
        hardware: str = "default",
        minimum_standing: EvidenceStanding = EvidenceStanding.ALIVE,
    ) -> tuple[PlannerAggregate, ...]:
        receipts = self._eligible_receipts(
            signature,
            objective=objective,
            environment=environment,
            hardware=hardware,
            minimum_standing=minimum_standing,
        )
        grouped: dict[str, list[PlannerReceipt]] = {}
        for receipt in receipts:
            grouped.setdefault(receipt.planner_id, []).append(receipt)

        aggregates: list[PlannerAggregate] = []
        for planner_id, rows in sorted(grouped.items()):
            standing = min(rows, key=lambda r: _STANDING_RANK[r.standing]).standing
            aggregates.append(
                PlannerAggregate(
                    planner_id=planner_id,
                    observations=len(rows),
                    wall_time_s=self._mean([r.wall_time_s for r in rows]),
                    cost_usd=self._mean([r.cost_usd for r in rows]),
                    memory_bytes=self._mean([float(r.memory_bytes) for r in rows]),
                    quality=self._mean([r.quality for r in rows]),
                    human_interventions=self._mean(
                        [float(r.human_interventions) for r in rows]
                    ),
                    frontier_tokens=self._mean(
                        [float(r.frontier_tokens) for r in rows]
                    ),
                    standing=standing,
                )
            )
        return tuple(aggregates)

    @staticmethod
    def _dominates(a: PlannerAggregate, b: PlannerAggregate) -> bool:
        av = a.minimization_vector
        bv = b.minimization_vector
        return all(x <= y for x, y in zip(av, bv)) and any(
            x < y for x, y in zip(av, bv)
        )

    def pareto_candidates(
        self,
        signature: ProblemSignature,
        *,
        objective: str = "default",
        environment: str = "default",
        hardware: str = "default",
        minimum_standing: EvidenceStanding = EvidenceStanding.ALIVE,
    ) -> tuple[PlannerAggregate, ...]:
        aggregates = self.aggregates(
            signature,
            objective=objective,
            environment=environment,
            hardware=hardware,
            minimum_standing=minimum_standing,
        )
        survivors = [
            candidate
            for candidate in aggregates
            if not any(
                self._dominates(other, candidate)
                for other in aggregates
                if other.planner_id != candidate.planner_id
            )
        ]
        return tuple(sorted(survivors, key=lambda row: row.planner_id))

    def route(
        self,
        signature: ProblemSignature,
        *,
        objective: str = "default",
        environment: str = "default",
        hardware: str = "default",
    ) -> SelectionDecision:
        applicable = self.applicable(signature)
        if not applicable:
            return SelectionDecision(
                signature_key=signature.key,
                regime=DecisionRegime.COLD,
                candidates=(),
                evidence_count=0,
                reason="no structurally applicable registered planner",
            )

        aggregates = self.aggregates(
            signature,
            objective=objective,
            environment=environment,
            hardware=hardware,
        )
        observed = {row.planner_id for row in aggregates}
        pareto = self.pareto_candidates(
            signature,
            objective=objective,
            environment=environment,
            hardware=hardware,
        )
        evidence_count = sum(row.observations for row in pareto)
        if not pareto:
            return SelectionDecision(
                signature_key=signature.key,
                regime=DecisionRegime.COLD,
                candidates=applicable,
                evidence_count=0,
                reason="no verified ALIVE empirical receipt for exact signature",
            )

        all_applicable_observed = observed == set(applicable)
        if (
            len(pareto) == 1
            and pareto[0].observations >= self.min_hot_receipts
            and all_applicable_observed
        ):
            winner = pareto[0]
            return SelectionDecision(
                signature_key=signature.key,
                regime=DecisionRegime.HOT,
                candidates=(winner.planner_id,),
                evidence_count=winner.observations,
                reason=(
                    "single non-dominated planner with repeated verified ALIVE evidence"
                ),
            )

        return SelectionDecision(
            signature_key=signature.key,
            regime=DecisionRegime.WARM,
            candidates=tuple(row.planner_id for row in pareto),
            evidence_count=evidence_count,
            reason="verified evidence exists but bounded comparison remains necessary",
        )

    def export_records(self) -> tuple[dict[str, object], ...]:
        """Return deterministic JSON-ready records for a persistent index layer."""
        records = []
        for receipt in self._receipts:
            row = asdict(receipt)
            row["standing"] = receipt.standing.value
            records.append(row)
        return tuple(
            sorted(
                records,
                key=lambda row: (
                    str(row["signature_key"]),
                    str(row["objective"]),
                    str(row["environment"]),
                    str(row["hardware"]),
                    str(row["planner_id"]),
                    float(row["wall_time_s"]),
                    float(row["cost_usd"]),
                ),
            )
        )
