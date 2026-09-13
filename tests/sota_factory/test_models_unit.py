from autofde_lab.sota_factory import (
    ArchitecturePoint,
    BasisChoice,
    BenchmarkTarget,
    BudgetPolicy,
    DecisionBasis,
    ExperimentBasis,
    FrontierStanding,
    ScoreLaw,
    TrialOutcome,
    TrialResult,
)


def _basis(model: str = "m1") -> DecisionBasis:
    return DecisionBasis(
        model=BasisChoice(model),
        planner=BasisChoice("planner"),
        tool_policy=BasisChoice("tools"),
        repair_policy=BasisChoice("repair"),
        replanning_policy=BasisChoice("replan"),
        verification_policy=BasisChoice("oracle"),
        projection_policy=BasisChoice("gymact"),
        memory_policy=BasisChoice("memory"),
        budget=BudgetPolicy("bounded", max_steps=10),
    )


def test_decision_digest_is_content_stable() -> None:
    left = _basis()
    right = _basis()
    assert left.digest == right.digest
    assert left.digest.startswith("decision:")


def test_partial_population_cannot_claim_sota_even_if_observed_task_passes() -> None:
    basis = _basis()
    arch = ArchitecturePoint(basis, ExperimentBasis())
    target = BenchmarkTarget(
        benchmark_id="ported",
        revision="r1",
        published_sota=63.7,
        primary_metric="e2e_success_percent",
        task_ids=("one",),
        expected_task_count=34,
    )
    result = TrialResult(
        plan_id="p1",
        benchmark_id="ported",
        benchmark_revision="r1",
        task_id="one",
        architecture_digest=arch.digest,
        outcome=TrialOutcome.PASS,
    )
    score = ScoreLaw().score(target, arch.digest, [result])
    assert score.standing is FrontierStanding.INCOMPLETE_EVALUATION
    assert score.score == 100.0 / 34.0
    assert score.optimistic_score == 100.0


def test_strictly_greater_is_required_for_sota() -> None:
    target = BenchmarkTarget(
        benchmark_id="b",
        revision="r",
        published_sota=50.0,
        primary_metric="success",
        task_ids=("a", "b"),
        expected_task_count=2,
    )
    assert ScoreLaw.compare(target, 50.0) is FrontierStanding.FRONTIER_MATCHED
    assert ScoreLaw.compare(target, 50.0001) is FrontierStanding.SOTA_SURPASSED
