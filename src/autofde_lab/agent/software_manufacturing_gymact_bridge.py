# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real GymAct `EnvironmentProvider`/`Environment` bridge for a compiled
software-manufacturing plan (see `software_manufacturing_history.py`).

Structurally matches `azuregoat_privesc/gymact_bridge.py` (this repo's own
reference AzureGoat integration) and `gymact.providers.MemoryProvider` (the
package's documented reference shape): a real `gymact.models.Capability` per
plan step, real `actuate()`/`observe()`/`verify()`/`checkpoint()`/`restore()`
methods driving the real, already-tested `ReplayWorld` from
`software_manufacturing_history.py` -- this module does not re-implement
replay logic, dependency-cone computation, or receipt hashing; it adapts the
existing real object to the real `gymact` protocol.

This is REPLAY mode only (one of the three world modes an "August as a
computational laboratory" architecture would eventually need -- see
`docs/case-studies/august-2026-software-manufacturing-replay.md`'s "Real
GitHub ingestion" section for what's built and what remains a design
program, not implemented here): the trajectory a materialized episode can
take is exactly the admissible-action frontier `ReplayWorld` already
computes from the plan's declared dependency edges. There is no transition
model, no counterfactual branching beyond what the plan's own partial order
already allows, and no execution escalation to a real sandbox/BRCE path --
`requires_authority` defaults to `False` and every capability is a
DO-classified in-memory state advance with zero external side effect,
matching the module's existing `authority: "NONE"` / `do_authority: False`
law verbatim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from gymact.models import Capability, Consequence

from autofde_lab.agent.software_manufacturing_history import ReplayWorld


class ActuationRefused(RuntimeError):
    """Raised when `actuate()` is asked to run a step that is not currently
    admissible from the real current replay state -- never silently allowed
    or silently no-op'd, matching `azuregoat_privesc/gymact_bridge.py`'s
    convention for the same class of refusal.
    """


def _capability_for_step(step: Mapping[str, Any]) -> Capability:
    step_id = str(step["id"])
    kind = str(step.get("kind", "step"))
    intent = str(step.get("intent", step_id))
    return Capability(
        iri=f"urn:gymact:software-manufacturing:capability:{step_id}",
        title=f"{kind}: {intent}",
        consequence=Consequence.DO,
        binding=step_id,
    )


class SoftwareManufacturingEnvironment:
    """One materialized replay episode over one compiled manufacturing plan.

    Wraps a real `ReplayWorld` instance (real dependency-cone-aware admission,
    real deterministic receipt hashing) -- this class adds nothing to that
    logic beyond adapting it to the `gymact.providers.Environment` protocol's
    method names and `Capability`-mediated action vocabulary.
    """

    def __init__(
        self, plan: dict[str, Any], *, requires_authority: bool = False
    ) -> None:
        self.environment_id = (
            f"urn:gymact:software-manufacturing:environment:{uuid4().hex}"
        )
        self.requires_authority = requires_authority
        self._world = ReplayWorld(plan)
        self._capabilities = tuple(
            _capability_for_step(step) for step in self._world._steps()
        )
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("environment is torn down")

    def capabilities(self) -> tuple[Capability, ...]:
        self._ensure_open()
        return self._capabilities

    async def observe(self) -> dict[str, Any]:
        self._ensure_open()
        # ReplayWorld.receipt() is the real, deterministic, hash-carrying
        # summary of this exact trajectory (authority/do_authority/
        # evidence_kind/state/receipt_sha256) -- included here rather than
        # only in a standalone call, because gymact's kernel independently
        # judges verify() against a fresh observe() read (gymact.kernel.
        # GymAct.verify -> DictSubsetVerifier), never against
        # Environment.verify()'s own self-report, so any field a caller
        # wants to `gym.verify(episode_id, {...})` against must live here.
        receipt = self._world.receipt()
        return {
            **receipt,
            "admissible": list(self._world.admissible_actions()),
            "step_count": len(self._world._steps()),
        }

    async def actuate(
        self, capability: Capability, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_open()
        step_id = capability.binding
        agent = str(payload.get("agent", "reference-agent"))
        before = list(self._world.completed)
        try:
            self._world.apply(step_id, agent=agent)
        except ValueError as exc:
            raise ActuationRefused(
                f"refused: {step_id!r} is not admissible from the real current "
                f"state (completed={before!r}): {exc}"
            ) from exc
        return {
            "before": {"completed": before},
            "after": {"completed": list(self._world.completed)},
            "capability": capability.iri,
        }

    async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        self._ensure_open()
        observed = self._world.receipt()
        if expected:
            passed = all(observed.get(key) == value for key, value in expected.items())
        else:
            passed = observed.get("state") == "ALIVE"
        return passed, observed

    async def checkpoint(self) -> dict[str, Any]:
        self._ensure_open()
        return {
            "completed": list(self._world.completed),
            "transitions": [dict(item) for item in self._world.transitions],
        }

    async def restore(self, checkpoint: dict[str, Any]) -> None:
        self._ensure_open()
        completed = checkpoint.get("completed", [])
        transitions = checkpoint.get("transitions", [])
        if not isinstance(completed, list) or not isinstance(transitions, list):
            raise TypeError("checkpoint.completed and .transitions must be arrays")
        self._world.completed = [str(item) for item in completed]
        self._world.transitions = [dict(item) for item in transitions]

    async def teardown(self) -> None:
        # Real, idempotent no-op: a ReplayWorld holds no external resource
        # (no subprocess, no network socket, no filesystem handle) -- matching
        # azuregoat_privesc/gymact_bridge.py's identical teardown rationale.
        self._closed = True


class SoftwareManufacturingProvider:
    """Real `gymact.providers.EnvironmentProvider` that materializes a
    `SoftwareManufacturingEnvironment` from one compiled plan.

    `config["plan"]` accepts either an already-parsed plan `dict` (as
    returned by `compile_history()`) or a path (`str`/`Path`) to a
    `*.plan.json` file compiled by
    `software_manufacturing_history.py compile`.
    """

    name = "software_manufacturing"
    materialization_requires_authority = False

    def __init__(self, *, requires_authority: bool = False) -> None:
        self.requires_authority = requires_authority

    async def materialize(
        self, *, scenario: str | None, config: dict[str, Any]
    ) -> SoftwareManufacturingEnvironment:
        del scenario
        plan = config.get("plan")
        if isinstance(plan, (str, Path)):
            plan = json.loads(Path(plan).read_text())
        if not isinstance(plan, dict):
            raise TypeError(
                "config.plan must be a compiled plan dict or a path to a *.plan.json file"
            )
        configured = config.get("requires_authority", self.requires_authority)
        if not isinstance(configured, bool):
            raise TypeError("config.requires_authority must be a boolean")
        return SoftwareManufacturingEnvironment(plan, requires_authority=configured)
