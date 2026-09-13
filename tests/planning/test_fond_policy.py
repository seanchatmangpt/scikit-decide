from autofde_lab.planning.fond_policy import (
    CandidatePolicy,
    FONDProblem,
    PolicySemantics,
    check_candidate_policy,
)


def test_strong_accepts_acyclic_branching_policy() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={
            ("s0", "advance"): frozenset({"s1", "s2"}),
            ("s1", "finish"): frozenset({"goal"}),
            ("s2", "finish"): frozenset({"goal"}),
        },
    )
    policy = CandidatePolicy(actions={"s0": "advance", "s1": "finish", "s2": "finish"})

    check = check_candidate_policy(problem, policy, semantics=PolicySemantics.STRONG)

    assert check.valid
    assert check.reachable_states == frozenset({"s0", "s1", "s2", "goal"})
    assert check.claim_ceiling == "candidate_policy_only"


def test_strong_rejects_cycle_that_strong_cyclic_accepts() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={("s0", "retry"): frozenset({"s0", "goal"})},
    )
    policy = CandidatePolicy(actions={"s0": "retry"})

    strong = check_candidate_policy(problem, policy, semantics=PolicySemantics.STRONG)
    strong_cyclic = check_candidate_policy(
        problem, policy, semantics=PolicySemantics.STRONG_CYCLIC
    )

    assert not strong.valid
    assert strong.non_goal_cycle_states == frozenset({"s0"})
    assert strong_cyclic.valid
    assert strong_cyclic.non_goal_cycle_states == frozenset({"s0"})


def test_multistate_cycle_distinguishes_strong_from_strong_cyclic() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={
            ("s0", "advance"): frozenset({"s1", "goal"}),
            ("s1", "retry"): frozenset({"s0"}),
        },
    )
    policy = CandidatePolicy(actions={"s0": "advance", "s1": "retry"})

    strong = check_candidate_policy(problem, policy, semantics=PolicySemantics.STRONG)
    strong_cyclic = check_candidate_policy(
        problem, policy, semantics=PolicySemantics.STRONG_CYCLIC
    )

    assert not strong.valid
    assert strong.non_goal_cycle_states == frozenset({"s0", "s1"})
    assert strong_cyclic.valid
    assert strong_cyclic.non_goal_cycle_states == frozenset({"s0", "s1"})
    assert not strong_cyclic.cannot_reach_goal_states


def test_strong_cyclic_rejects_closed_non_goal_component() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={("s0", "spin"): frozenset({"s0"})},
    )
    policy = CandidatePolicy(actions={"s0": "spin"})

    check = check_candidate_policy(
        problem, policy, semantics=PolicySemantics.STRONG_CYCLIC
    )

    assert not check.valid
    assert check.cannot_reach_goal_states == frozenset({"s0"})


def test_missing_policy_state_is_typed_failure() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={("s0", "advance"): frozenset({"s1", "goal"})},
    )
    policy = CandidatePolicy(actions={"s0": "advance"})

    check = check_candidate_policy(
        problem, policy, semantics=PolicySemantics.STRONG_CYCLIC
    )

    assert not check.valid
    assert check.missing_policy_states == frozenset({"s1"})


def test_selected_action_without_outcomes_is_dead_end() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={},
    )
    policy = CandidatePolicy(actions={"s0": "unknown"})

    check = check_candidate_policy(problem, policy, semantics=PolicySemantics.STRONG)

    assert not check.valid
    assert check.dead_end_states == frozenset({"s0"})
