# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""CloudGoat IAM Privesc — a SIMULATED planning domain over one attack scenario.

This models the ``iam_privesc_by_attachment`` scenario from the vendored
``vendor/gyms/cloudgoat`` gym (RhinoSecurityLabs/cloudgoat,
``cloudgoat/scenarios/aws/iam_privesc_by_attachment``): starting as the
limited IAM user "Kerrigan," reach the scenario's documented goal — deleting
the ``cg-super-critical-security-server`` EC2 instance — by escalating
privilege via instance-profile role attachment.

Everything here is simulation. The domain touches no AWS API, no Terraform
state, and no real IAM/EC2 resource; it imports nothing outside
``autofde_lab``. Each :class:`Action` is a state-tuple field flip named after
one step of the scenario's documented walkthrough
(``vendor/gyms/cloudgoat/cloudgoat/scenarios/aws/iam_privesc_by_attachment/README.md``,
section "Walkthrough - IAM User 'Kerrigan'") and its cheat sheet
(``cheat_sheet_kerrigan.md``, real ``aws`` CLI invocations against a live
CloudGoat deployment). This file computes a **candidate plan** over that
walkthrough's step structure — it does not actuate, admit, broker, or issue
receipts, and no action name here is evidence that the named AWS API call is
reachable from this repository.

Real preconditions, not decoration
-----------------------------------
The walkthrough is a strictly sequential exploit chain, and every precondition
below is taken directly from the scenario's own dependency structure rather
than invented for solver difficulty:

1. ``enumerate_profiles_and_roles`` — always applicable from the start (the
   attacker's first move with their limited "Kerrigan" credentials).
2. ``swap_admin_role_onto_profile`` — requires having enumerated
   (``iam:ListInstanceProfiles`` / ``iam:ListRoles`` results are what tell the
   attacker which profile/role pair to touch); swaps the full-admin
   ("mighty") role onto the meek instance profile.
3. ``create_keypair`` — also requires having enumerated first (the attacker
   needs to know a usable subnet/security group before it is worth minting a
   key), but does **not** require the role swap — it is the second of two
   genuinely independent prerequisites for launching the staging EC2
   instance, matching the cheat sheet's own step ordering (key-pair creation
   has no data dependency on the instance-profile edit).
4. ``launch_ec2_with_keypair_and_profile`` — requires both prior steps
   (the role swap for the goal's authority, the keypair for the goal's
   accessibility); this is the walkthrough's combined "create instance +
   attach the empowered profile" step.
5. ``ssh_to_instance`` — requires the instance to exist; the attacker gets a
   session and can now run ``aws`` CLI commands via the attached role.
6. ``terminate_target_instance`` — requires shell access via the mighty role;
   reaching this state is the scenario's documented goal.
"""

from __future__ import annotations

import itertools
from enum import Enum
from typing import Any, NamedTuple, Optional

from autofde_lab import DeterministicPlanningDomain, Space, Value
from autofde_lab.builders.domain import Renderable
from autofde_lab.hub.space.gym import EnumSpace, ListSpace


class Action(Enum):
    """The six simulated steps of the Kerrigan walkthrough."""

    enumerate_profiles_and_roles = 0
    swap_admin_role_onto_profile = 1
    create_keypair = 2
    launch_ec2_with_keypair_and_profile = 3
    ssh_to_instance = 4
    terminate_target_instance = 5


class State(NamedTuple):
    """Attacker foothold state. Hashable — booleans only."""

    enumerated: bool = False
    admin_role_on_profile: bool = False
    keypair_created: bool = False
    instance_launched: bool = False
    has_shell_access: bool = False
    target_terminated: bool = False


class D(DeterministicPlanningDomain, Renderable):
    T_state = State
    T_observation = T_state
    T_event = Action
    T_value = float
    T_predicate = bool
    T_info = None


class CloudGoatIamPrivescDomain(D):
    """Kerrigan's privilege-escalation route from ``iam_privesc_by_attachment``.

    # Parameters
    initial_state: optional non-default starting foothold, mainly useful for
        tests that want to start mid-chain (e.g. to exercise a replan).
    """

    def __init__(self, initial_state: Optional[State] = None) -> None:
        self._initial_state = initial_state if initial_state is not None else State()
        self._goal = State(
            enumerated=True,
            admin_role_on_profile=True,
            keypair_created=True,
            instance_launched=True,
            has_shell_access=True,
            target_terminated=True,
        )

    def applicable(self, state: State, action: Action) -> bool:
        """Public precondition predicate.

        Public because the walkthrough dependency claims tested against this
        domain are claims about *this predicate*, and a test asserting them
        should read the same function the solver does (mirrors
        ``BreachClockDomain.applicable``).
        """
        return self._applicable(state, action)

    def _applicable(self, state: State, action: Action) -> bool:
        if action == Action.enumerate_profiles_and_roles:
            return not state.enumerated
        if action == Action.swap_admin_role_onto_profile:
            return state.enumerated and not state.admin_role_on_profile
        if action == Action.create_keypair:
            return state.enumerated and not state.keypair_created
        if action == Action.launch_ec2_with_keypair_and_profile:
            return (
                state.admin_role_on_profile
                and state.keypair_created
                and not state.instance_launched
            )
        if action == Action.ssh_to_instance:
            return state.instance_launched and not state.has_shell_access
        if action == Action.terminate_target_instance:
            return state.has_shell_access and not state.target_terminated
        return False

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return ListSpace([a for a in Action if self._applicable(memory, a)])

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        if not self._applicable(memory, action):
            return memory

        if action == Action.enumerate_profiles_and_roles:
            return memory._replace(enumerated=True)
        if action == Action.swap_admin_role_onto_profile:
            return memory._replace(admin_role_on_profile=True)
        if action == Action.create_keypair:
            return memory._replace(keypair_created=True)
        if action == Action.launch_ec2_with_keypair_and_profile:
            return memory._replace(instance_launched=True)
        if action == Action.ssh_to_instance:
            return memory._replace(has_shell_access=True)
        if action == Action.terminate_target_instance:
            return memory._replace(target_terminated=True)
        return memory

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=1)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return EnumSpace(Action)

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace([self._goal])

    def _get_initial_state_(self) -> D.T_state:
        return self._initial_state

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace(
            [State(*bits) for bits in itertools.product([False, True], repeat=6)]
        )

    def _render_from(self, memory: D.T_memory[D.T_state], **kwargs: Any) -> Any:
        # No visual rendering for this domain; state is a small boolean tuple
        # printable directly.
        print(memory)
