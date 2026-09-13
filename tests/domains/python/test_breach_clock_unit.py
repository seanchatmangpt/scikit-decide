# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test) for the Breach Clock domain.

SCOPE WARNING -- read before citing this file as evidence of anything:

    This exercises ONE registered solver against ONE locally-defined,
    fully SIMULATED domain. Nothing here contacts a cloud provider, an
    identity system, or a notification channel. ``revoke_sessions`` moves an
    enum. Passing supports exactly one claim: A* computes a goal-reaching,
    precondition-respecting plan over BreachClockDomain. It is not evidence
    for any actuation, admission, or cross-repository standing claim.

    Named ``_unit`` and not ``_chicago`` per tests/CLAUDE.md invariant 1: it
    is a domain checkpoint, not an exercise of the real system for its scope.
"""

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.breach_clock import (
    Action,
    BreachClockDomain,
    Containment,
    Notification,
    Scope,
)
from autofde_lab.hub.domain.breach_clock.breach_clock import (
    CONTAINMENT_CHOICE,
    DIVERGENCE_POPULATION,
    INDEPENDENT_ACTIONS,
)


@pytest.fixture
def domain():
    return BreachClockDomain()


def _rollout(domain, solver, max_steps: int = 30):
    obs = domain.reset()
    plan = []
    for _ in range(max_steps):
        if domain._is_terminal(obs):
            break
        action = solver.sample_action(obs)
        plan.append(action)
        obs = domain.step(action).observation
    return plan, obs


def test_astar_reaches_delivered_notification(domain):
    """Real registered solver, real domain, real rollout."""
    Astar = utils.load_registered_solver("Astar")
    assert Astar is not None, "Astar did not load from the registry"

    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        plan, obs = _rollout(domain, solver)

    assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
    assert obs.notification is Notification.DELIVERED
    assert obs.notified_populations == obs.populations

    # every prerequisite actually landed, and exactly one containment posture
    assert obs.triaged and obs.evidence and obs.scope is Scope.KNOWN
    assert obs.containment is not Containment.NONE
    chosen = [a for a in plan if a in CONTAINMENT_CHOICE]
    assert len(chosen) == 1, f"expected one containment action, got {chosen}"

    # the plan is precondition-respecting when replayed against the domain
    state = domain._get_initial_state_()
    for action in plan:
        assert domain.applicable(state, action), (
            f"{action} applied in a state where it is not applicable: {state}"
        )
        state = domain._get_next_state(state, action)
    assert domain._is_goal(state)


def test_the_three_independent_actions_share_no_precondition(domain):
    """Concurrency is real: none of the three enables another."""
    s0 = domain._get_initial_state_()
    for a in INDEPENDENT_ACTIONS:
        assert domain.applicable(s0, a), f"{a} not applicable initially"

    # doing any one of them leaves the other two applicable
    for a in INDEPENDENT_ACTIONS:
        s1 = domain._get_next_state(s0, a)
        for b in INDEPENDENT_ACTIONS:
            if b is a:
                continue
            assert domain.applicable(s1, b), f"{a} was a hidden precondition of {b}"


def test_containment_is_a_real_three_way_exclusive_choice(domain):
    """All three offered; taking one closes the other two out."""
    s = domain._get_next_state(domain._get_initial_state_(), Action.triage)
    for a in CONTAINMENT_CHOICE:
        assert domain.applicable(s, a), f"{a} not offered"

    for a in CONTAINMENT_CHOICE:
        after = domain._get_next_state(s, a)
        assert after.containment is CONTAINMENT_CHOICE[a]
        for b in CONTAINMENT_CHOICE:
            assert not domain.applicable(after, b), f"{b} survived choosing {a}"


def test_divergence_hook_invalidates_a_plan_that_had_already_drafted(domain):
    """The observation that forces a replan."""
    s = domain._get_initial_state_()
    for a in (
        Action.triage,
        Action.collect_evidence,
        Action.compute_scope,
        Action.revoke_sessions,
        Action.draft_notification,
    ):
        assert domain.applicable(s, a)
        s = domain._get_next_state(s, a)
    assert s.notified_populations == s.populations

    diverged = domain.observe_divergence(s)
    assert DIVERGENCE_POPULATION in diverged.populations
    assert diverged.scope is Scope.PARTIAL
    # delivering now would notify the wrong set -- so it is no longer applicable
    assert not domain.applicable(diverged, Action.deliver_notification)
    assert not domain._is_goal(domain._get_next_state(diverged, Action.deliver_notification))
    # and the hook is pure
    assert s.populations == domain._get_initial_state_().populations


def test_astar_replans_from_the_diverged_state(domain):
    """A fresh plan from the widened state still reaches the goal."""
    wider = BreachClockDomain(
        initial_populations=frozenset({"A", DIVERGENCE_POPULATION})
    )
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: wider) as solver:
        solver.solve()
        plan, obs = _rollout(wider, solver)
    assert wider._is_goal(obs), f"replan did not reach the goal. Plan: {plan}"
    assert obs.notified_populations == frozenset({"A", DIVERGENCE_POPULATION})
