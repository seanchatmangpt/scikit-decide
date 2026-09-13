# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic rollout and failure containment for cache deployments."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping

from .types import CacheMode

__all__ = [
    "BreakerSnapshot",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "RolloutController",
    "RolloutDecision",
    "RolloutPolicy",
    "RolloutReason",
]


class RolloutReason(str, Enum):
    NORMAL = "normal"
    VERIFY_COHORT = "verify_cohort"
    DISABLED_COHORT = "disabled_cohort"
    KILL_SWITCH = "kill_switch"
    CIRCUIT_OPEN = "circuit_open"
    FORCED = "forced"
    REQUESTED = "requested"


@dataclass(frozen=True)
class RolloutDecision:
    mode: CacheMode
    reason: RolloutReason
    cohort: float | None
    breaker_permitted: bool


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_seconds: float = 30.0
    half_open_max_calls: int = 1

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.recovery_seconds <= 0:
            raise ValueError("recovery_seconds must be positive")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")


@dataclass(frozen=True)
class BreakerSnapshot:
    key: str
    state: CircuitState
    consecutive_failures: int
    opened_at: float | None
    half_open_calls: int


@dataclass
class _BreakerState:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: float | None = None
    half_open_calls: int = 0


class CircuitBreaker:
    """Per-namespace circuit breaker that degrades cache use to bypass."""

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or CircuitBreakerConfig()
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._states: dict[str, _BreakerState] = {}

    def allow(self, key: str) -> bool:
        with self._lock:
            state = self._states.setdefault(key, _BreakerState())
            if state.state is CircuitState.OPEN:
                assert state.opened_at is not None
                if self._monotonic() - state.opened_at >= self.config.recovery_seconds:
                    state.state = CircuitState.HALF_OPEN
                    state.half_open_calls = 0
                else:
                    return False
            if state.state is CircuitState.HALF_OPEN:
                if state.half_open_calls >= self.config.half_open_max_calls:
                    return False
                state.half_open_calls += 1
            return True

    def record_success(self, key: str) -> None:
        with self._lock:
            state = self._states.setdefault(key, _BreakerState())
            state.state = CircuitState.CLOSED
            state.consecutive_failures = 0
            state.opened_at = None
            state.half_open_calls = 0

    def record_failure(self, key: str) -> None:
        with self._lock:
            state = self._states.setdefault(key, _BreakerState())
            state.consecutive_failures += 1
            if (
                state.state is CircuitState.HALF_OPEN
                or state.consecutive_failures >= self.config.failure_threshold
            ):
                state.state = CircuitState.OPEN
                state.opened_at = self._monotonic()
                state.half_open_calls = 0

    def snapshot(self, key: str) -> BreakerSnapshot:
        with self._lock:
            state = self._states.setdefault(key, _BreakerState())
            return BreakerSnapshot(
                key=key,
                state=state.state,
                consecutive_failures=state.consecutive_failures,
                opened_at=state.opened_at,
                half_open_calls=state.half_open_calls,
            )


@dataclass(frozen=True)
class RolloutPolicy:
    """Stable cohort assignment for normal, verify, and bypass operation."""

    enabled_percent: float = 100.0
    verify_percent: float = 0.0
    salt: str = "autofde_lab-cache-rollout-v1"
    kill_switch: bool = False
    forced_modes: Mapping[str, CacheMode] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.enabled_percent <= 100.0:
            raise ValueError("enabled_percent must be in [0, 100]")
        if not 0.0 <= self.verify_percent <= self.enabled_percent:
            raise ValueError("verify_percent must be in [0, enabled_percent]")
        if not self.salt:
            raise ValueError("salt must be non-empty")
        object.__setattr__(
            self,
            "forced_modes",
            MappingProxyType(dict(self.forced_modes)),
        )


class RolloutController:
    """Choose a deterministic mode and honor a per-namespace breaker."""

    def __init__(
        self,
        policy: RolloutPolicy | None = None,
        *,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.policy = policy or RolloutPolicy()
        self.breaker = breaker or CircuitBreaker()

    def cohort(self, identity: str) -> float:
        digest = hashlib.blake2b(
            f"{self.policy.salt}:{identity}".encode("utf-8"),
            digest_size=8,
        ).digest()
        integer = int.from_bytes(digest, "big")
        return integer / float(2**64) * 100.0

    def decide(
        self,
        *,
        identity: str,
        breaker_key: str,
        requested: CacheMode | None = None,
    ) -> RolloutDecision:
        if self.policy.kill_switch:
            return RolloutDecision(
                mode=CacheMode.BYPASS,
                reason=RolloutReason.KILL_SWITCH,
                cohort=None,
                breaker_permitted=True,
            )
        if not self.breaker.allow(breaker_key):
            return RolloutDecision(
                mode=CacheMode.BYPASS,
                reason=RolloutReason.CIRCUIT_OPEN,
                cohort=None,
                breaker_permitted=False,
            )
        forced = self.policy.forced_modes.get(identity)
        if forced is not None:
            return RolloutDecision(
                mode=forced,
                reason=RolloutReason.FORCED,
                cohort=None,
                breaker_permitted=True,
            )
        if requested is not None and requested is not CacheMode.NORMAL:
            return RolloutDecision(
                mode=requested,
                reason=RolloutReason.REQUESTED,
                cohort=None,
                breaker_permitted=True,
            )
        cohort = self.cohort(identity)
        if cohort >= self.policy.enabled_percent:
            return RolloutDecision(
                mode=CacheMode.BYPASS,
                reason=RolloutReason.DISABLED_COHORT,
                cohort=cohort,
                breaker_permitted=True,
            )
        if cohort < self.policy.verify_percent:
            return RolloutDecision(
                mode=CacheMode.VERIFY,
                reason=RolloutReason.VERIFY_COHORT,
                cohort=cohort,
                breaker_permitted=True,
            )
        return RolloutDecision(
            mode=CacheMode.NORMAL,
            reason=RolloutReason.NORMAL,
            cohort=cohort,
            breaker_permitted=True,
        )

    def mode_for(
        self,
        *,
        identity: str,
        breaker_key: str,
        requested: CacheMode | None = None,
    ) -> CacheMode:
        return self.decide(
            identity=identity,
            breaker_key=breaker_key,
            requested=requested,
        ).mode
