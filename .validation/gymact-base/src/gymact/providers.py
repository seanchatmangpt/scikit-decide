"""Environment/provider contracts and a deterministic reference gym."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from gymact.models import Capability, Consequence


@runtime_checkable
class Environment(Protocol):
    """Materialized bounded world exposed to GymAct."""

    environment_id: str
    requires_authority: bool

    def capabilities(self) -> tuple[Capability, ...]: ...

    async def observe(self) -> dict[str, Any]: ...

    async def actuate(self, capability: Capability, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]: ...

    async def checkpoint(self) -> dict[str, Any]: ...

    async def restore(self, checkpoint: dict[str, Any]) -> None: ...

    async def teardown(self) -> None: ...


@runtime_checkable
class EnvironmentProvider(Protocol):
    """Factory for materialized environment instances."""

    name: str
    materialization_requires_authority: bool

    async def materialize(self, *, scenario: str | None, config: dict[str, Any]) -> Environment: ...


MEMORY_CAPABILITIES = (
    Capability(
        iri="urn:gymact:memory:capability:set",
        title="Set a value in the bounded memory world",
        consequence=Consequence.DO,
        binding="set",
    ),
    Capability(
        iri="urn:gymact:memory:capability:delete",
        title="Delete a value from the bounded memory world",
        consequence=Consequence.DO,
        binding="delete",
    ),
    Capability(
        iri="urn:gymact:memory:capability:increment",
        title="Increment a numeric value in the bounded memory world",
        consequence=Consequence.DO,
        binding="increment",
    ),
)


class MemoryEnvironment:
    """Deterministic executable reference world used for contract validation."""

    def __init__(
        self, *, initial: dict[str, Any] | None = None, requires_authority: bool = False
    ) -> None:
        self.environment_id = f"urn:gymact:memory:environment:{uuid4().hex}"
        self.requires_authority = requires_authority
        self._state: dict[str, Any] = deepcopy(initial or {})
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("environment is torn down")

    def capabilities(self) -> tuple[Capability, ...]:
        self._ensure_open()
        return MEMORY_CAPABILITIES

    async def observe(self) -> dict[str, Any]:
        self._ensure_open()
        return deepcopy(self._state)

    async def actuate(self, capability: Capability, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_open()
        before = deepcopy(self._state)
        binding = capability.binding
        if binding == "set":
            key = str(payload["key"])
            self._state[key] = deepcopy(payload.get("value"))
        elif binding == "delete":
            key = str(payload["key"])
            self._state.pop(key, None)
        elif binding == "increment":
            key = str(payload["key"])
            amount = payload.get("amount", 1)
            current = self._state.get(key, 0)
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                raise TypeError("increment requires a numeric current value")
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                raise TypeError("increment requires a numeric amount")
            self._state[key] = current + amount
        else:
            raise ValueError(f"unsupported provider binding: {binding}")
        return {
            "before": before,
            "after": deepcopy(self._state),
            "capability": capability.iri,
        }

    async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        self._ensure_open()
        observed = await self.observe()
        passed = all(observed.get(key) == value for key, value in expected.items())
        return passed, observed

    async def checkpoint(self) -> dict[str, Any]:
        self._ensure_open()
        return deepcopy(self._state)

    async def restore(self, checkpoint: dict[str, Any]) -> None:
        self._ensure_open()
        self._state = deepcopy(checkpoint)

    async def teardown(self) -> None:
        self._closed = True


class MemoryProvider:
    """Reference provider that materializes isolated in-memory worlds."""

    name = "memory"
    materialization_requires_authority = False

    def __init__(self, *, requires_authority: bool = False) -> None:
        self.requires_authority = requires_authority

    async def materialize(
        self, *, scenario: str | None, config: dict[str, Any]
    ) -> MemoryEnvironment:
        del scenario
        initial = config.get("initial", {})
        if not isinstance(initial, dict):
            raise TypeError("config.initial must be an object")
        configured = config.get("requires_authority", False)
        if not isinstance(configured, bool):
            raise TypeError("config.requires_authority must be a boolean")
        required = self.requires_authority or configured
        return MemoryEnvironment(initial=initial, requires_authority=required)
