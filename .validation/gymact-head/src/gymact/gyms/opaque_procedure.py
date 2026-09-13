"""Leakage-resistant bounded world for black-box procedure discovery.

The provider receives a private transition model at materialization time. The
materialized environment exposes only an observed fact set and opaque DO
capabilities. Preconditions, effects, source provenance, recipe ordering and
human-readable step descriptions never cross the environment boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4

from gymact.models import Capability, Consequence


def _as_fact_set(value: object, field: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{field} must be a list of strings")
    return frozenset(value)


@dataclass(frozen=True)
class _HiddenStep:
    opaque_id: str
    preconditions: frozenset[str]
    establishes: frozenset[str]
    removes: frozenset[str]


def _opaque_id(*, subject: str, step_id: str) -> str:
    token = sha256(f"gymact-opaque-v1\0{subject}\0{step_id}".encode()).hexdigest()[:20]
    return f"urn:gymact:opaque:action:{token}"


class OpaqueProcedureEnvironment:
    """Deterministic black-box world whose action model remains provider-private."""

    def __init__(
        self,
        *,
        subject: str,
        initial_facts: frozenset[str],
        goal_facts: frozenset[str],
        hidden_steps: tuple[_HiddenStep, ...],
        requires_authority: bool,
    ) -> None:
        self.environment_id = f"urn:gymact:opaque:environment:{uuid4().hex}"
        self.requires_authority = requires_authority
        self.subject = subject
        self._goal_facts = goal_facts
        self._state = set(initial_facts)
        self._steps = {step.opaque_id: step for step in hidden_steps}
        self._capabilities = tuple(
            Capability(
                iri=step.opaque_id,
                title="Opaque consequential action",
                consequence=Consequence.DO,
                binding=step.opaque_id,
            )
            for step in sorted(hidden_steps, key=lambda item: item.opaque_id)
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
        return {"facts": sorted(self._state)}

    async def actuate(
        self, capability: Capability, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_open()
        if payload:
            raise ValueError("OPAQUE_ACTION_ACCEPTS_NO_PAYLOAD")
        step = self._steps.get(capability.binding)
        if step is None:
            raise ValueError("UNKNOWN_OPAQUE_ACTION")
        if not step.preconditions <= self._state:
            raise ValueError("PRECONDITION_REFUSED")
        if step.establishes <= self._state and not (step.removes & self._state):
            raise ValueError("ALREADY_SATISFIED_REFUSED")
        before = sorted(self._state)
        self._state.difference_update(step.removes)
        self._state.update(step.establishes)
        return {
            "action": step.opaque_id,
            "before_facts": before,
            "after_facts": sorted(self._state),
        }

    async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        self._ensure_open()
        observed = await self.observe()
        allowed = {"facts_include", "facts_equal", "goal_reached"}
        unknown = set(expected) - allowed
        if unknown:
            raise ValueError(f"UNSUPPORTED_OPAQUE_VERIFICATION:{sorted(unknown)!r}")
        passed = True
        if "facts_include" in expected:
            required = _as_fact_set(expected["facts_include"], "expected.facts_include")
            passed = passed and required <= self._state
        if "facts_equal" in expected:
            exact = _as_fact_set(expected["facts_equal"], "expected.facts_equal")
            passed = passed and exact == self._state
        if "goal_reached" in expected:
            if not isinstance(expected["goal_reached"], bool):
                raise TypeError("expected.goal_reached must be a boolean")
            reached = self._goal_facts <= self._state
            passed = passed and reached is expected["goal_reached"]
        return passed, observed

    async def checkpoint(self) -> dict[str, Any]:
        self._ensure_open()
        return {"facts": sorted(self._state)}

    async def restore(self, checkpoint: dict[str, Any]) -> None:
        self._ensure_open()
        facts = _as_fact_set(checkpoint.get("facts"), "checkpoint.facts")
        self._state = set(facts)

    async def teardown(self) -> None:
        self._closed = True


class OpaqueProcedureProvider:
    """Materialize a hidden transition model while exposing only opaque actions."""

    name = "opaque-procedure"
    materialization_requires_authority = False

    async def materialize(
        self, *, scenario: str | None, config: dict[str, Any]
    ) -> OpaqueProcedureEnvironment:
        del scenario
        subject = config.get("subject")
        if not isinstance(subject, str) or not subject:
            raise TypeError("config.subject must be a non-empty string")
        initial_facts = _as_fact_set(config.get("initial_facts"), "config.initial_facts")
        goal_facts = _as_fact_set(config.get("goal_facts"), "config.goal_facts")
        raw_steps = config.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise TypeError("config.steps must be a non-empty list")
        hidden_steps: list[_HiddenStep] = []
        opaque_ids: set[str] = set()
        for index, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                raise TypeError(f"config.steps[{index}] must be an object")
            step_id = raw.get("id")
            if not isinstance(step_id, str) or not step_id:
                raise TypeError(f"config.steps[{index}].id must be a non-empty string")
            opaque_id = _opaque_id(subject=subject, step_id=step_id)
            if opaque_id in opaque_ids:
                raise ValueError("DUPLICATE_OPAQUE_ACTION")
            opaque_ids.add(opaque_id)
            hidden_steps.append(
                _HiddenStep(
                    opaque_id=opaque_id,
                    preconditions=_as_fact_set(
                        raw.get("preconditions", []), f"config.steps[{index}].preconditions"
                    ),
                    establishes=_as_fact_set(
                        raw.get("establishes", []), f"config.steps[{index}].establishes"
                    ),
                    removes=_as_fact_set(
                        raw.get("removes", []), f"config.steps[{index}].removes"
                    ),
                )
            )
        requires_authority = config.get("requires_authority", False)
        if not isinstance(requires_authority, bool):
            raise TypeError("config.requires_authority must be a boolean")
        return OpaqueProcedureEnvironment(
            subject=subject,
            initial_facts=initial_facts,
            goal_facts=goal_facts,
            hidden_steps=tuple(hidden_steps),
            requires_authority=requires_authority,
        )
