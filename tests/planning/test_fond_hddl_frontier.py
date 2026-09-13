from autofde_lab.planning.fond_hddl import (
    FONDHDDLFrontierCheck,
    HDDLProgressWitness,
    check_fond_hddl_frontier_closure,
)
from autofde_lab.planning.fond_policy import (
    CandidatePolicy,
    FONDProblem,
    PolicySemantics,
)


def _witness(task_network_state: str, *actions: str) -> HDDLProgressWitness:
    return HDDLProgressWitness(
        task_network_state=task_network_state,
        permitted_primitive_actions=frozenset(actions),
    )


def _chain_problem() -> tuple[FONDProblem, CandidatePolicy]:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={
            ("s0", "advance"): frozenset({"s1"}),
            ("s1", "finish"): frozenset({"goal"}),
        },
    )
    policy = CandidatePolicy(actions={"s0": "advance", "s1": "finish"})
    return problem, policy


def test_frontier_accepts_only_when_all_retained_hddl_progress_allows_action() -> None:
    problem, policy = _chain_problem()
    witnesses = {
        "s0": frozenset(
            {
                _witness("route-left", "advance"),
                _witness("route-right", "advance", "inspect"),
            }
        ),
        "s1": frozenset({_witness("finish-task", "finish")}),
    }

    check = check_fond_hddl_frontier_closure(
        problem,
        policy,
        semantics=PolicySemantics.STRONG,
        hierarchy_witnesses=witnesses,
    )

    assert isinstance(check, FONDHDDLFrontierCheck)
    assert check.valid
    assert check.hierarchy_closed_action_states == frozenset({"s0", "s1"})
    assert not check.hierarchy_rejected_action_states
    assert check.claim_ceiling == "candidate_fond_hddl_frontier_only"


def test_same_world_state_with_incompatible_hddl_progress_is_rejected() -> None:
    problem, policy = _chain_problem()
    witnesses = {
        "s0": frozenset(
            {
                _witness("progress-allows", "advance"),
                _witness("progress-blocks", "inspect"),
            }
        ),
        "s1": frozenset({_witness("finish-task", "finish")}),
    }

    check = check_fond_hddl_frontier_closure(
        problem,
        policy,
        semantics=PolicySemantics.STRONG,
        hierarchy_witnesses=witnesses,
    )

    assert not check.valid
    assert check.hierarchy_rejected_action_states == frozenset({"s0"})
    assert check.rejected_progress_witnesses == frozenset({("s0", "progress-blocks")})


def test_missing_and_malformed_hierarchy_progress_are_typed_failures() -> None:
    problem, policy = _chain_problem()
    witnesses = {
        "s0": frozenset({_witness("", "advance")}),
    }

    check = check_fond_hddl_frontier_closure(
        problem,
        policy,
        semantics=PolicySemantics.STRONG,
        hierarchy_witnesses=witnesses,
    )

    assert not check.valid
    assert check.malformed_hierarchy_witness_states == frozenset({"s0"})
    assert check.missing_hierarchy_witness_states == frozenset({"s1"})


def test_hierarchy_frontier_cannot_promote_an_invalid_fond_policy() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={("s0", "retry"): frozenset({"s0", "goal"})},
    )
    policy = CandidatePolicy(actions={"s0": "retry"})
    witnesses = {
        "s0": frozenset({_witness("retry-progress", "retry")}),
    }

    check = check_fond_hddl_frontier_closure(
        problem,
        policy,
        semantics=PolicySemantics.STRONG,
        hierarchy_witnesses=witnesses,
    )

    assert not check.valid
    assert check.policy_check.non_goal_cycle_states == frozenset({"s0"})
    assert check.hierarchy_closed_action_states == frozenset({"s0"})


def test_strong_cyclic_fond_can_close_against_retained_hddl_progress() -> None:
    problem = FONDProblem(
        initial_state="s0",
        goal_states=frozenset({"goal"}),
        transitions={("s0", "retry"): frozenset({"s0", "goal"})},
    )
    policy = CandidatePolicy(actions={"s0": "retry"})
    witnesses = {
        "s0": frozenset(
            {
                _witness("retry-a", "retry"),
                _witness("retry-b", "retry", "inspect"),
            }
        ),
    }

    check = check_fond_hddl_frontier_closure(
        problem,
        policy,
        semantics=PolicySemantics.STRONG_CYCLIC,
        hierarchy_witnesses=witnesses,
    )

    assert check.valid
    assert check.policy_check.valid
    assert check.policy_check.non_goal_cycle_states == frozenset({"s0"})
