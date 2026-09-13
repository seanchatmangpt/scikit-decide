# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school test for
autofde_lab.hub.domain.azuregoat_privesc.AzureGoatPrivilegeEscalation.

Exercises the real domain (the ten documented steps transcribed from
AzureGoat's ``attack-manuals/module-1/05-Privilege Escalation.md``, no
mocked domain internals) against the real, already-registered Astar
solver's ``solve()``. Assertions are on real final state (attacker holds
the Owner role) and the real returned plan - no mocking of the domain or
solver under test.
"""

from __future__ import annotations

import re

from autofde_lab.hub.domain.azuregoat_privesc import AzureGoatPrivilegeEscalation
from autofde_lab.hub.domain.azuregoat_privesc.azuregoat_privesc import (
    ATTACK_STEPS,
    DEFAULT_MANUAL_FILE,
    GOAL_FACT,
    parse_manual_steps,
)
from autofde_lab.hub.solver.astar import Astar

# For each hand-authored AttackStep, the literal command substring that must
# appear, verbatim, in the real vendored manual's fenced code block for that
# step -- proves the domain's preconditions/establishes are not a free-floating
# fabrication disconnected from the source, even though (unlike TerraGoat's
# regex-parsed findings) preconditions/establishes are a modeling choice that
# cannot itself be regex-parsed out of unstructured attack-manual prose.
_EXPECTED_COMMAND_SUBSTRING: dict[str, str] = {
    "ssh_login_vm": "ssh -i justin.pem justin@",
    "az_login_managed_identity": "az login -i",
    "list_resources_for_principal_id": "az resource list",
    "list_role_assignments": "az role assignment list -g azuregoat_app",
    "correlate_owner_principal_to_automation_account": "az resource list",
    "list_runbooks": "az automation runbook list --automation-account-name",
    "write_privesc_runbook_script": "New-AzRoleAssignment",
    "replace_and_publish_runbook": "runbook replace-content",
    "start_runbook": "runbook start",
    "confirm_owner_role": "az role assignment list -g azuregoat_app",
}


def test_attack_steps_match_real_manual_commands_parsed_at_runtime():
    """Cross-check every hand-authored AttackStep against a real runtime
    regex parse of the real vendored manual file (not a hard-coded copy of
    the manual's text, and not trusting the domain module's own docstring
    claim of transcription): the manual step number in each AttackStep must
    resolve to a real ``**Step N:**`` section in
    ``vendor/gyms/azuregoat/attack-manuals/module-1/05-Privilege Escalation.md``,
    and that section's real fenced code block must literally contain the
    command substring the AttackStep claims to be transcribing.

    This is the AzureGoat analogue of what
    ``terragoat_remediation.parse_findings`` gives TerraGoat: a runtime,
    re-checkable link from the domain back to the real vendored source, so
    manual drift or a transcription error is a real, automatically-caught
    test failure instead of an unverifiable claim.
    """
    assert DEFAULT_MANUAL_FILE.is_file(), (
        f"expected real vendored manual at {DEFAULT_MANUAL_FILE}"
    )

    manual_steps = parse_manual_steps(DEFAULT_MANUAL_FILE)
    assert len(manual_steps) == 9, (
        "the real vendored manual documents Steps 1-9; a count drift here "
        "means either the vendored file or this parser changed"
    )
    by_number = {s.number: s for s in manual_steps}

    assert len(ATTACK_STEPS) == len(_EXPECTED_COMMAND_SUBSTRING)
    for step in ATTACK_STEPS:
        manual_number = int(re.match(r"Step (\d+)", step.manual_step).group(1))
        assert manual_number in by_number, (
            f"{step.id!r} claims {step.manual_step!r}, but the real manual "
            f"has no Step {manual_number}"
        )
        real_code = by_number[manual_number].code
        expected_substring = _EXPECTED_COMMAND_SUBSTRING[step.id]
        assert expected_substring in real_code, (
            f"{step.id!r} claims command {expected_substring!r} from real "
            f"{step.manual_step!r}, but the real manual's code block for "
            f"Step {manual_number} is:\n{real_code!r}"
        )


def test_attack_steps_are_the_documented_azuregoat_manual_chain():
    """The transcribed steps must form a real, satisfiable precondition chain
    (each step's preconditions are establishable by some earlier step), and
    must end with the manual's own stated objective."""
    assert len(ATTACK_STEPS) == 10
    assert ATTACK_STEPS[0].preconditions == frozenset()
    assert ATTACK_STEPS[-1].establishes == GOAL_FACT

    established_so_far: set[str] = set()
    for step in ATTACK_STEPS:
        assert step.preconditions <= established_so_far, (
            f"step {step.id!r} ({step.manual_step}) requires "
            f"{step.preconditions - established_so_far} before it is reachable "
            "in the documented order"
        )
        established_so_far.add(step.establishes)


def test_astar_solves_azuregoat_privilege_escalation_to_owner_role():
    """Real domain, real Astar solver, real solve() call, real final state:
    the attacker reaches has_owner_role_on_resource_group."""
    domain_factory = lambda: AzureGoatPrivilegeEscalation()
    domain = domain_factory()

    initial_state = domain.get_initial_state()
    assert initial_state.facts == frozenset()
    assert not domain.is_goal(initial_state)

    with Astar(domain_factory=domain_factory) as solver:
        solver.solve()

        state = initial_state
        applied_actions = []
        for _ in range(len(ATTACK_STEPS) + 1):
            if domain.is_goal(state):
                break
            action = solver.get_next_action(state)
            state = domain.get_next_state(state, action)
            applied_actions.append(action)

        # Real goal state reached: attacker now holds the Owner role.
        assert domain.is_goal(state)
        assert GOAL_FACT in state.facts

        # Every documented step was taken exactly once, in a precondition-valid
        # order (no repeats, no omissions, no skipped prerequisites).
        assert set(applied_actions) == {s.id for s in ATTACK_STEPS}
        assert len(applied_actions) == 10
        assert applied_actions[0] == "ssh_login_vm"
        assert applied_actions[-1] == "confirm_owner_role"

        plan = solver.get_plan(initial_state)
        assert len(plan) == 10
        total_cost = sum(value.cost for _, _, value in plan)
        assert total_cost == 10.0
