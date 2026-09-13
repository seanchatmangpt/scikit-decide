import pytest

from autofde_lab.sota_factory import (
    BasisChoice,
    BenchmarkTarget,
    BudgetPolicy,
    DecisionSpace,
    ExperimentCompiler,
    SelectionStrategy,
)


def _maximal_space(width: int = 10) -> DecisionSpace:
    choices = tuple(BasisChoice(f"v{i}") for i in range(width))
    one = (BasisChoice("only"),)
    return DecisionSpace(
        models=choices,
        planners=choices,
        tool_policies=choices,
        repair_policies=choices,
        replanning_policies=choices,
        verification_policies=one,
        projection_policies=one,
        memory_policies=one,
        budgets=(BudgetPolicy("only"),),
    )


def _target() -> BenchmarkTarget:
    return BenchmarkTarget(
        benchmark_id="maximalist",
        revision="r1",
        published_sota=90.0,
        primary_metric="score",
        task_ids=("t1",),
        expected_task_count=1,
        evaluator_ref="evaluator:r1",
        frontier_source_ref="frontier:r1",
    )


def test_pairwise_strategy_does_not_materialize_cartesian_space() -> None:
    space = _maximal_space()
    baseline = next(space.iter_decisions(limit=1))
    assert space.upper_bound_size == 100_000

    compiled = ExperimentCompiler().compile(
        target=_target(),
        decision_space=space,
        strategy=SelectionStrategy.PAIRWISE_COVERING,
        baseline=baseline,
        candidate_limit=2_000,
    )

    assert compiled.architecture_count < space.upper_bound_size
    assert compiled.decisions[0].digest == baseline.digest


def test_pairwise_execution_ceiling_refuses_incomplete_coverage() -> None:
    space = _maximal_space()
    baseline = next(space.iter_decisions(limit=1))
    with pytest.raises(ValueError, match="PAIRWISE_COVERAGE_INCOMPLETE"):
        ExperimentCompiler().compile(
            target=_target(),
            decision_space=space,
            strategy=SelectionStrategy.PAIRWISE_COVERING,
            baseline=baseline,
            candidate_limit=2_000,
            max_architectures=2,
        )


def test_full_factorial_still_refuses_same_oversized_space() -> None:
    space = _maximal_space()
    with pytest.raises(ValueError, match="ARCHITECTURE_SPACE_TOO_LARGE"):
        ExperimentCompiler().compile(
            target=_target(),
            decision_space=space,
            strategy=SelectionStrategy.FULL_FACTORIAL,
            candidate_limit=2_000,
        )


def test_pairwise_second_order_design_refuses_instead_of_silently_losing_coverage() -> (
    None
):
    space = _maximal_space()
    baseline = next(space.iter_decisions(limit=1))
    with pytest.raises(ValueError, match="PAIRWISE_DESIGN_TOO_LARGE"):
        space.combinatorial_pairwise_candidates(
            baseline=baseline,
            candidate_limit=10,
        )
