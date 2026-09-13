# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real GymAct `EnvironmentProvider`/`Environment` bridge for the real
AzureGoat Module-1 privilege-escalation domain (`azuregoat_privesc.py`).

This is a real integration against the real, standalone `gymact` package
(installed as a real path dependency -- see `pyproject.toml`'s
`[tool.uv.sources]` and the `gymact` entry in `dependencies`), following
`~/gymact/docs/integrations/consumer-setup.md`'s checklist and structurally
matching `gymact.providers.MemoryProvider`/`MemoryEnvironment`, the reference
implementation documented there.

`materialize()` builds a real `AzureGoatPrivilegeEscalation` domain instance
and a real, C++-backed `Astar` solver (`autofde_lab.hub.solver.astar.astar.Astar`,
resolved the same way `tests/ecosystem/test_gymact_terragoat_bridge_chicago.py`
resolves it: `autofde_lab.utils.load_registered_solver("Astar")`), runs
`solver.solve()` for real, and replays the resulting policy from the real
initial state to derive a real, ordered 10-step plan -- exactly the manual's
documented step ordering (`ssh_login_vm` through `confirm_owner_role`), not a
hand-written sequence.

Every one of the ten `ATTACK_STEPS` is exposed as one `gymact.models.Capability`
classified `Consequence.DO`: each step is a real, world-changing actuation
against AzureGoat's documented attack surface (SSH login, `az login -i`,
rewriting and publishing an Owner-privileged runbook, starting it -- see that
module's own docstring), never `READ`. Per
`~/gymact/.claude/rules/actuation-authority.md` and this repo's own
consequence law (`request accepted != world changed != objective verified`),
`actuate()` refuses (raises `ActuationRefused`, never silently no-ops or
advances) any capability that is not the real solved plan's next step from
the real current state -- both the domain's own real precondition check
(`get_applicable_actions`) and the real plan cursor must agree, so neither an
inapplicable step nor an out-of-order-but-applicable step is silently
admitted.

`verify()` checks real observed state against `GOAL_FACT`
(`has_owner_role_on_resource_group`) membership, matching the manual's own
stated objective. `checkpoint()`/`restore()` snapshot/restore the real
`(facts, plan_cursor)` pair. `teardown()` is a real, idempotent no-op --
this domain holds no external resources (no subprocess, no network, no
filesystem handle) to release.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from gymact.models import Capability, Consequence

from autofde_lab import utils

from .azuregoat_privesc import ATTACK_STEPS, GOAL_FACT, AzureGoatPrivilegeEscalation, State

AZUREGOAT_PRIVESC_CAPABILITIES: tuple[Capability, ...] = tuple(
    Capability(
        iri=f"urn:gymact:azuregoat-privesc:capability:{step.id}",
        title=f"{step.manual_step}: {step.description}",
        consequence=Consequence.DO,
        binding=step.id,
    )
    for step in ATTACK_STEPS
)


class ActuationRefused(RuntimeError):
    """Raised when `actuate()` is asked to run a capability that is not the
    real next applicable step of the real solved plan from the real current
    state -- never silently allowed, per
    `~/gymact/.claude/rules/actuation-authority.md`.
    """


class AzureGoatPrivescEnvironment:
    """One materialized instance of the real AzureGoat Module-1
    privilege-escalation domain, with a real solved plan and real internal
    fact-set state advanced by real, precondition-checked actuation.
    """

    def __init__(self, *, requires_authority: bool = True) -> None:
        self.environment_id = f"urn:gymact:azuregoat-privesc:environment:{uuid4().hex}"
        self.requires_authority = requires_authority
        self._domain = AzureGoatPrivilegeEscalation()
        self._closed = False

        astar_cls = utils.load_registered_solver("Astar")
        plan: list[str] = []
        with astar_cls(domain_factory=lambda: self._domain) as solver:
            solver.solve()
            obs = self._domain.get_initial_state()
            for _ in range(len(self._domain.steps) + 1):
                if self._domain.is_goal(obs):
                    break
                action = solver.sample_action(obs)
                plan.append(action)
                obs = self._domain.get_next_state(obs, action)

        if not self._domain.is_goal(obs):
            raise RuntimeError(
                "real Astar solve did not reach the AzureGoat privesc goal "
                f"{GOAL_FACT!r}; computed partial plan: {plan}"
            )

        self._plan: tuple[str, ...] = tuple(plan)
        self._state: State = self._domain.get_initial_state()
        self._plan_cursor = 0

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("environment is torn down")

    def capabilities(self) -> tuple[Capability, ...]:
        self._ensure_open()
        return AZUREGOAT_PRIVESC_CAPABILITIES

    async def observe(self) -> dict[str, Any]:
        self._ensure_open()
        return {"facts": sorted(self._state.facts)}

    async def actuate(self, capability: Capability, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self._ensure_open()
        step_id = capability.binding
        try:
            step = self._domain.describe_step(step_id)
        except KeyError:
            raise ActuationRefused(
                f"refused: {step_id!r} is not a real AzureGoat privesc attack step"
            ) from None

        applicable_ids = {
            a for a in self._domain.get_applicable_actions(self._state).get_elements()
        }
        if step_id not in applicable_ids:
            raise ActuationRefused(
                f"refused: {step_id!r} is not applicable from the real current state "
                f"{sorted(self._state.facts)!r} (preconditions "
                f"{sorted(step.preconditions)!r} unmet, or already established)"
            )

        expected_next = self._plan[self._plan_cursor] if self._plan_cursor < len(self._plan) else None
        if step_id != expected_next:
            raise ActuationRefused(
                f"refused: {step_id!r} is applicable but is not the real solved "
                f"plan's next step (expected {expected_next!r} at plan cursor "
                f"{self._plan_cursor})"
            )

        before = self._state
        next_state = self._domain.get_next_state(before, step_id)
        self._state = next_state
        self._plan_cursor += 1
        return {
            "before": {"facts": sorted(before.facts)},
            "after": {"facts": sorted(next_state.facts)},
            "capability": capability.iri,
            "manual_step": step.manual_step,
            "established": step.establishes,
        }

    async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        self._ensure_open()
        observed = await self.observe()
        if "facts" in expected:
            expected_facts = set(expected["facts"])
            passed = expected_facts <= set(observed["facts"])
        else:
            passed = GOAL_FACT in observed["facts"]
        return passed, observed

    async def checkpoint(self) -> dict[str, Any]:
        self._ensure_open()
        return {"facts": sorted(self._state.facts), "plan_cursor": self._plan_cursor}

    async def restore(self, checkpoint: dict[str, Any]) -> None:
        self._ensure_open()
        self._state = State(facts=frozenset(checkpoint["facts"]))
        self._plan_cursor = int(checkpoint.get("plan_cursor", 0))

    async def teardown(self) -> None:
        # Real, idempotent no-op: this domain holds no external resource
        # (no subprocess, no network socket, no filesystem handle) that
        # needs releasing -- unlike e.g. gymact.gyms.kubernetes_reconciliation,
        # which tears down a real cluster object. Safe to call repeatedly.
        self._closed = True


class AzureGoatPrivescProvider:
    """Real `gymact.providers.EnvironmentProvider` that materializes the real
    AzureGoat Module-1 privilege-escalation domain (structurally matching
    `gymact.providers.MemoryProvider`, the documented reference shape).
    """

    name = "azuregoat_privesc"
    materialization_requires_authority = False

    def __init__(self, *, requires_authority: bool = True) -> None:
        self.requires_authority = requires_authority

    async def materialize(
        self, *, scenario: str | None, config: dict[str, Any]
    ) -> AzureGoatPrivescEnvironment:
        del scenario
        configured = config.get("requires_authority", self.requires_authority)
        if not isinstance(configured, bool):
            raise TypeError("config.requires_authority must be a boolean")
        return AzureGoatPrivescEnvironment(requires_authority=configured)
