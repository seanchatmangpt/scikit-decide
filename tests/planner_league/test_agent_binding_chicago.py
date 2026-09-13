"""Chicago-style proof that Agent is a fourth identity, distinct from
Planner, Policy, and Role (V2030.1.1 capability 2).

Real collaborators throughout: real ``ROLE_SPECS``, real
``PolicySpec.for_role``, real ``LeagueMatch``, real ``WORLD_CLASSES``. No
``unittest.mock`` / ``Mock`` / ``MagicMock`` / ``patch`` / ``monkeypatch`` are
used anywhere in this module.
"""

from __future__ import annotations

import pytest

from autofde_lab.planner_league import LeagueMatch, PolicySpec
from autofde_lab.planner_league.agent_binding import (
    AgentBinding,
    identity_quadruple,
    match_from_bindings,
)


def test_agent_differs_from_policy() -> None:
    """Two agents, same role, same policy: identities differ, policy identity does not."""
    policy = PolicySpec.for_role("Astar", "blue_defender")
    alice = AgentBinding(agent_id="alice", role_id="blue_defender", policy=policy)
    bob = AgentBinding(agent_id="bob", role_id="blue_defender", policy=policy)

    assert alice.identity_sha256 != bob.identity_sha256
    assert alice.policy_identity_sha256 == bob.policy_identity_sha256


def test_agent_differs_from_role_and_role_differs_from_policy() -> None:
    """Same agent, two real roles, same policy planner: Agent != Role, Role != Policy."""
    blue_policy = PolicySpec.for_role("Astar", "blue_defender")
    red_policy = PolicySpec.for_role("Astar", "red_disturbance")

    as_blue = AgentBinding(
        agent_id="alice", role_id="blue_defender", policy=blue_policy
    )
    as_red = AgentBinding(
        agent_id="alice", role_id="red_disturbance", policy=red_policy
    )

    assert as_blue.identity_sha256 != as_red.identity_sha256
    assert as_blue.policy.objective_id != as_red.policy.objective_id
    assert as_blue.agent_id == as_red.agent_id == "alice"


def test_planner_axis_isolated_from_policy_role_and_agent() -> None:
    """Same agent, same role, two real planners: only the planner axis in the quadruple differs."""
    astar_policy = PolicySpec.for_role("Astar", "blue_defender")
    mcts_policy = PolicySpec.for_role("MCTS", "blue_defender")

    with_astar = AgentBinding(
        agent_id="alice", role_id="blue_defender", policy=astar_policy
    )
    with_mcts = AgentBinding(
        agent_id="alice", role_id="blue_defender", policy=mcts_policy
    )

    q_astar = identity_quadruple(with_astar)
    q_mcts = identity_quadruple(with_mcts)

    agent_astar, role_astar, planner_astar, policy_digest_astar = q_astar
    agent_mcts, role_mcts, planner_mcts, policy_digest_mcts = q_mcts

    assert agent_astar == agent_mcts == "alice"
    assert role_astar == role_mcts == "blue_defender"
    assert planner_astar != planner_mcts
    assert planner_astar == "Astar"
    assert planner_mcts == "MCTS"
    # Changing the planner also changes the policy's own identity — Policy
    # tracks Planner as one of its fields, but Agent and Role are untouched.
    assert policy_digest_astar != policy_digest_mcts
    assert with_astar.identity_sha256 != with_mcts.identity_sha256


def test_unknown_role_is_refused_matching_league_match_shape() -> None:
    """AgentBinding refuses an unknown role with the same REFUSED shape LeagueMatch uses."""
    policy = PolicySpec.for_role("Astar", "blue_defender")
    with pytest.raises(ValueError, match=r"^REFUSED:UNKNOWN_ROLE:"):
        AgentBinding(agent_id="alice", role_id="not_a_real_role", policy=policy)

    # Confirm the real LeagueMatch refusal has the same prefix, so this
    # module's refusal genuinely matches the existing style rather than
    # merely resembling it by naming.
    with pytest.raises(ValueError, match=r"^REFUSED:UNKNOWN_ROLE:"):
        LeagueMatch(
            world_id="cyber_incident",
            left_role_id="not_a_real_role",
            left_policy=policy,
            right_role_id="blue_defender",
            right_policy=policy,
        )


def test_match_from_bindings_does_not_smuggle_agent_identity_into_the_match() -> None:
    """match_from_bindings() produces a LeagueMatch identical in shape to a direct one."""
    left_policy = PolicySpec.for_role("Astar", "blue_defender")
    right_policy = PolicySpec.for_role("MCTS", "red_disturbance")

    left_binding = AgentBinding(
        agent_id="alice", role_id="blue_defender", policy=left_policy
    )
    right_binding = AgentBinding(
        agent_id="bob", role_id="red_disturbance", policy=right_policy
    )

    via_bindings = match_from_bindings("cyber_incident", left_binding, right_binding)
    direct = LeagueMatch(
        world_id="cyber_incident",
        left_role_id="blue_defender",
        left_policy=left_policy,
        right_role_id="red_disturbance",
        right_policy=right_policy,
    )

    assert via_bindings.identity_sha256 == direct.identity_sha256
    assert via_bindings.as_gymact_candidate() == direct.as_gymact_candidate()

    # Agent identity is nowhere in the candidate payload: it rode beside the
    # match, never inside its experiment identity.
    candidate_json_str = repr(via_bindings.as_gymact_candidate())
    assert "alice" not in candidate_json_str
    assert "bob" not in candidate_json_str


def test_match_from_bindings_refuses_mismatched_information_partitions() -> None:
    """A real, typed refusal when the two bindings disagree on information partition."""
    policy = PolicySpec.for_role("Astar", "blue_defender")
    other_policy = PolicySpec.for_role("MCTS", "red_disturbance")
    left_binding = AgentBinding(
        agent_id="alice",
        role_id="blue_defender",
        policy=policy,
        information_partition_id="shared",
    )
    right_binding = AgentBinding(
        agent_id="bob",
        role_id="red_disturbance",
        policy=other_policy,
        information_partition_id="private",
    )

    with pytest.raises(ValueError, match=r"^REFUSED:INFORMATION_PARTITION_MISMATCH:"):
        match_from_bindings("cyber_incident", left_binding, right_binding)
