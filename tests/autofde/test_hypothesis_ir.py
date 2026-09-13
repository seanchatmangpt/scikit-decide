from __future__ import annotations

import pytest

from autofde_lab.autofde.hypothesis_ir import (
    BaselineSnapshot,
    DesiredStateEnvelope,
    DiscriminatingExperiment,
    EvidenceBinding,
    ExperimentPortfolio,
    FutureCandidate,
    Hypothesis,
    HypothesisPortfolio,
    PossibilityGraph,
    WorldDelta,
    construct_solution_graph,
)


def evidence(ref: str = "obs:1", admitted: bool = True) -> EvidenceBinding:
    return EvidenceBinding(ref, "observation", "sha256:subject", admitted)


def test_pipeline_preserves_bindings_and_builds_verifiable_solution() -> None:
    baseline = BaselineSnapshot("baseline:1", "world:before", ("process:normal",), (evidence(),))
    delta = WorldDelta("world:before", "world:after", baseline.digest, (evidence("obs:2"),))
    hypotheses = HypothesisPortfolio(
        delta.digest,
        (
            Hypothesis("h:network", "network path changed", ("obs:2",)),
            Hypothesis("h:config", "configuration changed"),
        ),
    )
    experiment = DiscriminatingExperiment(
        "exp:route-table",
        frozenset({"h:network", "h:config"}),
        "observe:route-table",
    )
    experiments = ExperimentPortfolio(hypotheses.digest, (experiment,))
    possibilities = PossibilityGraph(
        hypotheses.digest,
        (
            FutureCandidate(
                "future:repair-route",
                "h:network",
                "planner:a-star",
                "world:desired",
                1.0,
                "verify:route-health",
            ),
        ),
    )
    desired = DesiredStateEnvelope(
        "objective:restore",
        ("route-health=healthy",),
        ("preserve:data", "preserve:unrelated-resources"),
        frozenset({"network.write"}),
    )

    assert experiments.covers(h.hypothesis_id for h in hypotheses.live)
    solution = construct_solution_graph(
        possibilities,
        desired,
        future_id="future:repair-route",
        preconditions=("route-table-observed",),
        transformation_ref="manufacture:route-repair",
        recovery_ref="recover:route-repair",
        authority_requirements=("network.write",),
    )

    assert solution.possibility_graph_digest == possibilities.digest
    assert solution.verifier_ref == "verify:route-health"
    assert solution.recovery_ref == "recover:route-repair"
    assert solution.preservation_laws == desired.preservation_laws


def test_unadmitted_observation_cannot_enter_baseline_or_delta() -> None:
    with pytest.raises(ValueError, match="UNADMITTED_BASELINE_EVIDENCE_REFUSED"):
        BaselineSnapshot("baseline:1", "world:before", (), (evidence(admitted=False),))

    with pytest.raises(ValueError, match="UNADMITTED_DELTA_EVIDENCE_REFUSED"):
        WorldDelta("before", "after", "baseline:digest", (evidence(admitted=False),))


def test_empty_delta_and_non_discriminating_experiment_are_refused() -> None:
    with pytest.raises(ValueError, match="WORLD_DELTA_EMPTY_REFUSED"):
        WorldDelta("same", "same", "baseline:digest", ())

    with pytest.raises(ValueError, match="NON_DISCRIMINATING_EXPERIMENT_REFUSED"):
        DiscriminatingExperiment("exp:bad", frozenset({"h:one"}), "observe:x")


def test_candidate_experiment_cannot_claim_consequential_authority() -> None:
    with pytest.raises(ValueError, match="CONSEQUENTIAL_EXPERIMENT_REFUSED"):
        DiscriminatingExperiment(
            "exp:bad",
            frozenset({"h:one", "h:two"}),
            "mutate:x",
            authority_requirement="write",
        )


def test_duplicate_hypotheses_and_futures_are_refused() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_HYPOTHESIS_ID_REFUSED"):
        HypothesisPortfolio(
            "delta:digest",
            (Hypothesis("h:1", "a"), Hypothesis("h:1", "b")),
        )

    duplicate = FutureCandidate("f:1", "h:1", "p:1", "state:1", 1.0, "verify:1")
    with pytest.raises(ValueError, match="DUPLICATE_FUTURE_ID_REFUSED"):
        PossibilityGraph("h:digest", (duplicate, duplicate))


def test_solution_refuses_unknown_future_and_authority_escalation() -> None:
    possibilities = PossibilityGraph(
        "hypotheses:digest",
        (FutureCandidate("f:1", "h:1", "p:1", "state:1", 1.0, "verify:1"),),
    )
    desired = DesiredStateEnvelope(
        "objective:1",
        ("healthy",),
        ("preserve:data",),
        frozenset({"network.write"}),
    )

    with pytest.raises(ValueError, match="UNKNOWN_FUTURE_REFUSED"):
        construct_solution_graph(
            possibilities,
            desired,
            future_id="f:missing",
            preconditions=(),
            transformation_ref="manufacture:x",
            recovery_ref="recover:x",
            authority_requirements=(),
        )

    with pytest.raises(ValueError, match="AUTHORITY_CEILING_EXCEEDED_REFUSED"):
        construct_solution_graph(
            possibilities,
            desired,
            future_id="f:1",
            preconditions=(),
            transformation_ref="manufacture:x",
            recovery_ref="recover:x",
            authority_requirements=("subscription.delete",),
        )
