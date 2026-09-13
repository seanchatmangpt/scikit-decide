# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Thread-safe memory and process-safe SQLite cache tiers."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from .types import CacheInfo, CacheKey, CacheRecord, MutableCacheInfo

__all__ = [
    "CacheStore",
    "MemoryCacheStore",
    "SQLiteCacheStore",
    "StoreLookup",
    "TieredCacheStore",
]


@dataclass(frozen=True)
class StoreLookup:
    record: CacheRecord
    tier: str
    stale: bool


class CacheStore(Protocol):
    name: str

    def get(self, key: CacheKey, *, now: float | None = None) -> StoreLookup | None: ...

    def put(self, record: CacheRecord) -> bool: ...

    def invalidate(
        self,
        *,
        namespace: str | None = None,
        method: str | None = None,
        tags: Iterable[str] = (),
    ) -> int: ...

    def clear(self, *, reset_stats: bool = False) -> int: ...

    def info(self) -> CacheInfo: ...

    def acquire_lease(
        self, key_digest: str, owner: str, lease_seconds: float
    ) -> bool: ...

    def release_lease(self, key_digest: str, owner: str) -> None: ...

    def close(self) -> None: ...


class MemoryCacheStore:
    """Byte-bounded segmented LRU with lightweight TinyLFU admission.

    Probation protects the cache from one-hit scans. Repeatedly used records are
    promoted to a protected segment. When full, frequency evidence decides
    whether a new record should displace the probation victim.
    """

    name = "memory"

    def __init__(
        self,
        max_entries: int = 4096,
        *,
        max_bytes: int = 64 * 1024 * 1024,
        protected_ratio: float = 0.8,
        clock=time.time,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        if not 0 < protected_ratio < 1:
            raise ValueError("protected_ratio must be between 0 and 1")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._protected_limit = max(1, int(max_entries * protected_ratio))
        self._clock = clock
        self._probation: OrderedDict[str, CacheRecord] = OrderedDict()
        self._protected: OrderedDict[str, CacheRecord] = OrderedDict()
        self._frequency: dict[str, int] = {}
        self._frequency_events = 0
        self._bytes = 0
        self._leases: dict[str, tuple[str, float]] = {}
        self._stats = MutableCacheInfo()
        self._lock = threading.RLock()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def _count(self, digest: str) -> None:
        self._frequency[digest] = min(65535, self._frequency.get(digest, 0) + 1)
        self._frequency_events += 1
        if self._frequency_events >= max(1024, self._max_entries * 16):
            self._frequency = {
                key: value // 2 for key, value in self._frequency.items() if value > 1
            }
            self._frequency_events = 0

    def _remove(self, digest: str) -> CacheRecord | None:
        record = self._probation.pop(digest, None)
        if record is None:
            record = self._protected.pop(digest, None)
        if record is not None:
            self._bytes -= record.size_bytes
        return record

    def _victim(self) -> tuple[str, CacheRecord] | None:
        if self._probation:
            return next(iter(self._probation.items()))
        if self._protected:
            return next(iter(self._protected.items()))
        return None

    def _rebalance(self) -> None:
        while len(self._protected) > self._protected_limit:
            digest, record = self._protected.popitem(last=False)
            self._probation[digest] = record
        while (
            len(self._probation) + len(self._protected) > self._max_entries
            or self._bytes > self._max_bytes
        ):
            victim = self._victim()
            if victim is None:
                break
            digest, _ = victim
            self._remove(digest)
            self._stats.evictions += 1

    def get(self, key: CacheKey, *, now: float | None = None) -> StoreLookup | None:
        observed_at = self._clock() if now is None else now
        with self._lock:
            self._count(key.digest)
            record = self._protected.get(key.digest)
            if record is not None:
                if not record.is_fresh(observed_at) and not record.is_stale_servable(
                    observed_at
                ):
                    self._remove(key.digest)
                    self._stats.expirations += 1
                    self._stats.misses += 1
                    return None
                self._protected.move_to_end(key.digest)
                self._stats.hits += 1
                self._stats.l1_hits += 1
                self._stats.bytes_read += record.size_bytes
                stale = not record.is_fresh(observed_at)
                if stale:
                    self._stats.stale_hits += 1
                return StoreLookup(record=record, tier=self.name, stale=stale)

            record = self._probation.get(key.digest)
            if record is None:
                self._stats.misses += 1
                return None
            if not record.is_fresh(observed_at) and not record.is_stale_servable(
                observed_at
            ):
                self._remove(key.digest)
                self._stats.expirations += 1
                self._stats.misses += 1
                return None
            self._probation.pop(key.digest)
            self._protected[key.digest] = record
            self._rebalance()
            self._stats.hits += 1
            self._stats.l1_hits += 1
            self._stats.bytes_read += record.size_bytes
            stale = not record.is_fresh(observed_at)
            if stale:
                self._stats.stale_hits += 1
            return StoreLookup(record=record, tier=self.name, stale=stale)

    def put(self, record: CacheRecord) -> bool:
        if record.size_bytes > self._max_bytes:
            return False
        with self._lock:
            self._count(record.key.digest)
            self._remove(record.key.digest)
            victim = self._victim()
            full = (
                len(self._probation) + len(self._protected) >= self._max_entries
                or self._bytes + record.size_bytes > self._max_bytes
            )
            if full and victim is not None:
                victim_digest, _ = victim
                if self._frequency.get(record.key.digest, 0) < self._frequency.get(
                    victim_digest, 0
                ):
                    return False
            self._probation[record.key.digest] = record
            self._bytes += record.size_bytes
            self._stats.stores += 1
            self._stats.bytes_written += record.size_bytes
            self._rebalance()
            return (
                record.key.digest in self._probation
                or record.key.digest in self._protected
            )

    def invalidate(
        self,
        *,
        namespace: str | None = None,
        method: str | None = None,
        tags: Iterable[str] = (),
    ) -> int:
        required_tags = set(tags)
        with self._lock:
            candidates = list(self._probation.items()) + list(self._protected.items())
            digests = [
                digest
                for digest, record in candidates
                if (namespace is None or record.key.namespace == namespace)
                and (method is None or record.key.method == method)
                and (not required_tags or required_tags.intersection(record.tags))
            ]
            for digest in digests:
                self._remove(digest)
            if digests:
                self._stats.invalidations += len(digests)
            return len(digests)

    def clear(self, *, reset_stats: bool = False) -> int:
        with self._lock:
            count = len(self._probation) + len(self._protected)
            self._probation.clear()
            self._protected.clear()
            self._frequency.clear()
            self._bytes = 0
            if reset_stats:
                self._stats = MutableCacheInfo()
            else:
                self._stats.invalidations += count
            return count

    def info(self) -> CacheInfo:
        with self._lock:
            return self._stats.freeze(
                currsize=len(self._probation) + len(self._protected),
                maxsize=self._max_entries,
            )

    def acquire_lease(self, key_digest: str, owner: str, lease_seconds: float) -> bool:
        now = self._clock()
        with self._lock:
            current = self._leases.get(key_digest)
            if current is not None and current[1] > now and current[0] != owner:
                self._stats.lease_contentions += 1
                return False
            self._leases[key_digest] = (owner, now + lease_seconds)
            return True

    def release_lease(self, key_digest: str, owner: str) -> None:
        with self._lock:
            current = self._leases.get(key_digest)
            if current is not None and current[0] == owner:
                self._leases.pop(key_digest, None)

    def close(self) -> None:
        return None


class SQLiteCacheStore:
    """Persistent content-addressed store with WAL and process-safe leases."""

    name = "sqlite"
    _SCHEMA_VERSION = 2

    def __init__(
        self,
        path: Path | str,
        *,
        max_bytes: int = 4 * 1024 * 1024 * 1024,
        busy_timeout_ms: int = 5000,
        touch_interval_seconds: float = 5.0,
        clock=time.time,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._busy_timeout_ms = busy_timeout_ms
        self._touch_interval = touch_interval_seconds
        self._clock = clock
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()
        self._stats = MutableCacheInfo()
        self._stats_lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            return connection
        connection = sqlite3.connect(
            self.path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        # `PRAGMA journal_mode=WAL` needs an exclusive lock to perform the
        # (one-time, per file) journal-mode switch. sqlite3.connect's own
        # `timeout=` busy handler covers ordinary statement execution, but
        # two processes racing to open the *same not-yet-existent* db file
        # for the first time can still observe "database is locked" here
        # specifically -- reproduced deterministically (5/5 runs) via two
        # subprocesses calling CacheFabric(CacheConfig(persistent_path=...))
        # against a fresh path concurrently. Retry this one statement with
        # backoff, bounded by the same busy_timeout budget every other
        # lock-wait in this store already honors.
        self._execute_with_lock_retry(connection, "PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys=ON")
        self._local.connection = connection
        with self._connections_lock:
            self._connections.append(connection)
        return connection

    def _execute_with_lock_retry(
        self, connection: sqlite3.Connection, sql: str, *, poll_seconds: float = 0.01
    ) -> None:
        deadline = time.monotonic() + self._busy_timeout_ms / 1000
        while True:
            try:
                connection.execute(sql)
                return
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() or time.monotonic() >= deadline:
                    raise
                time.sleep(poll_seconds)

    def _initialize(self) -> None:
        connection = self._connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cache_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cache_blobs (
                digest TEXT PRIMARY KEY,
                payload BLOB NOT NULL,
                codec TEXT NOT NULL,
                compressed INTEGER NOT NULL,
                raw_size_bytes INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cache_entries (
                key_digest TEXT PRIMARY KEY,
                algorithm TEXT NOT NULL,
                namespace TEXT NOT NULL,
                method TEXT NOT NULL,
                version TEXT NOT NULL,
                canonical_size INTEGER NOT NULL,
                value_digest TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                stale_until REAL,
                accessed_at REAL NOT NULL,
                compute_ns INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY(value_digest) REFERENCES cache_blobs(digest)
            );
            CREATE INDEX IF NOT EXISTS idx_cache_entries_namespace_method
                ON cache_entries(namespace, method);
            CREATE INDEX IF NOT EXISTS idx_cache_entries_accessed
                ON cache_entries(accessed_at);
            CREATE TABLE IF NOT EXISTS cache_tags (
                tag TEXT NOT NULL,
                key_digest TEXT NOT NULL,
                PRIMARY KEY(tag, key_digest),
                FOREIGN KEY(key_digest) REFERENCES cache_entries(key_digest)
                    ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_cache_tags_key ON cache_tags(key_digest);
            CREATE TABLE IF NOT EXISTS cache_leases (
                key_digest TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                expires_at REAL NOT NULL
            );
            """
        )
        row = connection.execute(
            "SELECT value FROM cache_meta WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO cache_meta(key, value) VALUES('schema_version', ?)",
                (str(self._SCHEMA_VERSION),),
            )
        elif int(row["value"]) != self._SCHEMA_VERSION:
            raise RuntimeError(
                f"unsupported cache schema {row['value']}; "
                f"expected {self._SCHEMA_VERSION}"
            )

    def _row_to_record(self, row: sqlite3.Row, tags: tuple[str, ...]) -> CacheRecord:
        key = CacheKey(
            digest=row["key_digest"],
            algorithm=row["algorithm"],
            namespace=row["namespace"],
            method=row["method"],
            version=row["version"],
            canonical_size=row["canonical_size"],
        )
        return CacheRecord(
            key=key,
            value_digest=row["value_digest"],
            payload=bytes(row["payload"]),
            codec=row["codec"],
            compressed=bool(row["compressed"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            stale_until=row["stale_until"],
            size_bytes=row["size_bytes"],
            raw_size_bytes=row["raw_size_bytes"],
            tags=tags,
            compute_ns=row["compute_ns"],
            metadata=json.loads(row["metadata_json"]),
        )

    def get(self, key: CacheKey, *, now: float | None = None) -> StoreLookup | None:
        observed_at = self._clock() if now is None else now
        connection = self._connect()
        row = connection.execute(
            """
            SELECT e.*, b.payload, b.codec, b.compressed,
                   b.raw_size_bytes, b.size_bytes
              FROM cache_entries e
              JOIN cache_blobs b ON b.digest = e.value_digest
             WHERE e.key_digest = ?
            """,
            (key.digest,),
        ).fetchone()
        if row is None:
            with self._stats_lock:
                self._stats.misses += 1
            return None
        stale_until = row["stale_until"]
        expires_at = row["expires_at"]
        fresh = expires_at is None or observed_at < expires_at
        stale_servable = stale_until is not None and observed_at < stale_until
        if not fresh and not stale_servable:
            self._delete_keys(connection, [key.digest])
            with self._stats_lock:
                self._stats.expirations += 1
                self._stats.misses += 1
            return None
        tags = tuple(
            item["tag"]
            for item in connection.execute(
                "SELECT tag FROM cache_tags WHERE key_digest=? ORDER BY tag",
                (key.digest,),
            ).fetchall()
        )
        if row["accessed_at"] < observed_at - self._touch_interval:
            connection.execute(
                "UPDATE cache_entries SET accessed_at=? WHERE key_digest=?",
                (observed_at, key.digest),
            )
        record = self._row_to_record(row, tags)
        with self._stats_lock:
            self._stats.hits += 1
            self._stats.l2_hits += 1
            self._stats.bytes_read += record.size_bytes
            if not fresh:
                self._stats.stale_hits += 1
        return StoreLookup(record=record, tier=self.name, stale=not fresh)

    def put(self, record: CacheRecord) -> bool:
        connection = self._connect()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                INSERT OR IGNORE INTO cache_blobs(
                    digest, payload, codec, compressed, raw_size_bytes, size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.value_digest,
                    record.payload,
                    record.codec,
                    int(record.compressed),
                    record.raw_size_bytes,
                    record.size_bytes,
                ),
            )
            connection.execute(
                """
                INSERT INTO cache_entries(
                    key_digest, algorithm, namespace, method, version,
                    canonical_size, value_digest, created_at, expires_at,
                    stale_until, accessed_at, compute_ns, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_digest) DO UPDATE SET
                    algorithm=excluded.algorithm,
                    namespace=excluded.namespace,
                    method=excluded.method,
                    version=excluded.version,
                    canonical_size=excluded.canonical_size,
                    value_digest=excluded.value_digest,
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at,
                    stale_until=excluded.stale_until,
                    accessed_at=excluded.accessed_at,
                    compute_ns=excluded.compute_ns,
                    metadata_json=excluded.metadata_json
                """,
                (
                    record.key.digest,
                    record.key.algorithm,
                    record.key.namespace,
                    record.key.method,
                    record.key.version,
                    record.key.canonical_size,
                    record.value_digest,
                    record.created_at,
                    record.expires_at,
                    record.stale_until,
                    record.created_at,
                    record.compute_ns,
                    json.dumps(record.metadata, sort_keys=True, separators=(",", ":")),
                ),
            )
            connection.execute(
                "DELETE FROM cache_tags WHERE key_digest=?", (record.key.digest,)
            )
            connection.executemany(
                "INSERT OR IGNORE INTO cache_tags(tag, key_digest) VALUES(?, ?)",
                [(tag, record.key.digest) for tag in record.tags],
            )
            self._evict_to_capacity(connection)
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        with self._stats_lock:
            self._stats.stores += 1
            self._stats.bytes_written += record.size_bytes
        return True

    def _delete_keys(self, connection: sqlite3.Connection, keys: list[str]) -> int:
        if not keys:
            return 0
        placeholders = ",".join("?" for _ in keys)
        connection.execute(
            f"DELETE FROM cache_entries WHERE key_digest IN ({placeholders})", keys
        )
        connection.execute(
            "DELETE FROM cache_blobs WHERE digest NOT IN "
            "(SELECT DISTINCT value_digest FROM cache_entries)"
        )
        return len(keys)

    def _evict_to_capacity(self, connection: sqlite3.Connection) -> None:
        while True:
            total = connection.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM cache_blobs"
            ).fetchone()["total"]
            if total <= self._max_bytes:
                break
            victim = connection.execute(
                "SELECT key_digest FROM cache_entries ORDER BY accessed_at ASC LIMIT 1"
            ).fetchone()
            if victim is None:
                break
            self._delete_keys(connection, [victim["key_digest"]])
            with self._stats_lock:
                self._stats.evictions += 1

    def invalidate(
        self,
        *,
        namespace: str | None = None,
        method: str | None = None,
        tags: Iterable[str] = (),
    ) -> int:
        connection = self._connect()
        clauses: list[str] = []
        parameters: list[object] = []
        if namespace is not None:
            clauses.append("e.namespace=?")
            parameters.append(namespace)
        if method is not None:
            clauses.append("e.method=?")
            parameters.append(method)
        tag_list = tuple(tags)
        if tag_list:
            placeholders = ",".join("?" for _ in tag_list)
            clauses.append(
                "e.key_digest IN (SELECT key_digest FROM cache_tags "
                f"WHERE tag IN ({placeholders}))"
            )
            parameters.extend(tag_list)
        where = " AND ".join(clauses) if clauses else "1=1"
        keys = [
            row["key_digest"]
            for row in connection.execute(
                f"SELECT e.key_digest FROM cache_entries e WHERE {where}", parameters
            ).fetchall()
        ]
        connection.execute("BEGIN IMMEDIATE")
        try:
            removed = self._delete_keys(connection, keys)
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        with self._stats_lock:
            self._stats.invalidations += removed
        return removed

    def clear(self, *, reset_stats: bool = False) -> int:
        connection = self._connect()
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM cache_entries"
        ).fetchone()["n"]
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute("DELETE FROM cache_entries")
            connection.execute("DELETE FROM cache_blobs")
            connection.execute("DELETE FROM cache_leases")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        with self._stats_lock:
            if reset_stats:
                self._stats = MutableCacheInfo()
            else:
                self._stats.invalidations += count
        return count

    def info(self) -> CacheInfo:
        connection = self._connect()
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM cache_entries"
        ).fetchone()["n"]
        with self._stats_lock:
            return self._stats.freeze(currsize=count, maxsize=0)

    def acquire_lease(self, key_digest: str, owner: str, lease_seconds: float) -> bool:
        connection = self._connect()
        now = self._clock()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "DELETE FROM cache_leases WHERE key_digest=? AND expires_at<=?",
                (key_digest, now),
            )
            connection.execute(
                "INSERT OR IGNORE INTO cache_leases(key_digest, owner, expires_at) "
                "VALUES (?, ?, ?)",
                (key_digest, owner, now + lease_seconds),
            )
            row = connection.execute(
                "SELECT owner FROM cache_leases WHERE key_digest=?", (key_digest,)
            ).fetchone()
            acquired = row is not None and row["owner"] == owner
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        if not acquired:
            with self._stats_lock:
                self._stats.lease_contentions += 1
        return acquired

    def release_lease(self, key_digest: str, owner: str) -> None:
        connection = self._connect()
        connection.execute(
            "DELETE FROM cache_leases WHERE key_digest=? AND owner=?",
            (key_digest, owner),
        )

    def close(self) -> None:
        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()
        for connection in connections:
            try:
                connection.close()
            except sqlite3.Error:
                pass
        if hasattr(self._local, "connection"):
            del self._local.connection


class TieredCacheStore:
    """L1 memory + optional L2 persistence with read promotion."""

    name = "tiered"

    def __init__(
        self,
        memory: MemoryCacheStore,
        persistent: SQLiteCacheStore | None = None,
    ) -> None:
        self.memory = memory
        self.persistent = persistent
        self._stats = MutableCacheInfo()
        self._lock = threading.RLock()

    def get(self, key: CacheKey, *, now: float | None = None) -> StoreLookup | None:
        lookup = self.memory.get(key, now=now)
        if lookup is not None:
            return lookup
        if self.persistent is None:
            return None
        lookup = self.persistent.get(key, now=now)
        if lookup is None:
            return None
        self.memory.put(lookup.record)
        with self._lock:
            self._stats.promotions += 1
        return lookup

    def put(self, record: CacheRecord) -> bool:
        memory_stored = self.memory.put(record)
        persistent_stored = self.persistent.put(record) if self.persistent else False
        return memory_stored or persistent_stored

    def invalidate(
        self,
        *,
        namespace: str | None = None,
        method: str | None = None,
        tags: Iterable[str] = (),
    ) -> int:
        memory_removed = self.memory.invalidate(
            namespace=namespace, method=method, tags=tags
        )
        persistent_removed = (
            self.persistent.invalidate(namespace=namespace, method=method, tags=tags)
            if self.persistent
            else 0
        )
        return max(memory_removed, persistent_removed)

    def clear(self, *, reset_stats: bool = False) -> int:
        memory_removed = self.memory.clear(reset_stats=reset_stats)
        persistent_removed = (
            self.persistent.clear(reset_stats=reset_stats) if self.persistent else 0
        )
        if reset_stats:
            with self._lock:
                self._stats = MutableCacheInfo()
        return max(memory_removed, persistent_removed)

    def info(self) -> CacheInfo:
        memory = self.memory.info()
        persistent = (
            self.persistent.info() if self.persistent is not None else CacheInfo()
        )
        with self._lock:
            local = self._stats.freeze()
        return CacheInfo(
            hits=memory.hits + persistent.hits,
            misses=memory.misses + persistent.misses,
            waits=memory.waits + persistent.waits,
            stores=memory.stores + persistent.stores,
            evictions=memory.evictions + persistent.evictions,
            expirations=memory.expirations + persistent.expirations,
            bypasses=memory.bypasses + persistent.bypasses,
            errors=memory.errors + persistent.errors,
            invalidations=memory.invalidations + persistent.invalidations,
            # The same logical key commonly exists in both tiers. Counting it
            # twice would make capacity and hit-rate evidence misleading.
            currsize=max(memory.currsize, persistent.currsize),
            maxsize=memory.maxsize,
            l1_hits=memory.l1_hits,
            l2_hits=persistent.l2_hits,
            stale_hits=memory.stale_hits + persistent.stale_hits,
            refusals=memory.refusals + persistent.refusals,
            corruptions=memory.corruptions + persistent.corruptions,
            promotions=local.promotions,
            lease_contentions=(memory.lease_contentions + persistent.lease_contentions),
            bytes_read=memory.bytes_read + persistent.bytes_read,
            bytes_written=memory.bytes_written + persistent.bytes_written,
            compute_ns=memory.compute_ns + persistent.compute_ns,
        )

    def acquire_lease(self, key_digest: str, owner: str, lease_seconds: float) -> bool:
        target: CacheStore = self.persistent or self.memory
        return target.acquire_lease(key_digest, owner, lease_seconds)

    def release_lease(self, key_digest: str, owner: str) -> None:
        target: CacheStore = self.persistent or self.memory
        target.release_lease(key_digest, owner)

    def close(self) -> None:
        self.memory.close()
        if self.persistent is not None:
            self.persistent.close()
