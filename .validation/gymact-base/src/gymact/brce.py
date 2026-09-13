"""BRCE production DO port: candidate -> admitted grant -> verified consequence."""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from gymact.action_contract import ActionDefinition, ExecutionGrant, PreparedAction
from gymact.crown_runtime import VerifiedTransition, execute_admitted
from gymact.models import FrozenModel
from gymact.runtime import _PRODUCTION_BRCE_SEAL


class BrokerRuntime(Protocol):
    async def act(self, intent: Any) -> Any: ...

    async def verify(self, episode_id: str, expected: dict[str, Any]) -> Any: ...

    def _record(self, receipt: Any) -> Any: ...


class BrokerRequest(FrozenModel):
    action: ActionDefinition
    prepared: PreparedAction
    grant: ExecutionGrant
    current_revision: str | None = None
    expected: dict[str, Any] = Field(default_factory=dict)


class _BrokerRuntimeView:
    """Give Crown runtime only the DO port admitted for broker execution."""

    def __init__(self, runtime: BrokerRuntime) -> None:
        self._runtime = runtime

    async def act(self, intent: Any) -> Any:
        admitted = getattr(self._runtime, "_act_from_brce", None)
        if admitted is not None:
            return await admitted(intent, seal=_PRODUCTION_BRCE_SEAL)
        return await self._runtime.act(intent)

    async def verify(self, episode_id: str, expected: dict[str, Any]) -> Any:
        return await self._runtime.verify(episode_id, expected)

    def _record(self, receipt: Any) -> Any:
        return self._runtime._record(receipt)


class BRCEBroker:
    """Exclusive production-oriented DO facade.

    The broker exposes no raw ``act`` method. It accepts only a prepared candidate and
    an identity-bound ExecutionGrant, runs mechanical admission, delegates provider
    consequence through the sealed production DO port, and returns independently
    verified standing.
    """

    def __init__(self, runtime: BrokerRuntime) -> None:
        self._runtime = runtime
        self._view = _BrokerRuntimeView(runtime)

    async def execute(self, request: BrokerRequest) -> VerifiedTransition:
        return await execute_admitted(
            self._view,
            request.action,
            request.prepared,
            request.grant,
            current_revision=request.current_revision,
            expected=request.expected,
        )
