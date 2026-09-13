# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Transparent domain proxy and solver domain-factory integration."""

from __future__ import annotations

import functools
import inspect
import os
import threading
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

import wrapt

from .coordinator import CacheFabric
from .types import (
    UNSAFE_CAPABILITY_METHODS,
    CacheConfig,
    CacheMode,
    CachePolicy,
    MethodPolicy,
)

__all__ = [
    "CachedDomain",
    "CachedDomainFactory",
    "cache_domain",
    "cache_domain_factory",
]

_DomainT = TypeVar("_DomainT")


def _derive_namespace(domain: Any, explicit: str | None) -> str:
    if explicit:
        return explicit
    declared = getattr(domain, "__cache_namespace__", None)
    if declared:
        return str(declared)
    fingerprint = getattr(domain, "__cache_fingerprint__", None)
    if fingerprint is not None:
        projected = fingerprint() if callable(fingerprint) else fingerprint
        return f"{type(domain).__module__}.{type(domain).__qualname__}:{projected}"
    # Safe default: no cross-instance equivalence claim. A caller that wants
    # multi-solver or cross-run reuse must name the admitted model namespace.
    return (
        f"instance:{type(domain).__module__}.{type(domain).__qualname__}:"
        f"{uuid.uuid4().hex}"
    )


class CachedDomain(wrapt.ObjectProxy):
    """Transparent capability-aware cache wrapper around a domain instance.

    ``wrapt.ObjectProxy`` preserves ``__class__`` and therefore the framework's
    mixin/MRO capability checks, unlike a plain composition proxy.
    """

    def __init__(
        self,
        domain: _DomainT,
        *,
        fabric: CacheFabric,
        policy: CachePolicy,
        namespace: str | None = None,
    ) -> None:
        super().__init__(domain)
        self._self_cache_fabric = fabric
        self._self_cache_policy = policy
        self._self_cache_namespace = _derive_namespace(domain, namespace)
        self._self_cache_wrappers: dict[str, Callable[..., Any]] = {}
        self._self_cache_wrapper_lock = threading.RLock()

    @property
    def cache_fabric(self) -> CacheFabric:
        return self._self_cache_fabric

    @property
    def cache_policy(self) -> CachePolicy:
        return self._self_cache_policy

    @property
    def cache_namespace(self) -> str:
        return self._self_cache_namespace

    def cache_info(self):
        return self._self_cache_fabric.info()

    def cache_receipts(self):
        return self._self_cache_fabric.receipts()

    def invalidate_cache(self, method: str | None = None, *, tags=()) -> int:
        return self._self_cache_fabric.invalidate(
            namespace=self._self_cache_namespace,
            method=method,
            tags=tags,
        )

    def clear_cache(self, *, reset_stats: bool = False) -> int:
        return self._self_cache_fabric.clear(reset_stats=reset_stats)

    def _self_cache_call_is_explicit(
        self,
        callable_object: Callable[..., Any],
        method_policy: MethodPolicy,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> bool:
        required = method_policy.requires_explicit_arguments
        if not required:
            return True
        try:
            signature = inspect.signature(callable_object)
            bound = signature.bind_partial(*args, **kwargs)
        except (TypeError, ValueError):
            return False
        return all(
            name in bound.arguments and bound.arguments[name] is not None
            for name in required
        )

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self.__wrapped__, name)
        if (
            name not in self._self_cache_policy.methods
            or name in UNSAFE_CAPABILITY_METHODS
            or name.startswith("_")
            or name.startswith("sample")
            or not callable(attribute)
        ):
            return attribute

        with self._self_cache_wrapper_lock:
            wrapper = self._self_cache_wrappers.get(name)
            if wrapper is not None:
                return wrapper
            method_policy = self._self_cache_policy.policy_for(name)

            @functools.wraps(attribute)
            def cached(*args: Any, **kwargs: Any) -> Any:
                if not self._self_cache_call_is_explicit(
                    attribute, method_policy, args, kwargs
                ):
                    return self._self_cache_fabric.execute(
                        namespace=self._self_cache_namespace,
                        method=name,
                        args=args,
                        kwargs=kwargs,
                        compute=lambda: attribute(*args, **kwargs),
                        policy=method_policy,
                        mode=CacheMode.BYPASS,
                        tags=("implicit-state-bypass",),
                    )
                return self._self_cache_fabric.execute(
                    namespace=self._self_cache_namespace,
                    method=name,
                    args=args,
                    kwargs=kwargs,
                    compute=lambda: attribute(*args, **kwargs),
                    policy=method_policy,
                    tags=("domain-model",),
                    metadata={
                        "domain_type": (
                            f"{type(self.__wrapped__).__module__}."
                            f"{type(self.__wrapped__).__qualname__}"
                        )
                    },
                )

            self._self_cache_wrappers[name] = cached
            return cached

    def __reduce__(self):
        return (
            _restore_cached_domain,
            (
                self.__wrapped__,
                self._self_cache_policy,
                self._self_cache_namespace,
                self._self_cache_fabric.config,
            ),
        )


def _restore_cached_domain(
    domain: Any,
    policy: CachePolicy,
    namespace: str,
    config: CacheConfig,
) -> CachedDomain:
    return cache_domain(
        domain,
        policy=policy,
        namespace=namespace,
        config=config,
    )


class CachedDomainFactory:
    """Pickle-safe solver factory sharing one cache namespace and L2 database.

    Each process receives its own L1 memory tier and SQLite connection while the
    persistent tier and compute leases coordinate reuse across solver workers.
    """

    def __init__(
        self,
        domain_factory: Callable[[], _DomainT],
        *,
        policy: CachePolicy,
        namespace: str,
        config: CacheConfig | None = None,
    ) -> None:
        if not namespace:
            raise ValueError(
                "cache_domain_factory requires an explicit namespace because it "
                "asserts equivalence across domain instances"
            )
        self.domain_factory = domain_factory
        self.policy = policy
        self.namespace = namespace
        self.config = config or CacheConfig(
            memory_max_entries=policy.max_entries,
        )
        self._fabric: CacheFabric | None = None
        self._fabric_pid: int | None = None
        self._lock = threading.RLock()

    def _get_fabric(self) -> CacheFabric:
        pid = os.getpid()
        with self._lock:
            if self._fabric is None or self._fabric_pid != pid:
                self._fabric = CacheFabric(self.config)
                self._fabric_pid = pid
            return self._fabric

    def __call__(self) -> CachedDomain:
        return CachedDomain(
            self.domain_factory(),
            fabric=self._get_fabric(),
            policy=self.policy,
            namespace=self.namespace,
        )

    @property
    def cache_fabric(self) -> CacheFabric:
        return self._get_fabric()

    def close(self) -> None:
        with self._lock:
            if self._fabric is not None:
                self._fabric.close()
                self._fabric = None
                self._fabric_pid = None

    def __getstate__(self):
        return {
            "domain_factory": self.domain_factory,
            "policy": self.policy,
            "namespace": self.namespace,
            "config": self.config,
        }

    def __setstate__(self, state):
        self.domain_factory = state["domain_factory"]
        self.policy = state["policy"]
        self.namespace = state["namespace"]
        self.config = state["config"]
        self._fabric = None
        self._fabric_pid = None
        self._lock = threading.RLock()


def cache_domain(
    domain: _DomainT,
    *,
    policy: CachePolicy | None = None,
    namespace: str | None = None,
    fabric: CacheFabric | None = None,
    config: CacheConfig | None = None,
) -> CachedDomain:
    active_policy = policy or CachePolicy.model()
    active_config = config or CacheConfig(
        memory_max_entries=active_policy.max_entries,
    )
    return CachedDomain(
        domain,
        fabric=fabric or CacheFabric(active_config),
        policy=active_policy,
        namespace=namespace,
    )


def cache_domain_factory(
    domain_factory: Callable[[], _DomainT],
    *,
    policy: CachePolicy | None = None,
    namespace: str,
    config: CacheConfig | None = None,
) -> CachedDomainFactory:
    return CachedDomainFactory(
        domain_factory,
        policy=policy or CachePolicy.model(),
        namespace=namespace,
        config=config,
    )
