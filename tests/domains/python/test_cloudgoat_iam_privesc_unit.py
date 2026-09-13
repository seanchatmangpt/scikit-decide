# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test) for the CloudGoat IAM
privilege-escalation domain.

SCOPE WARNING -- read before citing this file as evidence of anything:

    This exercises ONE registered solver (A*) against ONE locally-defined,
    fully SIMULATED domain modeling the vendored ``vendor/gyms/cloudgoat``
    scenario ``iam_privesc_by_attachment``. Nothing here contacts AWS,
    Terraform, or any CloudGoat deployment. ``terminate_target_instance``
    flips a boolean in a state tuple. Passing supports exactly one claim: A*
    computes a goal-reaching, precondition-respecting plan over
    CloudGoatIamPrivescDomain that mirrors the scenario's documented
    walkthrough step order. It is not evidence of any actuation, admission,
    real AWS API call, or cross-repository standing claim.

    Named ``_unit`` and not ``_chicago`` per tests/CLAUDE.md invariant 1: it
    is a domain checkpoint, not an exercise of the real system for its scope.
"""

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.cloudgoat_iam_privesc import (
    Action,
    CloudGoatIamPrivescDomain,
    State,
)


@pytest.fixture
def domain():
    return CloudGoatIamPrivescDomain()


def _rollout(domain, solver, max_steps: int = 20):
    obs = domain.reset()
    plan = []
    for _ in range(max_steps):
        if domain._is_terminal(obs):
            break
        action = solver.sample_action(obs)
        plan.append(action)
        obs = domain.step(action).observation
    return plan, obs


def test_astar_reaches_terminated_target_instance(domain):
    """Real registered solver, real domain, real rollout."""
    Astar = utils.load_registered_solver("Astar")
    assert Astar is not None, "Astar did not load from the registry"

    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        plan, obs = _rollout(domain, solver)

    assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
    assert obs.target_terminated is True

    # every prerequisite in the walkthrough actually landed, in the right
    # dependency order -- not just the final flag flipped in isolation
    assert obs.enumerated
    assert obs.admin_role_on_profile
    assert obs.keypair_created
    assert obs.instance_launched
    assert obs.has_shell_access

    # the plan follows the scenario's documented step order: enumeration
    # strictly precedes both the role swap and the keypair creation; the
    # launch strictly follows both; shell access precedes termination.
    assert plan[0] == Action.enumerate_profiles_and_roles
    assert plan.index(Action.swap_admin_role_onto_profile) > plan.index(
        Action.enumerate_profiles_and_roles
    )
    assert plan.index(Action.create_keypair) > plan.index(
        Action.enumerate_profiles_and_roles
    )
    assert plan.index(Action.launch_ec2_with_keypair_and_profile) > plan.index(
        Action.swap_admin_role_onto_profile
    )
    assert plan.index(Action.launch_ec2_with_keypair_and_profile) > plan.index(
        Action.create_keypair
    )
    assert plan.index(Action.ssh_to_instance) > plan.index(
        Action.launch_ec2_with_keypair_and_profile
    )
    assert plan.index(Action.terminate_target_instance) > plan.index(
        Action.ssh_to_instance
    )

    # the plan is precondition-respecting when replayed against the domain
    state = domain._get_initial_state_()
    for action in plan:
        assert domain.applicable(state, action), (
            f"{action} applied in a state where it is not applicable: {state}"
        )
        state = domain._get_next_state(state, action)
    assert domain._is_goal(state)


def test_role_swap_requires_enumeration_first(domain):
    """A genuine precondition, not decoration: can't swap the role blind."""
    s0 = domain._get_initial_state_()
    assert not domain.applicable(s0, Action.swap_admin_role_onto_profile)
    assert not domain.applicable(s0, Action.create_keypair)
    assert domain.applicable(s0, Action.enumerate_profiles_and_roles)

    s1 = domain._get_next_state(s0, Action.enumerate_profiles_and_roles)
    assert domain.applicable(s1, Action.swap_admin_role_onto_profile)
    assert domain.applicable(s1, Action.create_keypair)


def test_launch_requires_both_role_swap_and_keypair(domain):
    """Real AND-precondition: neither prerequisite alone suffices."""
    enumerated = domain._get_next_state(
        domain._get_initial_state_(), Action.enumerate_profiles_and_roles
    )

    only_role = domain._get_next_state(
        enumerated, Action.swap_admin_role_onto_profile
    )
    assert not domain.applicable(
        only_role, Action.launch_ec2_with_keypair_and_profile
    )

    only_keypair = domain._get_next_state(enumerated, Action.create_keypair)
    assert not domain.applicable(
        only_keypair, Action.launch_ec2_with_keypair_and_profile
    )

    both = domain._get_next_state(only_role, Action.create_keypair)
    assert domain.applicable(both, Action.launch_ec2_with_keypair_and_profile)


def test_terminate_requires_shell_access_via_the_escalated_instance(domain):
    """The goal action is gated on having actually staged through the exploit."""
    s = domain._get_initial_state_()
    for a in (
        Action.enumerate_profiles_and_roles,
        Action.swap_admin_role_onto_profile,
        Action.create_keypair,
        Action.launch_ec2_with_keypair_and_profile,
    ):
        s = domain._get_next_state(s, a)
    assert not domain.applicable(s, Action.terminate_target_instance)

    s = domain._get_next_state(s, Action.ssh_to_instance)
    assert domain.applicable(s, Action.terminate_target_instance)
    s = domain._get_next_state(s, Action.terminate_target_instance)
    assert domain._is_goal(s)


def test_astar_resumes_from_a_partway_state():
    """A domain started mid-chain (already enumerated + keypair) still
    reaches the goal without redoing recon."""
    partway = State(enumerated=True, keypair_created=True)
    domain = CloudGoatIamPrivescDomain(initial_state=partway)

    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        plan, obs = _rollout(domain, solver)

    assert domain._is_goal(obs)
    assert Action.enumerate_profiles_and_roles not in plan
    assert Action.create_keypair not in plan
