from autofde_lab.sota_factory import (
    BasisChoice,
    BudgetPolicy,
    CompatibilityRule,
    DecisionSpace,
)
from autofde_lab.sota_factory.space import one_factor_at_a_time, pairwise_covering


def _space() -> DecisionSpace:
    one = (BasisChoice("current"),)
    return DecisionSpace(
        models=(BasisChoice("m1"), BasisChoice("m2")),
        planners=(BasisChoice("p1"), BasisChoice("p2")),
        tool_policies=(BasisChoice("t1"), BasisChoice("t2")),
        repair_policies=one,
        replanning_policies=one,
        verification_policies=one,
        projection_policies=one,
        memory_policies=one,
        budgets=(BudgetPolicy("b1"),),
    )


def test_pairwise_covering_reduces_three_binary_dimensions() -> None:
    decisions = _space().materialize()
    assert len(decisions) == 8
    selected = pairwise_covering(decisions)
    assert 0 < len(selected) < len(decisions)


def test_one_factor_at_a_time_keeps_only_baseline_and_hamming_one() -> None:
    decisions = _space().materialize()
    baseline = decisions[0]
    selected = one_factor_at_a_time(decisions, baseline)
    assert len(selected) == 4


def test_declarative_compatibility_rule_prunes_illegal_combination() -> None:
    base = _space()
    ruled = DecisionSpace(
        models=base.models,
        planners=base.planners,
        tool_policies=base.tool_policies,
        repair_policies=base.repair_policies,
        replanning_policies=base.replanning_policies,
        verification_policies=base.verification_policies,
        projection_policies=base.projection_policies,
        memory_policies=base.memory_policies,
        budgets=base.budgets,
        rules=(
            CompatibilityRule.from_mappings(
                when={"model": "m2"},
                forbid={"planner": "p2"},
                reason="measured incompatibility",
            ),
        ),
    )
    assert len(ruled.materialize()) == 6
