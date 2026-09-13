from autofde_lab.fabric.competitive_benchmark import (
    BenchmarkPoint,
    BenchmarkStanding,
    compare_curves,
)


def point(architecture, n, cost, *, workload="w", verifier="v", verified=None):
    return BenchmarkPoint(
        architecture=architecture,
        workload_digest=workload,
        verifier_digest=verifier,
        repetitions=n,
        verified_transitions=n if verified is None else verified,
        total_cost_usd=cost,
        wall_time_s=float(n),
        human_attention_s=1.0,
        frontier_tokens=n * 100,
    )


def curves():
    baseline = [
        point("frontier-agent", 1, 0.1),
        point("frontier-agent", 10, 1.0),
        point("frontier-agent", 100, 10.0),
        point("frontier-agent", 1000, 100.0),
    ]
    autofde = [
        point("autofde", 1, 0.5),
        point("autofde", 10, 1.5),
        point("autofde", 100, 2.0),
        point("autofde", 1000, 3.0),
    ]
    return baseline, autofde


def test_persistent_crossover_is_measured_per_verified_consequence():
    baseline, autofde = curves()
    report = compare_curves(baseline, autofde)
    assert report.standing is BenchmarkStanding.COMPARABLE
    assert report.cost_crossover_n == 100


def test_workload_identity_mismatch_is_refused():
    baseline, autofde = curves()
    autofde[0] = point("autofde", 1, 0.5, workload="different")
    assert (
        compare_curves(baseline, autofde).standing
        is BenchmarkStanding.REFUSED_WORKLOAD_MISMATCH
    )


def test_verifier_identity_mismatch_is_refused():
    baseline, autofde = curves()
    autofde[-1] = point("autofde", 1000, 3.0, verifier="different")
    assert (
        compare_curves(baseline, autofde).standing
        is BenchmarkStanding.REFUSED_VERIFIER_MISMATCH
    )


def test_repetition_mismatch_is_refused():
    baseline, autofde = curves()
    autofde.pop()
    assert (
        compare_curves(baseline, autofde).standing
        is BenchmarkStanding.REFUSED_REPETITION_MISMATCH
    )


def test_required_curve_points_cannot_be_skipped():
    baseline, autofde = curves()
    baseline = [p for p in baseline if p.repetitions != 1000]
    autofde = [p for p in autofde if p.repetitions != 1000]
    assert (
        compare_curves(baseline, autofde).standing
        is BenchmarkStanding.REFUSED_INCOMPLETE_CURVE
    )


def test_zero_verified_transitions_cannot_create_cheap_false_win():
    baseline, autofde = curves()
    autofde[2] = point("autofde", 100, 0.0, verified=0)
    report = compare_curves(baseline, autofde)
    assert report.standing is BenchmarkStanding.COMPARABLE
    assert report.cost_crossover_n == 1000
