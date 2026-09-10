"""Candidate-only closure checks between FOND policies and HDDL progress witnesses.

A FOND world-state policy is not equivalent to an HDDL policy: HTN progress is part
of the planning state.  This module therefore refuses to erase hierarchy.  Callers
must provide an explicit per-state decomposition/progress witness that names the
primitive HDDL actions currently permitted by the retained task network.

The checks below establish only candidate-level closure.  They do not prove that a
witness was produced by a trusted HDDL engine, do not admit a plan or policy, and do
not confer SELECT/CONSTRUCT/DO authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .fond_policy import (
    CandidatePolicy,
    FONDProblem,
    PolicyCheck,
    PolicySemantics,
    StateId,
    check_candidate_policy,
)


@dataclass(frozen=True)
class HDDLProgressWitness:
    """Retained HTN progress for one reachable FOND state.

    ``task_network_state`` is an opaque identity supplied by the HDDL side; it must
    not be reconstructed from world state. ``permitted_primitive_actions`` is the
    primitive frontier exposed by that retained hierarchy state.
    """

    task_network_state: str
    permitted_primitive_actions: frozenset[str]


@dataclass(frozen=True)
class FONDHDDLClosureCheck:
    policy_check: PolicyCheck
    valid: bool
    missing_hierarchy_witness_states: frozenset[StateId]
    hierarchy_closed_action_states: frozenset[StateId]
    hierarchy_rejected_action_states: frozenset[StateId]
    claim_ceiling: str = "candidate_fond_hddl_closure_only"


def check_fond_hddl_closure(
    problem: FONDProblem,
    policy: CandidatePolicy,
    *,
    semantics: PolicySemantics,
    hierarchy_witnesses: Mapping[StateId, HDDLProgressWitness],
) -> FONDHDDLClosureCheck:
    """Check FOND policy validity plus per-state HDDL primitive-frontier closure.

    Every reachable non-goal state must retain an explicit HTN-progress witness.
    The selected FOND action must be in that witness's primitive action frontier.
    A missing witness is a typed failure rather than permission to flatten the HTN.
    """

    policy_check = check_candidate_policy(problem, policy, semantics=semantics)
    missing: set[StateId] = set()
    accepted: set[StateId] = set()
    rejected: set[StateId] = set()

    for state in policy_check.reachable_states - problem.goal_states:
        witness = hierarchy_witnesses.get(state)
        if witness is None or not witness.task_network_state:
            missing.add(state)
            continue

        action = policy.actions.get(state)
        if action is None:
            # The FOND checker already records this as a missing policy state.
            continue
        if action in witness.permitted_primitive_actions:
            accepted.add(state)
        else:
            rejected.add(state)

    valid = policy_check.valid and not missing and not rejected
    return FONDHDDLClosureCheck(
        policy_check=policy_check,
        valid=valid,
        missing_hierarchy_witness_states=frozenset(missing),
        hierarchy_closed_action_states=frozenset(accepted),
        hierarchy_rejected_action_states=frozenset(rejected),
    )
