from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from autofde_lab.planner_league import (
    NOVELTY_ORACLES,
    PLANNER_CAPABILITY_FIELDS,
    PRIMARY_PLANNERS,
    CompatibilityResult,
    CompatibilityStanding,
    LeagueMatch,
    PayoffHypergraph,
    PayoffObservation,
    PlannerLeague,
    PolicySpec,
)


def admitted(planner_id: str, role_id: str) -> CompatibilityResult:
    return CompatibilityResult(
        planner_id=planner_id,
        role_id=role_id,
        standing=CompatibilityStanding.COMPATIBLE,
        reason="COMPATIBLE:TESTED_DOMAIN_CONTRACT",
    )


def test_live_population_projection_separates_dspy_novelty_boundary() -> None:
    assert len(PRIMARY_PLANNERS) == 56
    assert len(set(PRIMARY_PLANNERS)) == 56
    assert NOVELTY_ORACLES == ("DSPyPolicy",)
    assert "DSPyPolicy" not in PRIMARY_PLANNERS
    assert "Astar" in PRIMARY_PLANNERS
    assert "MCTS" in PRIMARY_PLANNERS
    assert "POMCP" in PRIMARY_PLANNERS


def test_planner_capability_schema_never_contains_authority() -> None:
    assert "authority" not in PLANNER_CAPABILITY_FIELDS
    assert "planner_id" in PLANNER_CAPABILITY_FIELDS
    assert "refusal_conditions" in PLANNER_CAPABILITY_FIELDS


def test_role_owns_game_semantics_not_planner() -> None:
    blue = PolicySpec.for_role("Astar", "blue_defender")
    red = PolicySpec.for_role("Astar", "red_disturbance")
    assert blue.planner_id == red.planner_id == "Astar"
    assert blue.objective_id != red.objective_id
    assert blue.action_projection_id == "candidate_plan"
    assert red.action_projection_id == "disturbance_intent"


def test_covering_cross_play_uses_only_compatible_edges() -> None:
    left = (
        admitted("Astar", "blue_defender"),
        CompatibilityResult(
            "DSPyPolicy",
            "blue_defender",
            CompatibilityStanding.REFUSED,
            "REFUSED:LLM_NOVELTY_BOUNDARY",
        ),
        admitted("MCTS", "blue_defender"),
    )
    right = (
        admitted("POMCP", "red_disturbance"),
        admitted("UCT", "red_disturbance"),
    )
    matches = PlannerLeague.cover_cross_play(
        left,
        right,
        world_id="cyber_incident",
        left_role_id="blue_defender",
        right_role_id="red_disturbance",
        rounds=2,
    )
    assert len(matches) == 4
    assert all(m.left_policy.planner_id != "DSPyPolicy" for m in matches)
    assert {m.right_policy.planner_id for m in matches} == {"POMCP", "UCT"}


def test_candidate_identity_is_stable_but_not_called_receipt() -> None:
    match = LeagueMatch(
        world_id="identity_degradation",
        left_role_id="blue_defender",
        left_policy=PolicySpec.for_role("Astar", "blue_defender"),
        right_role_id="red_disturbance",
        right_policy=PolicySpec.for_role("MCTS", "red_disturbance"),
    )
    assert match.identity_sha256 == match.identity_sha256
    payload = match.as_gymact_candidate()
    assert payload["experiment_identity_sha256"] == match.identity_sha256
    assert "receipt" not in payload
    assert payload["players"][0]["planner_id"] == "Astar"


def test_payoff_hypergraph_rejects_unreceipted_execution() -> None:
    match = LeagueMatch(
        world_id="generic_enterprise",
        left_role_id="plan_constructor",
        left_policy=PolicySpec.for_role("Astar", "plan_constructor"),
        right_role_id="plan_falsifier",
        right_policy=PolicySpec.for_role("MCTS", "plan_falsifier"),
    )
    with pytest.raises(ValueError, match="REFUSED:UNRECEIPTED_PAYOFF"):
        PayoffObservation(match, 1.0, -1.0, receipt_id="")
    with pytest.raises(ValueError, match="REFUSED:UNRECEIPTED_PAYOFF"):
        PayoffObservation(match, 1.0, -1.0, receipt_id="r-1", execution_observed=False)


def test_payoff_hypergraph_refuses_a_non_payoff_observation() -> None:
    # Found by the V2030.1.1 cap 1 adversarial refute pass (#114):
    # `PayoffHypergraph.add()` accepted a `LeagueSolveOutcome` (candidate-
    # plan evidence, deliberately never a receipted `PayoffObservation`)
    # silently, and only failed later, in `_scores()`, with an unrelated
    # `AttributeError` -- a second, unguarded door into the hypergraph.
    # `PayoffObservation.__post_init__` gates receipting; this pins that
    # `add()` itself gates *type*, so only that one door is ever open.
    graph = PayoffHypergraph()

    @dataclasses.dataclass(frozen=True, slots=True)
    class NotAPayoffObservation:
        match: object = None

    with pytest.raises(
        TypeError, match="REFUSED:PAYOFF_HYPERGRAPH_REQUIRES_PAYOFF_OBSERVATION"
    ):
        graph.add(NotAPayoffObservation())  # type: ignore[arg-type]
    assert graph.observations == []


def test_empirical_best_response_requires_complete_mixture_evidence() -> None:
    graph = PayoffHypergraph()
    for planner_id, score_vs_mcts, score_vs_uct in (
        ("Astar", 0.8, 0.7),
        ("POMCP", 0.6, 0.9),
    ):
        for opponent_id, score in (("MCTS", score_vs_mcts), ("UCT", score_vs_uct)):
            match = LeagueMatch(
                world_id="cyber_incident",
                left_role_id="blue_defender",
                left_policy=PolicySpec.for_role(planner_id, "blue_defender"),
                right_role_id="red_disturbance",
                right_policy=PolicySpec.for_role(opponent_id, "red_disturbance"),
            )
            graph.add(
                PayoffObservation(
                    match,
                    score,
                    -score,
                    receipt_id=f"receipt-{planner_id}-{opponent_id}",
                )
            )

    assert (
        graph.empirical_best_response(
            candidates=("Astar", "POMCP"),
            opponent_mixture={"MCTS": 0.5, "UCT": 0.5},
            role_id="blue_defender",
            opponent_role_id="red_disturbance",
            world_id="cyber_incident",
        )
        == "POMCP"
    )

    assert (
        graph.empirical_best_response(
            candidates=("Astar",),
            opponent_mixture={"MCTS": 0.5, "DESPOT": 0.5},
            role_id="blue_defender",
            opponent_role_id="red_disturbance",
            world_id="cyber_incident",
        )
        is None
    )


def test_novelty_frontier_requires_refusal_not_unknown_edges() -> None:
    refused = (
        CompatibilityResult(
            "Astar", "blue_defender", CompatibilityStanding.REFUSED, "REFUSED:X"
        ),
        CompatibilityResult(
            "MCTS", "blue_defender", CompatibilityStanding.REFUSED, "REFUSED:Y"
        ),
    )
    request = PlannerLeague.novelty_frontier(refused)
    assert request is not None
    assert request.allowed_oracles == ("DSPyPolicy",)

    unsupported = refused + (
        CompatibilityResult(
            "POMCP",
            "blue_defender",
            CompatibilityStanding.UNSUPPORTED,
            "UNSUPPORTED:LOAD",
        ),
    )
    assert PlannerLeague.novelty_frontier(unsupported) is None


def test_gymact_projection_keeps_authority_out_of_planner() -> None:
    path = Path(__file__).parents[2] / "gymact" / "generated" / "planner-league.json"
    payload = json.loads(path.read_text())
    assert payload["execution_semantics"] == {
        "candidate_only": True,
        "planner_has_authority": False,
        "payoff_requires_execution_receipt": True,
    }
    planner_ids = {row["id"] for row in payload["catalog"] if row["kind"] == "planner"}
    assert set(PRIMARY_PLANNERS) | set(NOVELTY_ORACLES) == planner_ids
