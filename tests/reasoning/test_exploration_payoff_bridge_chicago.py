# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `exploration_payoff_bridge` -- the real join
between `laboratory.py`'s exploration-candidate generators (TRIZ, DOE, Monte
Carlo) and the real role-conditioned planner league's `PayoffHypergraph`.

Real collaborators throughout: a real `Maze` domain (`autofde_lab.hub.domain.
maze`), a real `PlannerLeague` calling the real, installed `Astar`/`MCTS`/
`CIDual` solver entry points' real `check_domain()`, real
`generate_triz_candidates`/`generate_doe_candidates`/
`generate_montecarlo_candidates` output, real `ExperimentReceipt` +
`falsify_candidate` evidence, and a real `PayoffHypergraph`/
`PayoffObservation`. No `unittest.mock` / `Mock` / `MagicMock` / `patch` /
`monkeypatch` anywhere in this file.

`Astar` and `MCTS` are confirmed live (this session, real
`PlannerLeague().compatibility(Maze(), planner_id, role_id)` calls) to be
`COMPATIBLE` with a real `Maze()` domain; `CIDual` is confirmed live to be
`REFUSED:DOMAIN_CONTRACT_MISMATCH` against the same real domain -- used
below for the real incompatible-planner refusal path.
"""

from __future__ import annotations

from autofde_lab.hub.domain.maze import Maze
from autofde_lab.planner_league import PayoffHypergraph, PayoffObservation, PlannerLeague
from autofde_lab.reasoning.exploration_payoff_bridge import (
    admit_exploration_candidate_payoff,
    falsification_to_payoff_scores,
)
from autofde_lab.reasoning.laboratory import (
    ArchitectureCandidate,
    DesiredStateHypothesis,
    ExperimentReceipt,
    FalsificationResult,
    FalsificationStanding,
    MonteCarloCostModel,
    MonteCarloDistribution,
    TRIZContradiction,
    TRIZParameter,
    falsify_candidate,
    generate_doe_candidates,
    generate_montecarlo_candidates,
    generate_triz_candidates,
)


def _hypothesis() -> DesiredStateHypothesis:
    return DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
    )


def test_falsification_to_payoff_scores_maps_the_three_real_scoreable_standings() -> None:
    assert falsification_to_payoff_scores(FalsificationStanding.SURVIVES) == (1.0, 0.0)
    assert falsification_to_payoff_scores(FalsificationStanding.FALSIFIED) == (0.0, 1.0)
    assert falsification_to_payoff_scores(FalsificationStanding.PARTIAL) == (0.5, 0.5)


def test_falsification_to_payoff_scores_refuses_every_unscoreable_standing() -> None:
    assert falsification_to_payoff_scores(FalsificationStanding.UNKNOWN) is None
    assert falsification_to_payoff_scores(FalsificationStanding.UNSUPPORTED) is None
    assert falsification_to_payoff_scores(FalsificationStanding.REFUSED) is None


def test_admits_real_triz_candidate_with_real_surviving_falsification() -> None:
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidates = generate_triz_candidates((_hypothesis(),), contradiction)
    candidate = candidates[0]
    assert candidate.provenance == "triz-v1"

    receipt = ExperimentReceipt(
        intent_id="intent-triz-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_observed=("latency_reduced",),
    )
    falsification = falsify_candidate(candidate, receipts=(receipt,))
    assert falsification.standing == FalsificationStanding.SURVIVES

    domain = Maze()
    league = PlannerLeague()
    hypergraph = PayoffHypergraph()

    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=league,
        domain=domain,
        hypergraph=hypergraph,
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "ALIVE"
    assert outcome.admitted
    assert isinstance(outcome.observation, PayoffObservation)
    assert outcome.observation.left_score == 1.0
    assert outcome.observation.right_score == 0.0
    assert outcome.observation.match.left_policy.planner_id == "Astar"
    assert outcome.observation.match.right_policy.planner_id == "MCTS"
    assert outcome.observation.match.left_role_id == "plan_constructor"
    assert outcome.observation.match.right_role_id == "plan_falsifier"
    assert outcome.observation.receipt_id  # real, non-empty digest
    assert hypergraph.observations == [outcome.observation]


def test_admits_real_doe_candidate_with_real_falsified_falsification() -> None:
    candidates = generate_doe_candidates(
        (_hypothesis(),),
        cost_levels=(10.0, 100.0),
        authority_levels=(("read_only",), ("read_write", "delete")),
    )
    candidate = candidates[0]
    assert candidate.provenance == "doe-v1"

    receipt = ExperimentReceipt(
        intent_id="intent-doe-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_violated=("cost_ceiling_exceeded",),
    )
    falsification = falsify_candidate(candidate, receipts=(receipt,))
    assert falsification.standing == FalsificationStanding.FALSIFIED

    domain = Maze()
    league = PlannerLeague()
    hypergraph = PayoffHypergraph()

    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=league,
        domain=domain,
        hypergraph=hypergraph,
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "ALIVE"
    assert outcome.observation.left_score == 0.0
    assert outcome.observation.right_score == 1.0
    assert len(hypergraph.observations) == 1


def test_admits_real_montecarlo_candidate_with_real_partial_falsification() -> None:
    cost_model = MonteCarloCostModel(
        distribution=MonteCarloDistribution.UNIFORM, low=10.0, high=50.0
    )
    candidates = generate_montecarlo_candidates((_hypothesis(),), cost_model, n=2)
    candidate = candidates[0]
    assert candidate.provenance == "montecarlo-v1"

    # Two real receipts, neither reporting a violation, but only one
    # confirming its expected postconditions -- falsify_candidate's own
    # real PARTIAL branch (`not all_confirmed`).
    receipts = (
        ExperimentReceipt(
            intent_id="intent-mc-1",
            observed_outcome_refs=("outcome-1",),
            standing="ALIVE",
            postconditions_observed=("cost_within_bound",),
        ),
        ExperimentReceipt(
            intent_id="intent-mc-2",
            observed_outcome_refs=("outcome-2",),
            standing="ALIVE",
        ),
    )
    falsification = falsify_candidate(candidate, receipts=receipts)
    assert falsification.standing == FalsificationStanding.PARTIAL

    domain = Maze()
    league = PlannerLeague()
    hypergraph = PayoffHypergraph()

    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=league,
        domain=domain,
        hypergraph=hypergraph,
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "ALIVE"
    assert outcome.observation.left_score == 0.5
    assert outcome.observation.right_score == 0.5


def test_refuses_on_real_candidate_identity_mismatch_never_admits() -> None:
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]
    mismatched_falsification = FalsificationResult(
        candidate_id="a-different-candidate-id",
        standing=FalsificationStanding.SURVIVES,
        receipt_refs=("intent-1",),
    )

    hypergraph = PayoffHypergraph()
    outcome = admit_exploration_candidate_payoff(
        candidate,
        mismatched_falsification,
        league=PlannerLeague(),
        domain=Maze(),
        hypergraph=hypergraph,
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "REFUSED"
    assert "FALSIFICATION_CANDIDATE_MISMATCH" in outcome.reason
    assert not outcome.admitted
    assert hypergraph.observations == []


def test_refuses_on_real_unknown_falsification_standing_never_admits() -> None:
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]
    # Real falsify_candidate contract: zero receipts -> real UNKNOWN, never
    # SURVIVES by default.
    falsification = falsify_candidate(candidate, receipts=())
    assert falsification.standing == FalsificationStanding.UNKNOWN

    hypergraph = PayoffHypergraph()
    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=PlannerLeague(),
        domain=Maze(),
        hypergraph=hypergraph,
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "UNKNOWN"
    assert "NO_SCOREABLE_EVIDENCE" in outcome.reason
    assert not outcome.admitted
    assert hypergraph.observations == []


def test_refuses_on_real_incompatible_planner_never_admits() -> None:
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]
    receipt = ExperimentReceipt(
        intent_id="intent-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_observed=("latency_reduced",),
    )
    falsification = falsify_candidate(candidate, receipts=(receipt,))
    assert falsification.standing == FalsificationStanding.SURVIVES

    domain = Maze()
    league = PlannerLeague()
    # Real, live-confirmed this session: CIDual.check_domain(Maze()) is
    # False -> REFUSED:DOMAIN_CONTRACT_MISMATCH, never UNSUPPORTED (it does
    # load) and never silently treated as compatible.
    real_refusal = league.compatibility(domain, "CIDual", "plan_constructor")
    assert real_refusal.standing.value == "REFUSED"

    hypergraph = PayoffHypergraph()
    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=league,
        domain=domain,
        hypergraph=hypergraph,
        world_id="generic_enterprise",
        constructor_planner_id="CIDual",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "REFUSED"
    assert "DOMAIN_CONTRACT_MISMATCH" in outcome.reason
    assert not outcome.admitted
    assert hypergraph.observations == []


def test_refuses_on_missing_receipt_refs_before_ever_constructing_a_payoff() -> None:
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]
    # A real, hand-constructed FalsificationResult claiming SURVIVES with no
    # real receipt_refs -- falsify_candidate's own real contract can never
    # produce this (SURVIVES/FALSIFIED/PARTIAL all derive receipt_refs from
    # a nonempty usable_receipts list), so this exercises the bridge's own
    # defensive real check against a hand-built evidence object.
    falsification = FalsificationResult(
        candidate_id=candidate.candidate_id,
        standing=FalsificationStanding.SURVIVES,
        receipt_refs=(),
    )

    hypergraph = PayoffHypergraph()
    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=PlannerLeague(),
        domain=Maze(),
        hypergraph=hypergraph,
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "REFUSED"
    assert "NO_RECEIPT_REFS" in outcome.reason
    assert not outcome.admitted
    assert hypergraph.observations == []


def test_payoffobservation_fail_closed_guard_the_bridge_delegates_to_is_real() -> None:
    """Confirms, directly against the real shared collaborator, that the
    exact `PayoffObservation.__post_init__` fail-closed check
    `admit_exploration_candidate_payoff` relies on (and never bypasses) is
    real and still refuses an empty `receipt_id` -- mirrors
    `tests/planner_league/test_planner_league.py::
    test_payoff_hypergraph_rejects_unreceipted_execution`."""
    import pytest

    from autofde_lab.planner_league import LeagueMatch, PolicySpec

    match = LeagueMatch(
        world_id="generic_enterprise",
        left_role_id="plan_constructor",
        left_policy=PolicySpec.for_role("Astar", "plan_constructor"),
        right_role_id="plan_falsifier",
        right_policy=PolicySpec.for_role("MCTS", "plan_falsifier"),
    )
    with pytest.raises(ValueError, match="REFUSED:UNRECEIPTED_PAYOFF"):
        PayoffObservation(match, 1.0, 0.0, receipt_id="")
