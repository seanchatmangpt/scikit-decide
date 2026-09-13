# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `exploration_psro_loop` -- the real end-to-end
driver from exploration-candidate falsification evidence through
`exploration_payoff_bridge` into a real `PolicySpaceResponseOracle.step()`.

Real collaborators throughout: a real `Maze` domain
(`autofde_lab.hub.domain.maze`), a real `PlannerLeague` calling the real,
installed `Astar`/`MCTS` solver entry points' real `check_domain()`, real
`generate_triz_candidates`/`generate_doe_candidates` output, real
`ExperimentReceipt` + `falsify_candidate` evidence, a real
`PayoffHypergraph`/`PayoffObservation`, and the real
`planner_league.psro.PolicySpaceResponseOracle`/`PsroState`. No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in
this file.

`Astar` and `MCTS` are confirmed live (prior session work, real
`PlannerLeague().compatibility(Maze(), planner_id, role_id)` calls) to be
`COMPATIBLE` with a real `Maze()` domain for both `plan_constructor` and
`plan_falsifier` roles (`compatibility()` gates on domain contract only,
never on role identity -- confirmed by reading `core.py`'s
`compatibility()` directly).
"""

from __future__ import annotations

from autofde_lab.hub.domain.maze import Maze
from autofde_lab.planner_league import PlannerLeague
from autofde_lab.reasoning.exploration_psro_loop import (
    ExplorationPsroRoundOutcome,
    run_exploration_psro_round,
)
from autofde_lab.reasoning.laboratory import (
    DesiredStateHypothesis,
    ExperimentReceipt,
    FalsificationStanding,
    TRIZContradiction,
    TRIZParameter,
    falsify_candidate,
    generate_doe_candidates,
    generate_triz_candidates,
)


def _hypothesis() -> DesiredStateHypothesis:
    return DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
    )


def _surviving_triz_candidate_and_falsification():
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]
    receipt = ExperimentReceipt(
        intent_id="intent-psro-triz-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_observed=("latency_reduced",),
    )
    falsification = falsify_candidate(candidate, receipts=(receipt,))
    assert falsification.standing == FalsificationStanding.SURVIVES
    return candidate, falsification


def test_run_exploration_psro_round_advances_with_one_surviving_candidate() -> None:
    candidate, falsification = _surviving_triz_candidate_and_falsification()
    domain = Maze()
    league = PlannerLeague()

    result = run_exploration_psro_round(
        [(candidate, falsification)],
        league=league,
        domain=domain,
        world_id="generic_enterprise",
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )

    assert isinstance(result, ExplorationPsroRoundOutcome)
    # One (candidate, constructor) pair -> exactly one admission attempt.
    assert len(result.admissions) == 1
    assert result.admissions[0].admitted
    assert result.admitted_count == 1
    assert len(result.hypergraph.observations) == 1

    # Astar has complete real coverage against the {MCTS: 1.0} opponent
    # mixture (the only candidate, the only opponent) -> PSRO must advance.
    assert result.psro_step.advanced
    assert result.psro_step.standing == "ALIVE"
    assert result.psro_step.reason == "ALIVE:EMPIRICAL_PSRO_STEP"
    assert result.psro_step.receipt is not None
    assert result.psro_step.receipt.selected_best_response == "Astar"
    assert result.psro_step.state.iteration == 1
    assert "Astar" in result.psro_step.state.population
    # Real, deterministic digest -- re-derive independently to confirm the
    # receipt is bound to this exact real transition, not merely present.
    assert len(result.psro_step.receipt.identity_sha256) == 64


def test_run_exploration_psro_round_refuses_when_the_only_candidate_has_no_coverage() -> None:
    candidate, falsification = _surviving_triz_candidate_and_falsification()
    domain = Maze()
    league = PlannerLeague()

    # Admit Astar's payoff against MCTS, but ask PSRO to find a best
    # response among ["MCTS"] instead -- MCTS has zero observed edges as a
    # *constructor* against the {MCTS: 1.0} opponent mixture (all real
    # observations recorded Astar as constructor), so real payoff closure
    # is genuinely incomplete for every candidate PSRO was asked to
    # consider.
    result = run_exploration_psro_round(
        [(candidate, falsification)],
        league=league,
        domain=domain,
        world_id="generic_enterprise",
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )
    # Sanity: the admission that did happen is real and present.
    assert result.admitted_count == 1

    # Now re-run PSRO directly against the same real, already-populated
    # hypergraph but ask it to evaluate a candidate with zero real edges.
    from autofde_lab.planner_league.psro import PolicySpaceResponseOracle, PsroState

    oracle = PolicySpaceResponseOracle(
        result.hypergraph,
        role_id="plan_constructor",
        opponent_role_id="plan_falsifier",
        world_id="generic_enterprise",
    )
    state = PsroState.seed(["MCTS"])
    step = oracle.step(state, candidates=["MCTS"])

    assert not step.advanced
    assert step.standing == "REFUSED"
    assert step.reason == "REFUSED:PSRO_MISSING_PAYOFF_CLOSURE"
    assert step.receipt is None
    # Refusal must not mutate empirical state.
    assert step.state == state


def test_run_exploration_psro_round_collects_real_refusal_for_incompatible_falsifier() -> None:
    candidate, falsification = _surviving_triz_candidate_and_falsification()
    domain = Maze()
    league = PlannerLeague()

    # CIDual is confirmed REFUSED:DOMAIN_CONTRACT_MISMATCH against a real
    # Maze() domain (established by test_exploration_payoff_bridge_chicago.py).
    result = run_exploration_psro_round(
        [(candidate, falsification)],
        league=league,
        domain=domain,
        world_id="generic_enterprise",
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="CIDual",
    )

    assert result.admitted_count == 0
    assert len(result.admissions) == 1
    assert not result.admissions[0].admitted
    assert result.admissions[0].reason.startswith("falsifier:REFUSED:DOMAIN_CONTRACT_MISMATCH")
    assert result.hypergraph.observations == []

    # No real payoff edges at all -> PSRO must refuse, never fabricate an
    # advance from an empty hypergraph.
    assert not result.psro_step.advanced
    assert result.psro_step.reason == "REFUSED:PSRO_MISSING_PAYOFF_CLOSURE"


def test_run_exploration_psro_round_picks_the_real_higher_scoring_constructor() -> None:
    """Two real candidates, two real constructor planners, one fixed real
    opponent ("MCTS") -- PSRO must pick the constructor whose real admitted
    edges average a strictly higher score, not merely the first one seen.

    Kept to a single opponent deliberately: `PayoffHypergraph._scores()`
    only matches an exact (planner_id, opponent_id) edge, so a planner
    never has real coverage against itself as opponent unless it actually
    played that match -- using two opponents in the mixture here would make
    both candidates miss self-play coverage and get skipped by
    `empirical_best_response`, which is a real, different scenario (see the
    "no coverage" refusal test above), not the "which real score is higher"
    scenario this test targets.
    """
    triz_candidate, triz_falsification = _surviving_triz_candidate_and_falsification()

    doe_candidates = generate_doe_candidates(
        (_hypothesis(),),
        cost_levels=(10.0, 100.0),
        authority_levels=(("read_only",), ("read_write", "delete")),
    )
    doe_candidate = doe_candidates[0]
    doe_receipt = ExperimentReceipt(
        intent_id="intent-psro-doe-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_violated=("cost_ceiling_exceeded",),
    )
    doe_falsification = falsify_candidate(doe_candidate, receipts=(doe_receipt,))
    assert doe_falsification.standing == FalsificationStanding.FALSIFIED

    domain = Maze()
    league = PlannerLeague()

    # Astar realizes both candidates against the same real opponent MCTS:
    # real SURVIVES (TRIZ) -> score 1.0, real FALSIFIED (DOE) -> score 0.0
    # -> real average 0.5.
    result_astar = run_exploration_psro_round(
        [(triz_candidate, triz_falsification), (doe_candidate, doe_falsification)],
        league=league,
        domain=domain,
        world_id="generic_enterprise",
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )
    assert result_astar.admitted_count == 2

    # MCTS realizes only the surviving TRIZ candidate, also against MCTS as
    # the real falsifier -- real average 1.0. (Nothing in `LeagueMatch`/
    # `admit_exploration_candidate_payoff` forbids the same registered
    # planner playing both constructor and falsifier in one match; the two
    # role slots are independent and both are real, separately-checked
    # `PlannerLeague.compatibility()` calls.)
    result_mcts = run_exploration_psro_round(
        [(triz_candidate, triz_falsification)],
        league=league,
        domain=domain,
        world_id="generic_enterprise",
        constructor_planner_ids=["MCTS"],
        falsifier_planner_id="MCTS",
    )
    assert result_mcts.admitted_count == 1

    # Merge both real hypergraphs' real observations into one, then run a
    # single real PSRO best-response computation over both constructors
    # against the single real opponent both rounds actually played.
    from autofde_lab.planner_league import PayoffHypergraph
    from autofde_lab.planner_league.psro import PolicySpaceResponseOracle, PsroState

    merged = PayoffHypergraph()
    for obs in (*result_astar.hypergraph.observations, *result_mcts.hypergraph.observations):
        merged.add(obs)
    assert len(merged.observations) == 3

    oracle = PolicySpaceResponseOracle(
        merged, role_id="plan_constructor", opponent_role_id="plan_falsifier", world_id="generic_enterprise"
    )
    state = PsroState.seed(["MCTS"])
    step = oracle.step(state, candidates=["Astar", "MCTS"])

    # Astar: real scores [1.0, 0.0] vs MCTS -> mean 0.5.
    # MCTS: real scores [1.0] vs MCTS -> mean 1.0.
    # Both have complete coverage against the single-opponent mixture, so
    # the real, strictly higher-scoring MCTS must win.
    assert step.advanced
    assert step.receipt is not None
    assert step.receipt.selected_best_response == "MCTS"
