# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Admission, lookup, construction, receipts, replay, and invalidation."""

from __future__ import annotations

import contextlib
import contextvars
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from .codecs import PickleCodec, ValueCodec
from .keys import CanonicalKeyEncoder, Digestor, make_cache_key
from .stores import (
    CacheStore,
    MemoryCacheStore,
    SQLiteCacheStore,
    StoreLookup,
    TieredCacheStore,
)
from .types import (
    CacheAdmissionError,
    CacheConfig,
    CacheDisposition,
    CacheInfo,
    CacheKey,
    CacheLeaseTimeoutError,
    CacheMode,
    CacheReceipt,
    CacheRecord,
    CacheResult,
    MethodPolicy,
    MutableCacheInfo,
    UnhashableCacheKeyError,
    now_seconds,
)

__all__ = ["CacheFabric", "build_cache_store"]

_T = TypeVar("_T")


@dataclass
class _Flight:
    event: threading.Event
    result: CacheResult | None = None
    error: BaseException | None = None


def build_cache_store(config: CacheConfig) -> TieredCacheStore:
    memory = MemoryCacheStore(
        max_entries=config.memory_max_entries,
        max_bytes=config.memory_max_bytes,
        protected_ratio=config.protected_ratio,
    )
    persistent = None
    if config.persistent_path is not None:
        persistent = SQLiteCacheStore(
            config.persistent_path,
            max_bytes=config.persistent_max_bytes,
            busy_timeout_ms=config.sqlite_busy_timeout_ms,
            touch_interval_seconds=config.sqlite_touch_interval_seconds,
        )
    return TieredCacheStore(memory, persistent)


class CacheFabric:
    """Multi-tier cache fabric for deterministic domain and solver computations.

    No background worker is created. Every construction, lease, promotion,
    verification, invalidation, and replay operation is explicit and receipted.
    """

    def __init__(
        self,
        config: CacheConfig | None = None,
        *,
        store: CacheStore | None = None,
        codec: ValueCodec | None = None,
        receipt_sink: Callable[[CacheReceipt], None] | None = None,
        owner: str | None = None,
        clock: Callable[[], float] = now_seconds,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.config = config or CacheConfig()
        self.digestor = Digestor(self.config.digest_algorithm)
        self.encoder = CanonicalKeyEncoder()
        self.codec = codec or PickleCodec(
            digestor=self.digestor,
            compression_threshold_bytes=self.config.compression_threshold_bytes,
        )
        self.store = store or build_cache_store(self.config)
        self.owner = owner or f"{os.getpid()}:{uuid.uuid4().hex}"
        self._clock = clock
        self._monotonic_ns = monotonic_ns
        self._receipt_sink = receipt_sink
        self._receipts: deque[CacheReceipt] = deque(maxlen=self.config.receipt_history)
        self._receipt_lock = threading.RLock()
        self._flights: dict[str, _Flight] = {}
        self._flight_lock = threading.RLock()
        self._stats = MutableCacheInfo()
        self._stats_lock = threading.RLock()
        self._mode: contextvars.ContextVar[CacheMode] = contextvars.ContextVar(
            "skdecide_cache_mode", default=CacheMode.NORMAL
        )

    @contextlib.contextmanager
    def mode(self, mode: CacheMode):
        """Temporarily override the cache mode in the current context."""

        token = self._mode.set(mode)
        try:
            yield self
        finally:
            self._mode.reset(token)

    def _emit(self, receipt: CacheReceipt) -> None:
        with self._receipt_lock:
            self._receipts.append(receipt)
        if self._receipt_sink is not None:
            self._receipt_sink(receipt)

    def receipts(self) -> tuple[CacheReceipt, ...]:
        with self._receipt_lock:
            return tuple(self._receipts)

    @property
    def last_receipt(self) -> CacheReceipt | None:
        with self._receipt_lock:
            return self._receipts[-1] if self._receipts else None

    def export_receipts(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(receipt.to_json() for receipt in self.receipts())
        target.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        return target

    def _make_receipt(
        self,
        *,
        key: CacheKey,
        disposition: CacheDisposition,
        lookup: StoreLookup | None = None,
        record: CacheRecord | None = None,
        compute_ns: int = 0,
        load_ns: int = 0,
        verified: bool = False,
        error: BaseException | None = None,
        tags: tuple[str, ...] = (),
    ) -> CacheReceipt:
        active_record = record or (lookup.record if lookup is not None else None)
        return CacheReceipt(
            key_digest=key.digest,
            value_digest=(active_record.value_digest if active_record else None),
            namespace=key.namespace,
            method=key.method,
            version=key.version,
            disposition=disposition,
            tier=(lookup.tier if lookup is not None else None),
            observed_at=self._clock(),
            created_at=(active_record.created_at if active_record else None),
            expires_at=(active_record.expires_at if active_record else None),
            compute_ns=compute_ns,
            load_ns=load_ns,
            size_bytes=(active_record.size_bytes if active_record else 0),
            owner=self.owner,
            verified=verified,
            error_type=(type(error).__name__ if error is not None else None),
            tags=tags or (active_record.tags if active_record else ()),
        )

    def _decode(self, lookup: StoreLookup, policy: MethodPolicy) -> tuple[Any, int]:
        started = self._monotonic_ns()
        value = self.codec.decode(
            lookup.record.payload,
            value_digest=lookup.record.value_digest,
            compressed=lookup.record.compressed,
            copy_on_read=policy.copy_on_read,
        )
        return value, self._monotonic_ns() - started

    def _lookup_fresh(
        self,
        key: CacheKey,
        policy: MethodPolicy,
    ) -> tuple[CacheResult | None, StoreLookup | None]:
        lookup = self.store.get(key, now=self._clock())
        if lookup is None:
            return None, None
        if lookup.stale:
            return None, lookup
        value, load_ns = self._decode(lookup, policy)
        disposition = (
            CacheDisposition.HIT_L1
            if lookup.tier == "memory"
            else CacheDisposition.HIT_L2
        )
        receipt = self._make_receipt(
            key=key,
            disposition=disposition,
            lookup=lookup,
            load_ns=load_ns,
        )
        with self._stats_lock:
            self._stats.hits += 1
            if lookup.tier == "memory":
                self._stats.l1_hits += 1
            else:
                self._stats.l2_hits += 1
        self._emit(receipt)
        return CacheResult(value=value, receipt=receipt), None

    def execute(
        self,
        *,
        namespace: str,
        method: str,
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
        compute: Callable[[], _T],
        policy: MethodPolicy | None = None,
        mode: CacheMode | None = None,
        tags: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> _T:
        """Execute one admitted deterministic computation and return its value."""

        return self.execute_with_receipt(
            namespace=namespace,
            method=method,
            args=args,
            kwargs=kwargs,
            compute=compute,
            policy=policy,
            mode=mode,
            tags=tags,
            metadata=metadata,
        ).value

    def execute_with_receipt(
        self,
        *,
        namespace: str,
        method: str,
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
        compute: Callable[[], _T],
        policy: MethodPolicy | None = None,
        mode: CacheMode | None = None,
        tags: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> CacheResult:
        kwargs = dict(kwargs or {})
        policy = policy or MethodPolicy()
        active_mode = mode or self._mode.get()
        if not namespace:
            raise CacheAdmissionError("cache namespace must be non-empty")
        if not method or method.startswith("_") or method.startswith("sample"):
            with self._stats_lock:
                self._stats.refusals += 1
            raise CacheAdmissionError(
                f"operation is not admitted for caching: {method!r}"
            )

        try:
            projection = policy.key_fn(args, kwargs) if policy.key_fn else None
            key = make_cache_key(
                namespace=namespace,
                method=method,
                version=policy.version,
                args=args,
                kwargs=kwargs,
                encoder=self.encoder,
                digestor=self.digestor,
                key_projection=projection,
            )
        except UnhashableCacheKeyError:
            if policy.on_unhashable == "raise":
                raise
            started = self._monotonic_ns()
            value = compute()
            compute_ns = self._monotonic_ns() - started
            synthetic = CacheKey(
                digest="unhashable",
                algorithm=self.digestor.algorithm,
                namespace=namespace,
                method=method,
                version=policy.version,
                canonical_size=0,
            )
            receipt = self._make_receipt(
                key=synthetic,
                disposition=CacheDisposition.BYPASS,
                compute_ns=compute_ns,
            )
            with self._stats_lock:
                self._stats.bypasses += 1
                self._stats.compute_ns += compute_ns
            self._emit(receipt)
            return CacheResult(value=value, receipt=receipt)

        computed_tags = list(policy.static_tags)
        if policy.tag_fn is not None:
            computed_tags.extend(policy.tag_fn(args, kwargs))
        computed_tags.extend(tags)
        computed_tags.extend(
            (
                f"namespace:{namespace}",
                f"method:{method}",
                f"key:{key.digest}",
            )
        )
        normalized_tags = tuple(sorted(set(computed_tags)))

        if active_mode == CacheMode.BYPASS:
            started = self._monotonic_ns()
            value = compute()
            compute_ns = self._monotonic_ns() - started
            receipt = self._make_receipt(
                key=key,
                disposition=CacheDisposition.BYPASS,
                compute_ns=compute_ns,
                tags=normalized_tags,
            )
            with self._stats_lock:
                self._stats.bypasses += 1
                self._stats.compute_ns += compute_ns
            self._emit(receipt)
            return CacheResult(value=value, receipt=receipt)

        stale_lookup: StoreLookup | None = None
        if active_mode not in {CacheMode.REFRESH, CacheMode.VERIFY}:
            result, stale_lookup = self._lookup_fresh(key, policy)
            if result is not None:
                return result
        elif active_mode == CacheMode.VERIFY:
            result, stale_lookup = self._lookup_fresh(key, policy)
            if result is not None:
                started = self._monotonic_ns()
                observed = compute()
                compute_ns = self._monotonic_ns() - started
                encoded = self.codec.encode(observed)
                if encoded.value_digest == result.receipt.value_digest:
                    receipt = self._make_receipt(
                        key=key,
                        disposition=CacheDisposition.VERIFIED_HIT,
                        compute_ns=compute_ns,
                        verified=True,
                        tags=normalized_tags,
                    )
                    with self._stats_lock:
                        self._stats.compute_ns += compute_ns
                    self._emit(receipt)
                    return CacheResult(value=observed, receipt=receipt)
                self.invalidate(tags=(f"key:{key.digest}",))
                with self._stats_lock:
                    self._stats.misses += 1
                return self._store_computed(
                    key=key,
                    value=observed,
                    policy=policy,
                    compute_ns=compute_ns,
                    tags=normalized_tags,
                    metadata=metadata,
                )

        if active_mode == CacheMode.READ_ONLY:
            receipt = self._make_receipt(
                key=key,
                disposition=CacheDisposition.READ_ONLY_MISS,
                tags=normalized_tags,
            )
            with self._stats_lock:
                self._stats.misses += 1
            self._emit(receipt)
            raise KeyError(f"cache read-only miss: {key.digest}")

        if not policy.single_flight:
            with self._stats_lock:
                self._stats.misses += 1
            return self._construct(
                key=key,
                compute=compute,
                policy=policy,
                stale_lookup=stale_lookup,
                tags=normalized_tags,
                metadata=metadata,
                force_refresh=active_mode == CacheMode.REFRESH,
            )

        with self._flight_lock:
            flight = self._flights.get(key.digest)
            if flight is None:
                flight = _Flight(event=threading.Event())
                self._flights[key.digest] = flight
                leader = True
                with self._stats_lock:
                    self._stats.misses += 1
            else:
                leader = False
                with self._stats_lock:
                    self._stats.waits += 1

        if not leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            # Prefer an independently decoded stored value to avoid sharing a
            # mutable object graph with the leader.
            result, _ = self._lookup_fresh(key, policy)
            if result is not None:
                return result
            assert flight.result is not None
            return flight.result

        try:
            result = self._construct(
                key=key,
                compute=compute,
                policy=policy,
                stale_lookup=stale_lookup,
                tags=normalized_tags,
                metadata=metadata,
                force_refresh=active_mode == CacheMode.REFRESH,
            )
            flight.result = result
            return result
        except BaseException as error:
            flight.error = error
            raise
        finally:
            flight.event.set()
            with self._flight_lock:
                self._flights.pop(key.digest, None)

    def _construct(
        self,
        *,
        key: CacheKey,
        compute: Callable[[], _T],
        policy: MethodPolicy,
        stale_lookup: StoreLookup | None,
        tags: tuple[str, ...],
        metadata: Mapping[str, Any] | None,
        force_refresh: bool = False,
    ) -> CacheResult:
        lease_acquired = False
        if policy.cross_process_single_flight:
            lease_acquired = self.store.acquire_lease(
                key.digest, self.owner, policy.lease_seconds
            )
            if not lease_acquired:
                deadline = time.monotonic() + policy.lease_wait_seconds
                while time.monotonic() < deadline:
                    lookup = self.store.get(key, now=self._clock())
                    if lookup is not None and not lookup.stale:
                        value, load_ns = self._decode(lookup, policy)
                        receipt = self._make_receipt(
                            key=key,
                            disposition=(
                                CacheDisposition.HIT_L1
                                if lookup.tier == "memory"
                                else CacheDisposition.HIT_L2
                            ),
                            lookup=lookup,
                            load_ns=load_ns,
                        )
                        with self._stats_lock:
                            self._stats.hits += 1
                            self._stats.lease_contentions += 1
                        self._emit(receipt)
                        return CacheResult(value=value, receipt=receipt)
                    time.sleep(policy.lease_poll_seconds)
                if policy.lease_timeout == "raise":
                    raise CacheLeaseTimeoutError(
                        f"timed out waiting for cache lease {key.digest}"
                    )

        try:
            # A process may have filled the record between the original miss and
            # lease acquisition.
            if lease_acquired and not force_refresh:
                result, refreshed_stale = self._lookup_fresh(key, policy)
                if result is not None:
                    return result
                stale_lookup = stale_lookup or refreshed_stale

            started = self._monotonic_ns()
            try:
                value = compute()
            except BaseException as error:
                compute_ns = self._monotonic_ns() - started
                with self._stats_lock:
                    self._stats.errors += 1
                    self._stats.compute_ns += compute_ns
                if stale_lookup is not None and stale_lookup.record.is_stale_servable(
                    self._clock()
                ):
                    value, load_ns = self._decode(stale_lookup, policy)
                    receipt = self._make_receipt(
                        key=key,
                        disposition=CacheDisposition.STALE_IF_ERROR,
                        lookup=stale_lookup,
                        compute_ns=compute_ns,
                        load_ns=load_ns,
                        error=error,
                    )
                    with self._stats_lock:
                        self._stats.stale_hits += 1
                    self._emit(receipt)
                    return CacheResult(value=value, receipt=receipt)
                raise
            compute_ns = self._monotonic_ns() - started
            with self._stats_lock:
                self._stats.compute_ns += compute_ns
            return self._store_computed(
                key=key,
                value=value,
                policy=policy,
                compute_ns=compute_ns,
                tags=tags,
                metadata=metadata,
            )
        finally:
            if lease_acquired:
                self.store.release_lease(key.digest, self.owner)

    def _store_computed(
        self,
        *,
        key: CacheKey,
        value: Any,
        policy: MethodPolicy,
        compute_ns: int,
        tags: tuple[str, ...],
        metadata: Mapping[str, Any] | None,
    ) -> CacheResult:
        if value is None and not policy.cache_none:
            receipt = self._make_receipt(
                key=key,
                disposition=CacheDisposition.MISS_UNSTORED,
                compute_ns=compute_ns,
                tags=tags,
            )
            self._emit(receipt)
            return CacheResult(value=value, receipt=receipt)

        encoded = self.codec.encode(value)
        created_at = self._clock()
        expires_at = (
            None if policy.ttl_seconds is None else created_at + policy.ttl_seconds
        )
        stale_until = (
            None
            if expires_at is None or policy.stale_if_error_seconds <= 0
            else expires_at + policy.stale_if_error_seconds
        )
        record = CacheRecord(
            key=key,
            value_digest=encoded.value_digest,
            payload=encoded.payload,
            codec=encoded.codec,
            compressed=encoded.compressed,
            created_at=created_at,
            expires_at=expires_at,
            stale_until=stale_until,
            size_bytes=encoded.size_bytes,
            raw_size_bytes=encoded.raw_size_bytes,
            tags=tags,
            compute_ns=compute_ns,
            metadata=dict(metadata or {}),
        )
        stored = self.store.put(record)
        disposition = (
            CacheDisposition.MISS_STORED if stored else CacheDisposition.MISS_UNSTORED
        )
        receipt = self._make_receipt(
            key=key,
            disposition=disposition,
            record=record,
            compute_ns=compute_ns,
            tags=tags,
        )
        with self._stats_lock:
            if stored:
                self._stats.stores += 1
        self._emit(receipt)
        return CacheResult(value=value, receipt=receipt)

    def replay(self, key_digest: str, *, copy_on_read: bool = True) -> CacheResult:
        """Replay a stored value by its content-addressed computation key."""

        key = CacheKey(
            digest=key_digest,
            algorithm=self.digestor.algorithm,
            namespace="replay",
            method="replay",
            version="1",
            canonical_size=0,
        )
        lookup = self.store.get(key, now=self._clock())
        if lookup is None:
            raise KeyError(f"cache replay miss: {key_digest}")
        policy = MethodPolicy(copy_on_read=copy_on_read)
        value, load_ns = self._decode(lookup, policy)
        receipt = self._make_receipt(
            key=lookup.record.key,
            disposition=(
                CacheDisposition.HIT_L1
                if lookup.tier == "memory"
                else CacheDisposition.HIT_L2
            ),
            lookup=lookup,
            load_ns=load_ns,
        )
        self._emit(receipt)
        return CacheResult(value=value, receipt=receipt)

    def invalidate(
        self,
        *,
        namespace: str | None = None,
        method: str | None = None,
        tags: Iterable[str] = (),
    ) -> int:
        removed = self.store.invalidate(
            namespace=namespace,
            method=method,
            tags=tuple(tags),
        )
        with self._stats_lock:
            self._stats.invalidations += removed
        return removed

    def clear(self, *, reset_stats: bool = False) -> int:
        removed = self.store.clear(reset_stats=reset_stats)
        with self._stats_lock:
            if reset_stats:
                self._stats = MutableCacheInfo()
            else:
                self._stats.invalidations += removed
        if reset_stats:
            with self._receipt_lock:
                self._receipts.clear()
        return removed

    def info(self) -> CacheInfo:
        store_info = self.store.info()
        with self._stats_lock:
            logical = self._stats.freeze(
                currsize=store_info.currsize,
                maxsize=store_info.maxsize,
            )
        # Logical counters are authoritative for calls. Store counters contribute
        # resource events that are invisible at the coordinator boundary.
        return CacheInfo(
            hits=logical.hits,
            misses=logical.misses,
            waits=logical.waits,
            stores=logical.stores,
            evictions=store_info.evictions,
            expirations=store_info.expirations,
            bypasses=logical.bypasses,
            errors=logical.errors,
            invalidations=logical.invalidations,
            currsize=store_info.currsize,
            maxsize=store_info.maxsize,
            l1_hits=logical.l1_hits,
            l2_hits=logical.l2_hits,
            stale_hits=logical.stale_hits,
            refusals=logical.refusals,
            corruptions=store_info.corruptions,
            promotions=store_info.promotions,
            lease_contentions=logical.lease_contentions + store_info.lease_contentions,
            bytes_read=store_info.bytes_read,
            bytes_written=store_info.bytes_written,
            compute_ns=logical.compute_ns,
        )

    def close(self) -> None:
        self.store.close()
