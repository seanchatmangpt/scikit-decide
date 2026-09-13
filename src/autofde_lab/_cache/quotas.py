# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Thread-safe multi-tenant quotas for shared cache fabrics."""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator

__all__ = [
    "QuotaExceededError",
    "QuotaManager",
    "QuotaSnapshot",
    "QuotaSpec",
]


class QuotaExceededError(RuntimeError):
    """Raised when a tenant exceeds an admitted resource envelope."""


@dataclass(frozen=True)
class QuotaSpec:
    """Independent fair-use limits for one tenant."""

    requests_per_second: float = 1000.0
    burst: int = 2000
    max_concurrent: int = 64
    max_inflight_estimated_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.burst < 1:
            raise ValueError("burst must be at least 1")
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if self.max_inflight_estimated_bytes < 0:
            raise ValueError("max_inflight_estimated_bytes cannot be negative")


@dataclass(frozen=True)
class QuotaSnapshot:
    tenant: str
    available_tokens: float
    concurrent: int
    inflight_estimated_bytes: int
    admitted: int
    refused_rate: int
    refused_concurrency: int
    refused_bytes: int


@dataclass
class _TenantState:
    spec: QuotaSpec
    tokens: float
    last_refill: float
    concurrent: int = 0
    inflight_bytes: int = 0
    admitted: int = 0
    refused_rate: int = 0
    refused_concurrency: int = 0
    refused_bytes: int = 0


class QuotaManager:
    """Fail-fast token-bucket and concurrency admission by tenant."""

    def __init__(
        self,
        default_spec: QuotaSpec | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.default_spec = default_spec or QuotaSpec()
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._states: dict[str, _TenantState] = {}
        self._overrides: dict[str, QuotaSpec] = {}

    def register(self, tenant: str, spec: QuotaSpec) -> None:
        if not tenant:
            raise ValueError("tenant must be non-empty")
        with self._lock:
            self._overrides[tenant] = spec
            state = self._states.get(tenant)
            if state is not None:
                state.spec = spec
                state.tokens = min(state.tokens, float(spec.burst))

    def _state(self, tenant: str) -> _TenantState:
        state = self._states.get(tenant)
        if state is None:
            spec = self._overrides.get(tenant, self.default_spec)
            state = _TenantState(
                spec=spec,
                tokens=float(spec.burst),
                last_refill=self._monotonic(),
            )
            self._states[tenant] = state
        return state

    def _refill(self, state: _TenantState, now: float) -> None:
        elapsed = max(0.0, now - state.last_refill)
        state.tokens = min(
            float(state.spec.burst),
            state.tokens + elapsed * state.spec.requests_per_second,
        )
        state.last_refill = now

    @contextlib.contextmanager
    def admit(
        self,
        tenant: str,
        *,
        estimated_bytes: int = 0,
    ) -> Iterator[QuotaSnapshot]:
        if not tenant:
            raise ValueError("tenant must be non-empty")
        if estimated_bytes < 0:
            raise ValueError("estimated_bytes cannot be negative")
        with self._lock:
            state = self._state(tenant)
            self._refill(state, self._monotonic())
            if state.tokens < 1.0:
                state.refused_rate += 1
                raise QuotaExceededError(f"tenant request rate exceeded: {tenant}")
            if state.concurrent >= state.spec.max_concurrent:
                state.refused_concurrency += 1
                raise QuotaExceededError(f"tenant concurrency exceeded: {tenant}")
            projected = state.inflight_bytes + estimated_bytes
            if projected > state.spec.max_inflight_estimated_bytes:
                state.refused_bytes += 1
                raise QuotaExceededError(
                    f"tenant inflight byte estimate exceeded: {tenant}"
                )
            state.tokens -= 1.0
            state.concurrent += 1
            state.inflight_bytes = projected
            state.admitted += 1
            snapshot = self._snapshot_unlocked(tenant, state)
        try:
            yield snapshot
        finally:
            with self._lock:
                state.concurrent -= 1
                state.inflight_bytes -= estimated_bytes

    def _snapshot_unlocked(
        self,
        tenant: str,
        state: _TenantState,
    ) -> QuotaSnapshot:
        return QuotaSnapshot(
            tenant=tenant,
            available_tokens=state.tokens,
            concurrent=state.concurrent,
            inflight_estimated_bytes=state.inflight_bytes,
            admitted=state.admitted,
            refused_rate=state.refused_rate,
            refused_concurrency=state.refused_concurrency,
            refused_bytes=state.refused_bytes,
        )

    def snapshot(self, tenant: str) -> QuotaSnapshot:
        with self._lock:
            state = self._state(tenant)
            self._refill(state, self._monotonic())
            return self._snapshot_unlocked(tenant, state)

    def snapshots(self) -> tuple[QuotaSnapshot, ...]:
        with self._lock:
            now = self._monotonic()
            results = []
            for tenant, state in sorted(self._states.items()):
                self._refill(state, now)
                results.append(self._snapshot_unlocked(tenant, state))
            return tuple(results)
