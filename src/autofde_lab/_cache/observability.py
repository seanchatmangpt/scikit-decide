# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Receipt fanout and rolling SLO evaluation."""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable

__all__ = [
    "ObserverFailurePolicy",
    "ReceiptFanout",
    "SLOSnapshot",
    "SLOTargets",
    "SLOTracker",
]


class ObserverFailurePolicy(str, Enum):
    IGNORE = "ignore"
    COLLECT = "collect"
    RAISE = "raise"


class ReceiptFanout:
    """Compose receipt sinks with an explicit observer failure policy."""

    def __init__(
        self,
        sinks: Iterable[Callable[[Any], None]] = (),
        *,
        failure_policy: ObserverFailurePolicy = ObserverFailurePolicy.COLLECT,
        max_errors: int = 100,
    ) -> None:
        if max_errors < 1:
            raise ValueError("max_errors must be at least 1")
        self._sinks = tuple(sinks)
        self.failure_policy = failure_policy
        self._errors: deque[str] = deque(maxlen=max_errors)
        self._lock = threading.RLock()

    def __call__(self, receipt: Any) -> None:
        for sink in self._sinks:
            try:
                sink(receipt)
            except Exception as error:
                if self.failure_policy is ObserverFailurePolicy.RAISE:
                    raise
                if self.failure_policy is ObserverFailurePolicy.COLLECT:
                    with self._lock:
                        self._errors.append(f"{type(error).__name__}: {error}")

    def errors(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._errors)


@dataclass(frozen=True)
class SLOTargets:
    minimum_hit_rate: float = 0.70
    maximum_error_rate: float = 0.01
    maximum_p95_load_ms: float = 20.0
    maximum_p95_compute_ms: float = 1000.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_hit_rate <= 1.0:
            raise ValueError("minimum_hit_rate must be in [0, 1]")
        if not 0.0 <= self.maximum_error_rate <= 1.0:
            raise ValueError("maximum_error_rate must be in [0, 1]")
        if self.maximum_p95_load_ms < 0:
            raise ValueError("maximum_p95_load_ms cannot be negative")
        if self.maximum_p95_compute_ms < 0:
            raise ValueError("maximum_p95_compute_ms cannot be negative")


@dataclass(frozen=True)
class SLOSnapshot:
    samples: int
    hit_rate: float
    error_rate: float
    p95_load_ms: float
    p95_compute_ms: float
    compliant: bool
    violations: tuple[str, ...]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


class SLOTracker:
    """Evaluate service-level objectives over a bounded receipt window."""

    _HITS = {"hit_l1", "hit_l2", "verified_hit", "stale_if_error"}
    _ERRORS = {"refused"}

    def __init__(
        self,
        targets: SLOTargets | None = None,
        *,
        window_size: int = 10_000,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size must be at least 1")
        self.targets = targets or SLOTargets()
        self._receipts: deque[Any] = deque(maxlen=window_size)
        self._lock = threading.RLock()

    def observe(self, receipt: Any) -> None:
        with self._lock:
            self._receipts.append(receipt)

    __call__ = observe

    def snapshot(self) -> SLOSnapshot:
        with self._lock:
            receipts = tuple(self._receipts)
        if not receipts:
            return SLOSnapshot(
                samples=0,
                hit_rate=0.0,
                error_rate=0.0,
                p95_load_ms=0.0,
                p95_compute_ms=0.0,
                compliant=False,
                violations=("no receipt samples",),
            )
        dispositions = []
        load_ms = []
        compute_ms = []
        errors = 0
        for receipt in receipts:
            disposition = getattr(receipt, "disposition", "")
            value = getattr(disposition, "value", disposition)
            dispositions.append(str(value))
            load_ms.append(float(getattr(receipt, "load_ns", 0)) / 1_000_000)
            compute_ms.append(float(getattr(receipt, "compute_ns", 0)) / 1_000_000)
            if str(value) in self._ERRORS or getattr(receipt, "error_type", None):
                errors += 1
        samples = len(receipts)
        hit_rate = sum(value in self._HITS for value in dispositions) / samples
        error_rate = errors / samples
        p95_load = _percentile(load_ms, 0.95)
        p95_compute = _percentile(compute_ms, 0.95)
        violations = []
        if hit_rate < self.targets.minimum_hit_rate:
            violations.append(
                f"hit rate {hit_rate:.4f} below {self.targets.minimum_hit_rate:.4f}"
            )
        if error_rate > self.targets.maximum_error_rate:
            violations.append(
                f"error rate {error_rate:.4f} above "
                f"{self.targets.maximum_error_rate:.4f}"
            )
        if p95_load > self.targets.maximum_p95_load_ms:
            violations.append(
                f"p95 load {p95_load:.3f}ms above "
                f"{self.targets.maximum_p95_load_ms:.3f}ms"
            )
        if p95_compute > self.targets.maximum_p95_compute_ms:
            violations.append(
                f"p95 compute {p95_compute:.3f}ms above "
                f"{self.targets.maximum_p95_compute_ms:.3f}ms"
            )
        return SLOSnapshot(
            samples=samples,
            hit_rate=hit_rate,
            error_rate=error_rate,
            p95_load_ms=p95_load,
            p95_compute_ms=p95_compute,
            compliant=not violations,
            violations=tuple(violations),
        )
