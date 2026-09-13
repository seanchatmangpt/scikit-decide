# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Public types and admission policy for the scikit-decide cache fabric."""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

__all__ = [
    "CONSTANT_CAPABILITY_METHODS",
    "MODEL_CAPABILITY_METHODS",
    "SCHEDULING_CAPABILITY_METHODS",
    "UNSAFE_CAPABILITY_METHODS",
    "CacheAdmissionError",
    "CacheConfig",
    "CacheCorruptionError",
    "CacheDisposition",
    "CacheInfo",
    "CacheKey",
    "CacheLeaseTimeoutError",
    "CacheMode",
    "CachePolicy",
    "CacheReceipt",
    "CacheRecord",
    "CacheResult",
    "MethodPolicy",
    "UnhashableCacheKeyError",
    "UnsafeCacheMethodError",
]

KeyFunction = Callable[[tuple[Any, ...], Mapping[str, Any]], Any]
TagFunction = Callable[[tuple[Any, ...], Mapping[str, Any]], tuple[str, ...]]

CONSTANT_CAPABILITY_METHODS = frozenset(
    {
        "get_action_space",
        "get_constraints",
        "get_goals",
        "get_initial_state",
        "get_initial_state_distribution",
        "get_memory_maxlen",
        "get_observation_space",
        "is_transition_value_dependent_on_next_state",
    }
)

MODEL_CAPABILITY_METHODS = CONSTANT_CAPABILITY_METHODS | frozenset(
    {
        "get_action_mask",
        "get_applicable_actions",
        "get_enabled_events",
        "get_next_state",
        "get_next_state_distribution",
        "get_observation",
        "get_observation_distribution",
        "get_transition_value",
        "is_action",
        "is_applicable_action",
        "is_enabled_event",
        "is_goal",
        "is_observation",
        "is_terminal",
    }
)

SCHEDULING_CAPABILITY_METHODS = frozenset(
    {
        "all_tasks_possible",
        "check_if_skills_are_fulfilled",
        "check_unique_resource_names",
        "find_one_ressource_to_do_one_task",
        "get_all_resources_skills",
        "get_all_tasks_skills",
        "get_mode_costs",
        "get_non_zero_ressource_need_names",
        "get_original_quantity_resource",
        "get_preallocations",
        "get_predecessors",
        "get_predecessors_task",
        "get_quantity_resource",
        "get_resource_cost_per_time_unit",
        "get_resource_need",
        "get_resource_need_at_time",
        "get_resource_renewability",
        "get_resource_type_for_unit",
        "get_resource_types_names",
        "get_resource_units_names",
        "get_ressource_names",
        "get_ressource_names_for_task_mode",
        "get_skills_names",
        "get_skills_of_resource",
        "get_skills_of_task",
        "get_successors",
        "get_successors_task",
        "get_task_consumption",
        "get_task_duration",
        "get_task_duration_distribution",
        "get_task_duration_lower_bound",
        "get_task_duration_upper_bound",
        "get_task_modes",
        "get_task_paused_non_renewable_resource_returned",
        "get_task_preemptivity",
        "get_task_resuming_type",
        "get_tasks_ids",
        "get_tasks_mode",
        "get_tasks_modes",
        "get_time_lags",
        "get_time_window",
        "is_renewable",
        "task_modes_possible_to_launch",
        "task_possible_to_launch_precedence",
    }
)

UNSAFE_CAPABILITY_METHODS = frozenset(
    {
        "close",
        "compute_graph",
        "get_latest_sampled_duration",
        "render",
        "reset",
        "sample",
        "sample_quantity_resource",
        "sample_task_duration",
        "set_memory",
        "step",
    }
)

_EXPLICIT_MEMORY_METHODS = frozenset(
    {
        "get_action_mask",
        "get_applicable_actions",
        "get_enabled_events",
        "is_applicable_action",
        "is_enabled_event",
    }
)


class CacheAdmissionError(ValueError):
    """Raised when a cache subject or operation is not lawfully admitted."""


class UnsafeCacheMethodError(CacheAdmissionError):
    """Raised when a policy admits a stateful, stochastic, or side-effecting call."""


class UnhashableCacheKeyError(TypeError):
    """Raised when an input lacks a deterministic canonical representation."""


class CacheCorruptionError(RuntimeError):
    """Raised when a persisted payload fails its content digest."""


class CacheLeaseTimeoutError(TimeoutError):
    """Raised when another process holds a compute lease past the wait bound."""


class CacheMode(str, Enum):
    """Per-call execution mode."""

    NORMAL = "normal"
    REFRESH = "refresh"
    BYPASS = "bypass"
    VERIFY = "verify"
    READ_ONLY = "read_only"


class CacheDisposition(str, Enum):
    """Observed result of a cache operation."""

    HIT_L1 = "hit_l1"
    HIT_L2 = "hit_l2"
    MISS_STORED = "miss_stored"
    MISS_UNSTORED = "miss_unstored"
    STALE_IF_ERROR = "stale_if_error"
    BYPASS = "bypass"
    READ_ONLY_MISS = "read_only_miss"
    VERIFIED_HIT = "verified_hit"
    REFUSED = "refused"


@dataclass(frozen=True)
class MethodPolicy:
    """Admission and lifecycle policy for one deterministic operation."""

    version: str = "1"
    ttl_seconds: float | None = None
    stale_if_error_seconds: float = 0.0
    cache_none: bool = True
    single_flight: bool = True
    cross_process_single_flight: bool = True
    copy_on_read: bool = True
    key_fn: KeyFunction | None = None
    tag_fn: TagFunction | None = None
    static_tags: tuple[str, ...] = ()
    requires_explicit_arguments: frozenset[str] = frozenset()
    on_unhashable: Literal["bypass", "raise"] = "bypass"
    lease_seconds: float = 60.0
    lease_wait_seconds: float = 65.0
    lease_poll_seconds: float = 0.025
    lease_timeout: Literal["compute", "raise"] = "compute"

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("method policy version must be non-empty")
        if self.ttl_seconds is not None and self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive or None")
        if self.stale_if_error_seconds < 0:
            raise ValueError("stale_if_error_seconds cannot be negative")
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if self.lease_wait_seconds < 0:
            raise ValueError("lease_wait_seconds cannot be negative")
        if self.lease_poll_seconds <= 0:
            raise ValueError("lease_poll_seconds must be positive")
        if self.on_unhashable not in {"bypass", "raise"}:
            raise ValueError("on_unhashable must be 'bypass' or 'raise'")
        if self.lease_timeout not in {"compute", "raise"}:
            raise ValueError("lease_timeout must be 'compute' or 'raise'")
        object.__setattr__(
            self,
            "requires_explicit_arguments",
            frozenset(self.requires_explicit_arguments),
        )
        object.__setattr__(self, "static_tags", tuple(self.static_tags))


@dataclass(frozen=True)
class CachePolicy:
    """Explicit allow-list and method policy map.

    The compatibility fields ``max_entries``, ``ttl_seconds``, ``single_flight``,
    ``cache_none``, and ``on_unhashable`` remain accepted. Resource capacity is
    ultimately owned by :class:`CacheConfig`; these fields configure the default
    in-memory fabric created by ``cache_domain``.
    """

    methods: frozenset[str]
    max_entries: int = 4096
    ttl_seconds: float | None = None
    single_flight: bool = True
    cache_none: bool = True
    on_unhashable: Literal["bypass", "raise"] = "bypass"
    method_policies: Mapping[str, MethodPolicy] = field(default_factory=dict)
    default_version: str = "1"

    def __post_init__(self) -> None:
        methods = frozenset(self.methods)
        object.__setattr__(self, "methods", methods)
        object.__setattr__(self, "method_policies", dict(self.method_policies))
        if self.max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        malformed = {m for m in methods if not isinstance(m, str) or not m}
        private = {m for m in methods if isinstance(m, str) and m.startswith("_")}
        sampling = {m for m in methods if isinstance(m, str) and m.startswith("sample")}
        refused = (methods & UNSAFE_CAPABILITY_METHODS) | sampling
        if malformed:
            raise ValueError(
                f"cache method names must be non-empty strings: {malformed!r}"
            )
        if private or refused:
            names = sorted(private | refused)
            raise UnsafeCacheMethodError(
                "stateful, stochastic, side-effecting, and private methods cannot be "
                f"cached: {', '.join(names)}"
            )
        unknown_overrides = set(self.method_policies) - methods
        if unknown_overrides:
            raise ValueError(
                "method_policies contains methods outside the allow-list: "
                f"{sorted(unknown_overrides)!r}"
            )
        if self.ttl_seconds is not None and self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive or None")
        if self.on_unhashable not in {"bypass", "raise"}:
            raise ValueError("on_unhashable must be 'bypass' or 'raise'")

    def policy_for(self, method: str) -> MethodPolicy:
        override = self.method_policies.get(method)
        if override is not None:
            return override
        explicit = (
            frozenset({"memory"}) if method in _EXPLICIT_MEMORY_METHODS else frozenset()
        )
        return MethodPolicy(
            version=self.default_version,
            ttl_seconds=self.ttl_seconds,
            cache_none=self.cache_none,
            single_flight=self.single_flight,
            on_unhashable=self.on_unhashable,
            requires_explicit_arguments=explicit,
        )

    @classmethod
    def constants(cls, **kwargs: Any) -> "CachePolicy":
        return cls(methods=CONSTANT_CAPABILITY_METHODS, **kwargs)

    @classmethod
    def model(cls, **kwargs: Any) -> "CachePolicy":
        return cls(methods=MODEL_CAPABILITY_METHODS, **kwargs)

    @classmethod
    def scheduling(cls, **kwargs: Any) -> "CachePolicy":
        return cls(
            methods=MODEL_CAPABILITY_METHODS | SCHEDULING_CAPABILITY_METHODS,
            **kwargs,
        )

    @classmethod
    def custom(cls, *methods: str, **kwargs: Any) -> "CachePolicy":
        return cls(methods=frozenset(methods), **kwargs)

    def with_methods(self, *methods: str) -> "CachePolicy":
        return dataclasses.replace(self, methods=self.methods | frozenset(methods))

    def without_methods(self, *methods: str) -> "CachePolicy":
        removed = frozenset(methods)
        overrides = {k: v for k, v in self.method_policies.items() if k not in removed}
        return dataclasses.replace(
            self,
            methods=self.methods - removed,
            method_policies=overrides,
        )

    def with_method_policy(self, method: str, policy: MethodPolicy) -> "CachePolicy":
        if method not in self.methods:
            raise ValueError(f"method is not admitted: {method}")
        overrides = dict(self.method_policies)
        overrides[method] = policy
        return dataclasses.replace(self, method_policies=overrides)


@dataclass(frozen=True)
class CacheConfig:
    """Resource and persistence configuration for a cache fabric."""

    memory_max_entries: int = 4096
    memory_max_bytes: int = 64 * 1024 * 1024
    protected_ratio: float = 0.8
    persistent_path: Path | str | None = None
    persistent_max_bytes: int = 4 * 1024 * 1024 * 1024
    compression_threshold_bytes: int = 4096
    sqlite_busy_timeout_ms: int = 5000
    sqlite_touch_interval_seconds: float = 5.0
    receipt_history: int = 1024
    digest_algorithm: Literal["blake2b", "sha256", "blake3"] = "blake2b"

    def __post_init__(self) -> None:
        if self.memory_max_entries < 1:
            raise ValueError("memory_max_entries must be at least 1")
        if self.memory_max_bytes < 1:
            raise ValueError("memory_max_bytes must be at least 1")
        if not 0 < self.protected_ratio < 1:
            raise ValueError("protected_ratio must be between 0 and 1")
        if self.persistent_max_bytes < 1:
            raise ValueError("persistent_max_bytes must be at least 1")
        if self.compression_threshold_bytes < 0:
            raise ValueError("compression_threshold_bytes cannot be negative")
        if self.receipt_history < 1:
            raise ValueError("receipt_history must be at least 1")
        if self.digest_algorithm not in {"blake2b", "sha256", "blake3"}:
            raise ValueError("unsupported digest algorithm")
        if self.persistent_path is not None:
            object.__setattr__(self, "persistent_path", Path(self.persistent_path))


@dataclass(frozen=True)
class CacheKey:
    """Content-addressed identity for one admitted computation."""

    digest: str
    algorithm: str
    namespace: str
    method: str
    version: str
    canonical_size: int


@dataclass(frozen=True)
class CacheRecord:
    """Encoded value plus lifecycle and receipt metadata."""

    key: CacheKey
    value_digest: str
    payload: bytes
    codec: str
    compressed: bool
    created_at: float
    expires_at: float | None
    stale_until: float | None
    size_bytes: int
    raw_size_bytes: int
    tags: tuple[str, ...] = ()
    compute_ns: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def is_fresh(self, now: float) -> bool:
        return self.expires_at is None or now < self.expires_at

    def is_stale_servable(self, now: float) -> bool:
        return self.stale_until is not None and now < self.stale_until


@dataclass(frozen=True)
class CacheReceipt:
    """Replayable evidence emitted for each cache decision."""

    key_digest: str
    value_digest: str | None
    namespace: str
    method: str
    version: str
    disposition: CacheDisposition
    tier: str | None
    observed_at: float
    created_at: float | None
    expires_at: float | None
    compute_ns: int
    load_ns: int
    size_bytes: int
    owner: str
    verified: bool = False
    error_type: str | None = None
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["disposition"] = self.disposition.value
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CacheResult:
    """A decoded value paired with its cache receipt."""

    value: Any
    receipt: CacheReceipt


@dataclass(frozen=True)
class CacheInfo:
    """Aggregated cache counters across one or more tiers."""

    hits: int = 0
    misses: int = 0
    waits: int = 0
    stores: int = 0
    evictions: int = 0
    expirations: int = 0
    bypasses: int = 0
    errors: int = 0
    invalidations: int = 0
    currsize: int = 0
    maxsize: int = 0
    l1_hits: int = 0
    l2_hits: int = 0
    stale_hits: int = 0
    refusals: int = 0
    corruptions: int = 0
    promotions: int = 0
    lease_contentions: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    compute_ns: int = 0

    @property
    def hit_rate(self) -> float:
        denominator = self.hits + self.misses
        return self.hits / denominator if denominator else 0.0

    def plus(self, other: "CacheInfo") -> "CacheInfo":
        values = {
            field.name: getattr(self, field.name) + getattr(other, field.name)
            for field in dataclasses.fields(self)
        }
        return CacheInfo(**values)


@dataclass
class MutableCacheInfo:
    """Internal mutable counter accumulator."""

    hits: int = 0
    misses: int = 0
    waits: int = 0
    stores: int = 0
    evictions: int = 0
    expirations: int = 0
    bypasses: int = 0
    errors: int = 0
    invalidations: int = 0
    l1_hits: int = 0
    l2_hits: int = 0
    stale_hits: int = 0
    refusals: int = 0
    corruptions: int = 0
    promotions: int = 0
    lease_contentions: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    compute_ns: int = 0

    def freeze(self, *, currsize: int = 0, maxsize: int = 0) -> CacheInfo:
        payload = dataclasses.asdict(self)
        payload.update(currsize=currsize, maxsize=maxsize)
        return CacheInfo(**payload)


def now_seconds() -> float:
    """Wall-clock timestamp used in persisted records and receipts."""

    return time.time()
