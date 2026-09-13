import math

import pytest

from autofde_lab.fabric.selection import (
    DecisionRegime,
    EmpiricalPlannerIndex,
    EvidenceStanding,
    Observability,
    PlannerReceipt,
    PlannerRequirements,
    ProblemSignature,
    StateSpace,
)


def sig() -> ProblemSignature:
    return ProblemSignature(
        deterministic=True,
        observability=Observability.FULL,
        state_space=StateSpace.DISCRETE,
        temporal=False,
        probabilistic=False,
        tags=frozenset({"planning"}),
    )


def receipt(
    planner: str, *, wall: float, quality: float = 1.0, verified: bool = True
) -> PlannerReceipt:
    return PlannerReceipt(
        signature_key=sig().key,
        planner_id=planner,
        success=True,
        verified=verified,
        standing=EvidenceStanding.ALIVE,
        wall_time_s=wall,
        cost_usd=0.01,
        memory_bytes=100,
        quality=quality,
        human_interventions=0,
        frontier_tokens=0,
    )


def index() -> EmpiricalPlannerIndex:
    idx = EmpiricalPlannerIndex(min_hot_receipts=3)
    idx.register(
        PlannerRequirements(
            "Astar",
            equals={
                "deterministic": True,
                "observability": "full",
                "state_space": "discrete",
            },
        )
    )
    idx.register(
        PlannerRequirements(
            "POMCP",
            equals={"observability": "partial", "probabilistic": True},
        )
    )
    return idx


def test_signature_is_stable_across_tag_order():
    a = ProblemSignature(tags=frozenset({"b", "a"}))
    b = ProblemSignature(tags=frozenset({"a", "b"}))
    assert a.key == b.key
    assert a.canonical_json() == b.canonical_json()


def test_unknown_never_satisfies_required_property():
    req = PlannerRequirements("x", equals={"deterministic": True})
    assert not req.is_applicable(ProblemSignature())
    assert req.unmet(ProblemSignature()) == ("deterministic=True",)


def test_applicability_filters_wrong_problem_class():
    idx = index()
    assert idx.applicable(sig()) == ("Astar",)


def test_no_empirical_receipt_is_cold_not_false_crown():
    decision = index().route(sig())
    assert decision.regime is DecisionRegime.COLD
    assert decision.candidates == ("Astar",)


def test_unverified_success_cannot_warm_or_heat_route():
    idx = index()
    idx.record(receipt("Astar", wall=1.0, verified=False))
    assert idx.route(sig()).regime is DecisionRegime.COLD


def test_one_verified_receipt_is_warm_not_hot():
    idx = index()
    idx.record(receipt("Astar", wall=1.0))
    decision = idx.route(sig())
    assert decision.regime is DecisionRegime.WARM
    assert decision.candidates == ("Astar",)


def test_repeated_single_pareto_candidate_becomes_hot():
    idx = index()
    for wall in (1.0, 0.9, 1.1):
        idx.record(receipt("Astar", wall=wall))
    decision = idx.route(sig())
    assert decision.regime is DecisionRegime.HOT
    assert decision.candidates == ("Astar",)
    assert decision.evidence_count == 3


def test_pareto_tie_stays_warm():
    idx = index()
    idx.register(
        PlannerRequirements(
            "BFWS",
            equals={
                "deterministic": True,
                "observability": "full",
                "state_space": "discrete",
            },
        )
    )
    for _ in range(3):
        idx.record(receipt("Astar", wall=1.0))
        idx.record(receipt("BFWS", wall=1.0))
    decision = idx.route(sig())
    assert decision.regime is DecisionRegime.WARM
    assert decision.candidates == ("Astar", "BFWS")


def test_strictly_dominated_planner_is_removed():
    idx = index()
    idx.register(
        PlannerRequirements(
            "BFWS",
            equals={
                "deterministic": True,
                "observability": "full",
                "state_space": "discrete",
            },
        )
    )
    for _ in range(3):
        idx.record(receipt("Astar", wall=1.0, quality=1.0))
        idx.record(receipt("BFWS", wall=2.0, quality=0.5))
    assert tuple(x.planner_id for x in idx.pareto_candidates(sig())) == ("Astar",)
    assert idx.route(sig()).regime is DecisionRegime.HOT


def test_export_is_deterministic():
    idx = index()
    idx.record(receipt("Astar", wall=2.0))
    idx.record(receipt("Astar", wall=1.0))
    records = idx.export_records()
    assert [r["wall_time_s"] for r in records] == [1.0, 2.0]
    assert all(r["standing"] == "ALIVE" for r in records)


def test_untested_applicable_competitor_prevents_hot_crown():
    idx = index()
    idx.register(
        PlannerRequirements(
            "BFWS",
            equals={
                "deterministic": True,
                "observability": "full",
                "state_space": "discrete",
            },
        )
    )
    for wall in (1.0, 0.9, 1.1):
        idx.record(receipt("Astar", wall=wall))
    decision = idx.route(sig())
    assert decision.regime is DecisionRegime.WARM
    assert decision.candidates == ("Astar",)
    assert "bounded comparison" in decision.reason


def test_negative_normalized_utility_is_admitted():
    row = receipt("Astar", wall=1.0, quality=-7.25)
    assert row.quality == -7.25


@pytest.mark.parametrize("quality", [math.inf, -math.inf, math.nan])
def test_non_finite_utility_is_refused(quality: float):
    with pytest.raises(ValueError, match="quality must be finite"):
        receipt("Astar", wall=1.0, quality=quality)
