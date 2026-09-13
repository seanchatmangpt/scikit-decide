"""DfCM Pareto comparison over lawful FORTUNE5_SPACE cloud/security scenarios.

Mirrors the feasibility / dominance / Pareto-frontier / digest SHAPE of
``simulation/fortune5_safe/dfcm.py`` (``_is_feasible``, ``_dominates``,
``_pareto_frontier``), applied to the enumeration-only cloud/identity/policy/
availability/fault ``StateSpace`` in ``fortune5/space.py`` + ``catalog.py``.

This module is SELECT/CONSTRUCT only (see ``fortune5/space.py``'s own module
docstring): it produces a comparison over candidate scenario identities and
never an admission, receipt, or actuation. There is deliberately no
``winner``/``selected``/``best`` field anywhere in ``ComparisonResult`` — the
PRD falsifier for this capability is that "candidate rankings expose
objective tradeoffs instead of hiding them in one opaque aggregate."

Marketplace architecture axis and gym-backed evaluation are explicitly out
of scope for this step (see the cap-7 evidence record).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .space import Scenario, StateSpace

# --- deterministic typed scoring tables, keyed on the REAL catalog Option
# names (verified against fortune5/catalog.py:CATALOG_ROWS). Every table is
# total over its axis's real option set -- no silent fallback default that
# would let an unrecognized name masquerade as a scored one.

_CLOUD_COST: Mapping[str, float] = {
    "aws": 0.60,
    "azure": 0.65,
    "gcp": 0.55,
}

_AVAILABILITY_COST: Mapping[str, float] = {
    "standard": 0.30,
    "ha": 0.60,
    "mission-critical": 0.90,
}

_POLICY_COMPLIANCE_RISK: Mapping[str, float] = {
    "baseline": 0.70,
    "restricted": 0.40,
    "zero-trust": 0.15,
}

_DATA_CLASS_COMPLIANCE_RISK: Mapping[str, float] = {
    "public": 0.00,
    "internal": 0.10,
    "confidential": 0.30,
    "restricted": 0.50,
}

_FAULT_BLAST_RADIUS: Mapping[str, float] = {
    "healthy": 0.05,
    "config-drift": 0.15,
    "target-port": 0.20,
    "dns": 0.35,
    "rbac": 0.40,
    "secret": 0.45,
    "network-policy": 0.45,
    "quota": 0.30,
    "oom": 0.50,
    "cpu-throttle": 0.35,
    "pvc": 0.40,
    "image-pull": 0.20,
    "crash-loop": 0.55,
    "cert": 0.40,
    "ingress": 0.45,
    "dependency": 0.50,
    "schema": 0.55,
    "backpressure": 0.40,
    "node-pressure": 0.60,
    "zone-loss": 0.95,
}

_RELEASE_REVERSIBILITY: Mapping[str, float] = {
    "rolling": 0.50,
    "canary": 0.70,
    "blue-green": 0.85,
    "immutable": 0.95,
}

_CLUSTER_PROFILE_BLAST_RADIUS_ADD: Mapping[str, float] = {
    "shared": 0.20,
    "dedicated": 0.05,
    "regulated": 0.05,
    "edge": 0.10,
}

# Cost is coupled to policy/release/cluster_profile so lowering risk on those
# axes genuinely costs more -- without this coupling every axis optimizes
# independently and the "frontier" collapses to one dominant point, which
# would itself violate the PRD falsifier this capability exists to satisfy
# (a comparison that cannot actually disagree with itself proves nothing).
_POLICY_COST_ADD: Mapping[str, float] = {
    "baseline": 0.00,
    "restricted": 0.15,
    "zero-trust": 0.35,
}

_RELEASE_COST_ADD: Mapping[str, float] = {
    "rolling": 0.00,
    "canary": 0.10,
    "blue-green": 0.20,
    "immutable": 0.35,
}

_CLUSTER_PROFILE_COST_ADD: Mapping[str, float] = {
    "shared": 0.00,
    "dedicated": 0.25,
    "regulated": 0.30,
    "edge": 0.15,
}

# Hard-constraint eliminators. These ELIMINATE candidates from the feasible
# set (absence-is-not-evidence applied to feasibility: a scenario that fails
# one of these is KNOWN_INAPPLICABLE, never rescored down). Never used to
# adjust a score.
_REQUIRED_AXES = (
    "cloud",
    "policy",
    "availability",
    "fault",
    "data_class",
    "release",
    "cluster_profile",
)


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _names(scenario: Scenario) -> dict[str, str]:
    values = scenario.names()
    missing = [axis for axis in _REQUIRED_AXES if axis not in values]
    if missing:
        raise ValueError(f"REFUSED:MISSING_REQUIRED_AXES:{missing}")
    return values


def _is_feasible(names: Mapping[str, str]) -> bool:
    """Hard constraints that eliminate a scenario outright.

    Mirrors ``simulation/fortune5_safe/dfcm.py:_is_feasible`` in SHAPE
    (a conjunction of hard thresholds a candidate must clear), not in the
    literal predicates -- the axes here are cloud/identity/policy, not
    policy-vector throughput/reliability.
    """
    # A baseline (unrestricted) policy is never lawful for confidential or
    # restricted data -- this is the exact discriminator the cap-7 gap named
    # ("policy=baseline with data_class=regulated is infeasible").
    if names["policy"] == "baseline" and names["data_class"] in (
        "confidential",
        "restricted",
    ):
        return False
    # Mission-critical availability with a rolling release strategy has no
    # safe rollback path -- infeasible independent of the data-class check
    # above, so this exercises a second, distinct elimination reason.
    return not (
        names["availability"] == "mission-critical" and names["release"] == "rolling"
    )


def _score(names: Mapping[str, str]) -> tuple[float, float, float, float]:
    """Compute (cost, blast_radius, compliance_risk, reversibility)."""
    cost = (
        _CLOUD_COST[names["cloud"]]
        + 0.5 * _AVAILABILITY_COST[names["availability"]]
        + _POLICY_COST_ADD[names["policy"]]
        + _RELEASE_COST_ADD[names["release"]]
        + _CLUSTER_PROFILE_COST_ADD[names["cluster_profile"]]
    )
    blast_radius = (
        _FAULT_BLAST_RADIUS[names["fault"]]
        + _CLUSTER_PROFILE_BLAST_RADIUS_ADD[names["cluster_profile"]]
    )
    compliance_risk = min(
        1.0,
        _POLICY_COMPLIANCE_RISK[names["policy"]]
        + _DATA_CLASS_COMPLIANCE_RISK[names["data_class"]],
    )
    reversibility = _RELEASE_REVERSIBILITY[names["release"]]
    return (cost, blast_radius, compliance_risk, reversibility)


@dataclass(frozen=True, slots=True)
class ScenarioAggregate:
    """One scored, elimination-checked candidate. Not a ranking entry."""

    scenario_id: str
    scenario_digest: str
    feasible: bool
    cost: float
    blast_radius: float
    compliance_risk: float
    reversibility: float


def _dominates(left: ScenarioAggregate, right: ScenarioAggregate) -> bool:
    """Pareto dominance: mirrors dfcm.py:_dominates's sign-flip pattern.

    Lower is better for cost/blast_radius/compliance_risk; higher is better
    for reversibility.
    """
    left_values = (
        -left.cost,
        -left.blast_radius,
        -left.compliance_risk,
        left.reversibility,
    )
    right_values = (
        -right.cost,
        -right.blast_radius,
        -right.compliance_risk,
        right.reversibility,
    )
    return all(a >= b for a, b in zip(left_values, right_values)) and any(
        a > b for a, b in zip(left_values, right_values)
    )


def _tradeoff_vector(item: ScenarioAggregate) -> tuple[float, float, float, float]:
    return (item.cost, item.blast_radius, item.compliance_risk, item.reversibility)


def _pareto_frontier(
    feasible: Sequence[ScenarioAggregate],
) -> tuple[tuple[str, int], ...]:
    """Non-dominated DISTINCT tradeoff vectors, one representative id each.

    Found by this capability's own adversarial refute pass: `FORTUNE5_SPACE`
    has 14 axes but `_score` reads 7, so scenarios differing only in the
    other 7 (enterprise/geography/environment/workload/traffic/identity/
    runtime_ai) share an identical tradeoff vector -- equal vectors never
    dominate each other by `_dominates`'s strict definition, so a
    per-scenario-id frontier silently pads itself with exact duplicates
    (measured: 144 "frontier" ids, only 12 distinct vectors). That directly
    contradicts this capability's own PRD falsifier ("expose objective
    tradeoffs instead of hiding them in one opaque aggregate") by a
    different route -- padding hides real degeneracy behind an inflated
    count instead of collapsing it into one aggregate.

    Grouping by the real tradeoff vector first, then taking Pareto
    dominance over the DISTINCT vectors, makes the frontier's size mean
    what it claims: one entry per genuinely different tradeoff. Duplicate
    count per vector is retained (see `ComparisonResult.tradeoff_group_sizes`)
    so that degeneracy is visible, not silently discarded either.
    """
    groups: dict[tuple[float, float, float, float], list[str]] = {}
    for item in feasible:
        groups.setdefault(_tradeoff_vector(item), []).append(item.scenario_id)

    representatives: dict[tuple[float, float, float, float], ScenarioAggregate] = {}
    by_id = {item.scenario_id: item for item in feasible}
    for vector, ids in groups.items():
        representatives[vector] = by_id[min(ids)]

    non_dominated = [
        vector
        for vector, candidate in representatives.items()
        if not any(
            other_vector != vector and _dominates(other, candidate)
            for other_vector, other in representatives.items()
        )
    ]
    return tuple(
        sorted(
            (representatives[vector].scenario_id, len(groups[vector]))
            for vector in non_dominated
        )
    )


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Feasibility + Pareto-frontier comparison. Deliberately has no winner.

    ``tradeoffs`` exposes the raw per-axis (cost, blast_radius,
    compliance_risk, reversibility) vector for every frontier member so a
    caller sees the real tradeoffs instead of one collapsed scalar -- this is
    the PRD's own falsifier for capability 7.

    ``pareto_scenario_ids`` names ONE representative scenario per distinct,
    non-dominated tradeoff vector (the lexicographically smallest id sharing
    that vector) -- not every scenario whose vector happens to be
    non-dominated. ``tradeoff_group_sizes`` (parallel to ``pareto_scenario_ids``)
    is how many feasible scenarios share each representative's exact
    tradeoff vector, so degeneracy across unscored axes is visible rather
    than silently inflating or silently collapsing the frontier.
    """

    space_digest: str
    scenario_count: int
    feasible_scenario_ids: tuple[str, ...]
    pareto_scenario_ids: tuple[str, ...]
    tradeoff_group_sizes: tuple[int, ...]
    tradeoffs: tuple[tuple[str, tuple[float, float, float, float]], ...]
    digest: str


def compare_lawful_scenarios(
    *, space: StateSpace, limit: int, start: int = 0
) -> ComparisonResult:
    """Compare lawful scenarios in ``space`` without selecting a winner.

    Iterates ``space.iter_lawful`` (the real mixed-radix lawful enumeration),
    applies the hard-constraint eliminator ``_is_feasible`` (constraints
    eliminate, they never rescore), computes a Pareto frontier over the
    surviving feasible set, and returns per-axis tradeoff vectors for every
    frontier member. No admission, receipt, or actuation semantics.
    """
    if limit <= 0:
        raise ValueError("REFUSED:NONPOSITIVE_COMPARISON_LIMIT")

    scenarios = tuple(space.iter_lawful(limit=limit, start=start))
    if not scenarios:
        raise ValueError("REFUSED:NO_LAWFUL_SCENARIOS_IN_RANGE")

    aggregates: list[ScenarioAggregate] = []
    for scenario in scenarios:
        names = _names(scenario)
        cost, blast_radius, compliance_risk, reversibility = _score(names)
        aggregates.append(
            ScenarioAggregate(
                scenario_id=scenario.scenario_id,
                scenario_digest=scenario.digest,
                feasible=_is_feasible(names),
                cost=cost,
                blast_radius=blast_radius,
                compliance_risk=compliance_risk,
                reversibility=reversibility,
            )
        )

    feasible = tuple(item for item in aggregates if item.feasible)
    frontier = _pareto_frontier(feasible)
    frontier_ids = tuple(scenario_id for scenario_id, _count in frontier)
    group_sizes = tuple(count for _scenario_id, count in frontier)
    by_id = {item.scenario_id: item for item in feasible}
    tradeoffs = tuple(
        (
            scenario_id,
            (
                by_id[scenario_id].cost,
                by_id[scenario_id].blast_radius,
                by_id[scenario_id].compliance_risk,
                by_id[scenario_id].reversibility,
            ),
        )
        for scenario_id in frontier_ids
    )

    digest = _canonical_digest(
        {
            "space_digest": space.digest,
            "limit": limit,
            "start": start,
            "scenario_digests": sorted(item.scenario_digest for item in aggregates),
            "feasible_scenario_ids": sorted(item.scenario_id for item in feasible),
            "pareto_scenario_ids": list(frontier_ids),
            "tradeoff_group_sizes": list(group_sizes),
        }
    )

    return ComparisonResult(
        space_digest=space.digest,
        scenario_count=len(aggregates),
        feasible_scenario_ids=tuple(sorted(item.scenario_id for item in feasible)),
        pareto_scenario_ids=frontier_ids,
        tradeoff_group_sizes=group_sizes,
        tradeoffs=tradeoffs,
        digest=digest,
    )
