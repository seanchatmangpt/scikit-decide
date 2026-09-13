"""Candidate-only frontier closure between FOND policies and HDDL progress.

FOND world state and HDDL task-network progress are different state dimensions.
A world-state-only candidate policy is compatible with retained hierarchy progress
only when its selected primitive action is permitted by every admitted HDDL
progress witness for that reachable world state.

This is deliberately a frontier check, not a synchronized FOND×HDDL product proof.
It does not establish witness provenance, hierarchy-progress transitions, plan
admission, authorization, or actuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .fond_policy import (
    ActionId,
    CandidatePolicy,
    FONDProblem,
    PolicyCheck,
    PolicySemantics,
    StateId,
    check_candidate_policy,
)


@dataclass(frozen=True)
class HDDLProgressWitness:
    """One retained HDDL task-network progress state and its primitive frontier."""

    task_network_state: str
    permitted_primitive_actions: frozenset[ActionId]


@dataclass(frozen=True)
class FONDHDDLFrontierCheck:
    """Typed evidence for candidate-level FOND↔HDDL frontier compatibility."""

    policy_check: PolicyCheck
    valid: bool
    missing_hierarchy_witness_states: frozenset[StateId]
    malformed_hierarchy_witness_states: frozenset[StateId]
    hierarchy_closed_action_states: frozenset[StateId]
    hierarchy_rejected_action_states: frozenset[StateId]
    rejected_progress_witnesses: frozenset[tuple[StateId, str]]
    claim_ceiling: str = "candidate_fond_hddl_frontier_only"


def check_fond_hddl_frontier_closure(
    problem: FONDProblem,
    policy: CandidatePolicy,
    *,
    semantics: PolicySemantics,
    hierarchy_witnesses: Mapping[StateId, frozenset[HDDLProgressWitness]],
) -> FONDHDDLFrontierCheck:
    """Check FOND validity plus universal HDDL primitive-frontier compatibility.

    Every reachable non-goal world state must retain at least one explicit HDDL
    progress witness. Because hierarchy progress is not recoverable from world
    state alone, a world-state-only FOND action is accepted only when *every*
    admitted progress witness for that world state permits the selected primitive
    action. A missing or malformed witness is a typed failure, never permission to
    flatten or infer the task network.

    The result remains candidate-only and carries no SELECT/CONSTRUCT/DO authority.
    """

    policy_check = check_candidate_policy(problem, policy, semantics=semantics)
    missing: set[StateId] = set()
    malformed: set[StateId] = set()
    accepted: set[StateId] = set()
    rejected: set[StateId] = set()
    rejected_progress: set[tuple[StateId, str]] = set()

    for state in policy_check.reachable_states - problem.goal_states:
        witnesses = hierarchy_witnesses.get(state)
        if not witnesses:
            missing.add(state)
            continue
        if any(not witness.task_network_state for witness in witnesses):
            malformed.add(state)
            continue

        action = policy.actions.get(state)
        if action is None:
            # The FOND checker already records this as a missing policy state.
            continue

        blocked = {
            (state, witness.task_network_state)
            for witness in witnesses
            if action not in witness.permitted_primitive_actions
        }
        if blocked:
            rejected.add(state)
            rejected_progress.update(blocked)
        else:
            accepted.add(state)

    valid = policy_check.valid and not missing and not malformed and not rejected
    return FONDHDDLFrontierCheck(
        policy_check=policy_check,
        valid=valid,
        missing_hierarchy_witness_states=frozenset(missing),
        malformed_hierarchy_witness_states=frozenset(malformed),
        hierarchy_closed_action_states=frozenset(accepted),
        hierarchy_rejected_action_states=frozenset(rejected),
        rejected_progress_witnesses=frozenset(rejected_progress),
    )
