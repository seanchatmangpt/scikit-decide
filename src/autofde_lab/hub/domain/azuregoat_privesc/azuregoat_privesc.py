# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic planning domain over AzureGoat's documented Module-1
privilege-escalation attack path.

AzureGoat (vendored at ``vendor/gyms/azuregoat``, upstream
https://github.com/ine-labs/AzureGoat) is INE's "vulnerable by design" Azure
infrastructure. Its Module 1 attack manual
(``attack-manuals/module-1/05-Privilege Escalation.md``) documents a real,
step-by-step chain: an attacker who already holds SSH access to a Virtual
Machine (whose managed identity carries only the Contributor role) discovers
an Automation Account runbook that runs with the Owner role, rewrites that
runbook to grant the VM's identity the Owner role, and runs it — escalating
from Contributor to Owner on the resource group.

The ten steps below are transcribed directly from that manual's numbered
steps 1-9 (step 8 splits into two discrete commands here: replace-content
and publish, then start) (SSH login, ``az login -i``, ``az resource list``, ``az role
assignment list``, ``az automation runbook list``, writing the
privilege-escalation PowerShell workflow, ``runbook replace-content``,
``runbook publish``, ``runbook start``) — this is not a fabricated or
generic privilege-escalation toy, it is that documented scenario modeled as
facts and actions:

* **state**: the frozenset of facts the attacker currently holds/knows
  (e.g. ``has_vm_ssh_access``, ``knows_automation_account_name``,
  ``runbook_started``).
* **action**: perform one specific documented step; each has a real
  precondition (the facts the manual says must already be true before that
  step is possible) and adds exactly the one fact that step establishes.
* **transition**: deterministic fact-set union, cost 1 per step (mirrors
  each command/action in the manual).
* **goal**: ``has_owner_role_on_resource_group`` — the manual's own stated
  objective ("escalate privilege to the owner of the resource group").

Precondition gating makes this a real (if small) planning problem, not just
a fixed sequence to replay: actions are only applicable once their
documented prerequisite facts hold, so a solver must actually discover the
manual's step ordering rather than being handed it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Optional

from autofde_lab import D, DeterministicPlanningDomain, Space, Value
from autofde_lab.core import ImplicitSpace
from autofde_lab.hub.space.gym import ListSpace

DEFAULT_MANUAL_FILE = (
    Path(__file__).resolve().parents[5]
    / "vendor"
    / "gyms"
    / "azuregoat"
    / "attack-manuals"
    / "module-1"
    / "05-Privilege Escalation.md"
)

# Matches "**Step 1:**", "**Step 8:**", ... headers in the real vendored
# manual, capturing the step number and the sentence introducing it.
_STEP_HEADER_RE = re.compile(r"\*\*Step (\d+):\*\*\s*(.*)")
# Matches a fenced code block's contents (the literal shell/PowerShell text).
_CODE_BLOCK_RE = re.compile(r"```(?:\w*)\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class ManualStep:
    """One real step parsed at runtime out of AzureGoat's own vendored
    Module-1 Privilege Escalation manual (not a hand-copied constant)."""

    number: int
    intro: str
    code: str


def parse_manual_steps(manual_file: Path = DEFAULT_MANUAL_FILE) -> list[ManualStep]:
    """Parse every ``**Step N:**`` section and its first fenced code block out
    of the real vendored AzureGoat manual text at runtime.

    This gives the domain a real, re-checkable link back to its source: if
    the vendored manual changes, or if ``ATTACK_STEPS`` drifts from what the
    manual actually documents, a parity check against this parse can catch
    it, the same way ``terragoat_remediation.parse_findings`` keeps that
    domain's findings tied to the real vendored Terraform text instead of a
    disconnected hand-authored copy.

    # Parameters
    manual_file: path to the real vendored manual markdown file.

    # Returns
    list[ManualStep]: one entry per ``**Step N:**`` header found, in file
        order, each carrying the real intro sentence and the real fenced
        code block text (or ``""`` if that step has no code block, e.g. a
        pure explanation step).
    """
    text = manual_file.read_text()
    headers = list(_STEP_HEADER_RE.finditer(text))
    if not headers:
        raise ValueError(f"No '**Step N:**' headers parsed from {manual_file}")

    steps: list[ManualStep] = []
    for i, match in enumerate(headers):
        number = int(match.group(1))
        intro = match.group(2).strip()
        section_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section_text = text[match.end() : section_end]
        code_match = _CODE_BLOCK_RE.search(section_text)
        code = code_match.group(1) if code_match else ""
        steps.append(ManualStep(number=number, intro=intro, code=code))
    return steps


@dataclass(frozen=True)
class AttackStep:
    """One documented step from AzureGoat's Module-1 Privilege Escalation manual."""

    id: str
    description: str
    manual_step: str
    preconditions: frozenset[str]
    establishes: str


# Transcribed from vendor/gyms/azuregoat's
# attack-manuals/module-1/05-Privilege Escalation.md, steps 1-9.
ATTACK_STEPS: tuple[AttackStep, ...] = (
    AttackStep(
        id="ssh_login_vm",
        description=(
            "ssh -i justin.pem justin@<vm-ip> using credentials obtained from "
            "config.txt"
        ),
        manual_step="Step 1",
        preconditions=frozenset(),
        establishes="has_vm_ssh_access",
    ),
    AttackStep(
        id="az_login_managed_identity",
        description="az login -i (authenticate as the VM's managed identity)",
        manual_step="Step 2",
        preconditions=frozenset({"has_vm_ssh_access"}),
        establishes="has_managed_identity_context",
    ),
    AttackStep(
        id="list_resources_for_principal_id",
        description=(
            "az resource list (locate the VM's name and principal ID)"
        ),
        manual_step="Step 3",
        preconditions=frozenset({"has_managed_identity_context"}),
        establishes="knows_vm_principal_id",
    ),
    AttackStep(
        id="list_role_assignments",
        description=(
            "az role assignment list -g azuregoat_app (confirm Contributor "
            "role on the VM and locate the Owner-role principal)"
        ),
        manual_step="Step 4",
        preconditions=frozenset({"knows_vm_principal_id"}),
        establishes="knows_owner_role_principal_id",
    ),
    AttackStep(
        id="correlate_owner_principal_to_automation_account",
        description=(
            "az resource list again, matching the Owner principal ID to an "
            "Automation Account resource"
        ),
        manual_step="Step 5",
        preconditions=frozenset({"knows_owner_role_principal_id"}),
        establishes="knows_automation_account_name",
    ),
    AttackStep(
        id="list_runbooks",
        description=(
            "az automation runbook list --automation-account-name <name> "
            "-g azuregoat_app (find the PowerShellWorkflow runbook)"
        ),
        manual_step="Step 6",
        preconditions=frozenset({"knows_automation_account_name"}),
        establishes="knows_runbook_name",
    ),
    AttackStep(
        id="write_privesc_runbook_script",
        description=(
            "Write a PowerShell workflow that calls New-AzRoleAssignment "
            "-RoleDefinitionName Owner -ObjectId <VM-Object-ID> to grant the "
            "VM's identity the Owner role"
        ),
        manual_step="Step 7",
        preconditions=frozenset({"knows_runbook_name"}),
        establishes="has_privesc_script",
    ),
    AttackStep(
        id="replace_and_publish_runbook",
        description=(
            "az automation runbook replace-content ... && az automation "
            "runbook publish ... (install the privesc script into the "
            "Owner-privileged runbook)"
        ),
        manual_step="Step 8a",
        preconditions=frozenset({"has_privesc_script"}),
        establishes="runbook_published",
    ),
    AttackStep(
        id="start_runbook",
        description=(
            "az automation runbook start --automation-account-name <name> "
            "-g azuregoat_app --name <runbook> (runbook executes under the "
            "Owner-privileged Automation Account identity)"
        ),
        manual_step="Step 8b",
        preconditions=frozenset({"runbook_published"}),
        establishes="runbook_started",
    ),
    AttackStep(
        id="confirm_owner_role",
        description=(
            "az role assignment list -g azuregoat_app (role changed from "
            "Contributor to Owner for the VM's identity)"
        ),
        manual_step="Step 9",
        preconditions=frozenset({"runbook_started"}),
        establishes="has_owner_role_on_resource_group",
    ),
)

GOAL_FACT = "has_owner_role_on_resource_group"


class State(NamedTuple):
    facts: frozenset[str]


class D_(
    DeterministicPlanningDomain,
):
    T_state = State
    T_observation = T_state
    T_event = str  # attack step id
    T_value = float
    T_predicate = bool
    T_info = None


class AzureGoatPrivilegeEscalation(D_):
    """Plan the documented AzureGoat Module-1 Contributor-to-Owner escalation.

    Models the attacker as starting with nothing (no cloud access at all)
    and searches for the documented sequence of ten steps that ends with
    Owner-level access to the resource group, exactly as
    ``attack-manuals/module-1/05-Privilege Escalation.md`` describes it.
    """

    def __init__(self, steps: tuple[AttackStep, ...] = ATTACK_STEPS) -> None:
        """
        # Parameters
        steps: the documented attack steps to plan over. Defaults to the
            full ten-step AzureGoat Module-1 privilege-escalation chain.
        """
        self.steps = steps
        self._by_id = {s.id: s for s in steps}
        if GOAL_FACT not in {s.establishes for s in steps}:
            raise ValueError(
                f"No step in the provided chain establishes the goal fact "
                f"{GOAL_FACT!r}; cannot build a solvable privesc domain."
            )

    def describe_step(self, step_id: str) -> AttackStep:
        """Look up the real documented AttackStep (manual step + command) behind an action id."""
        return self._by_id[step_id]

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        step = self._by_id[action]
        return State(facts=memory.facts | {step.establishes})

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=1.0)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ListSpace([s.id for s in self.steps])

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(
            [
                s.id
                for s in self.steps
                if s.preconditions <= memory.facts and s.establishes not in memory.facts
            ]
        )

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(lambda state: GOAL_FACT in state.facts)

    def _get_initial_state_(self) -> D.T_state:
        return State(facts=frozenset())

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace([State(facts=frozenset({GOAL_FACT}))])
