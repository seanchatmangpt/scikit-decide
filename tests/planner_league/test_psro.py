from __future__ import annotations

from autofde_lab.planner_league import (
    LeagueMatch,
    PayoffHypergraph,
    PayoffObservation,
    PolicySpaceResponseOracle,
    PolicySpec,
    PsroState,
)


def payoff(
    graph: PayoffHypergraph,
    planner_id: str,
    opponent_id: str,
    score: float,
) -> None:
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


def oracle(graph: PayoffHypergraph) -> PolicySpaceResponseOracle:
    return PolicySpaceResponseOracle(
        graph,
        role_id="blue_defender",
        opponent_role_id="red_disturbance",
        world_id="cyber_incident",
    )


def test_psro_refuses_when_positive_weight_payoff_edge_is_missing() -> None:
    graph = PayoffHypergraph()
    payoff(graph, "Astar", "MCTS", 1.0)
    state = PsroState.seed(("MCTS", "UCT"))

    step = oracle(graph).step(state, candidates=("Astar",))

    assert not step.advanced
    assert step.state == state
    assert step.standing == "REFUSED"
    assert step.reason == "REFUSED:PSRO_MISSING_PAYOFF_CLOSURE"


def test_psro_adds_observed_best_response_without_do_authority() -> None:
    graph = PayoffHypergraph()
    for opponent_id, score in (("MCTS", 0.9), ("UCT", 0.8)):
        payoff(graph, "Astar", opponent_id, score)
        payoff(graph, "POMCP", opponent_id, score - 0.2)
    state = PsroState.seed(("MCTS", "UCT"))

    step = oracle(graph).step(state, candidates=("Astar", "POMCP"))

    assert step.advanced
    assert step.standing == "ALIVE"
    assert step.state.iteration == 1
    assert step.state.population == ("MCTS", "UCT", "Astar")
    assert step.receipt is not None
    assert step.receipt.selected_best_response == "Astar"
    assert step.receipt.claim_ceiling == "EMPIRICAL_META_SELECTION_ONLY"
    assert step.receipt.do_authority is False


def test_psro_empirical_frequency_updates_existing_population() -> None:
    graph = PayoffHypergraph()
    for opponent_id in ("MCTS", "UCT"):
        payoff(graph, "MCTS", opponent_id, 0.7)
        payoff(graph, "UCT", opponent_id, 0.2)
    state = PsroState.seed(("MCTS", "UCT"))

    step = oracle(graph).step(state, candidates=("MCTS", "UCT"))

    assert step.advanced
    assert step.state.population == state.population
    assert step.state.mixture == {"MCTS": 2 / 3, "UCT": 1 / 3}


def test_psro_receipt_identity_is_deterministic() -> None:
    graph = PayoffHypergraph()
    for opponent_id in ("MCTS", "UCT"):
        payoff(graph, "Astar", opponent_id, 1.0)
    state = PsroState.seed(("MCTS", "UCT"))

    left = oracle(graph).step(state, candidates=("Astar",))
    right = oracle(graph).step(state, candidates=("Astar",))

    assert left.receipt is not None
    assert right.receipt is not None
    assert left.receipt.identity_sha256 == right.receipt.identity_sha256
    assert left.state == right.state


def test_psro_candidate_order_does_not_override_empirical_payoff() -> None:
    graph = PayoffHypergraph()
    for opponent_id in ("MCTS", "UCT"):
        payoff(graph, "Astar", opponent_id, 0.8)
        payoff(graph, "POMCP", opponent_id, 0.9)
    state = PsroState.seed(("MCTS", "UCT"))

    first = oracle(graph).step(state, candidates=("Astar", "POMCP"))
    second = oracle(graph).step(state, candidates=("POMCP", "Astar"))

    assert first.receipt is not None
    assert second.receipt is not None
    assert first.receipt.selected_best_response == "POMCP"
    assert second.receipt.selected_best_response == "POMCP"
