# Capability cache fabric

`autofde_lab.caching` is a multi-tier cache fabric for deterministic planning,
reinforcement-learning, scheduling, self-play, and solver-support computations.
It is not a decorator collection and it is not a cache hidden inside one solver.
It sits at the capability boundary shared by domain factories, solver workers,
and repeated runs.

## Why this architecture exists

Scikit-decide solvers repeatedly ask equivalent domain questions:

- Which actions are applicable in this state?
- What state follows this state/action pair?
- What is the transition value?
- Is the state terminal or a goal?
- What are the static task, mode, resource, precedence, skill, and time-window
  descriptions?
- Has this self-play scenario or deterministic transformation already been
  evaluated?

A solver-local dictionary only eliminates duplicate work inside one process and
one algorithm. It cannot reuse work across solver instances, parallel workers,
notebooks, CLI invocations, MCP/A2A calls, or later runs. It also has no lawful
answer for invalidation, mutation, cache poisoning, stampedes, or replay.

The cache fabric treats reuse as a first-class system:

```text
call
  -> explicit admission
  -> canonical typed input
  -> content-addressed computation key
  -> L1 lookup
  -> L2 lookup / promotion
  -> thread single-flight
  -> process lease
  -> construction
  -> value serialization + digest
  -> L1/L2 store
  -> receipt
  -> replay / invalidation
```

## 80/20 ERRC

| Move | System effect |
|---|---|
| **Eliminate** | Duplicate model evaluation across algorithms, domain copies, threads, processes, and runs. Remove solver-specific memoization as the default architecture. |
| **Reduce** | Content-address values to deduplicate storage. Compress large payloads. Bound L1 by entries and bytes. Bound L2 by bytes. Use TinyLFU admission, segmented LRU, WAL, and touch coalescing to reduce churn and write amplification. |
| **Raise** | Make cache admission, versioning, TTL, stale-if-error, copy isolation, verification, dependency tags, invalidation, leases, counters, and corruption detection explicit. |
| **Create** | A shared capability cache fabric with replayable receipts, persistent cross-run reuse, solver-domain-factory integration, and a generic deterministic artifact cache for self-play and generated intermediate results. |

## Tiers

### L1: TinyLFU + segmented LRU memory

`MemoryCacheStore` is bounded by both entry count and encoded bytes.

New records enter a probation segment. Repeatedly used records are promoted into
a protected segment. When the cache is full, lightweight frequency evidence
prevents a one-hit scan from evicting a genuinely hot record.

Values are stored encoded rather than as a live Python object graph. Each hit
reconstructs an isolated value, so one caller cannot mutate the cached value seen
by another caller.

### L2: SQLite/WAL persistent CAS

`SQLiteCacheStore` provides:

- cross-process and cross-run reuse;
- WAL mode and bounded busy waits;
- content-addressed blob deduplication;
- atomic entry, tag, and lease updates;
- namespace, method, and dependency-tag invalidation;
- strict TTL plus optional stale-if-error retention;
- LRU-oriented byte-capacity eviction;
- orphaned-blob reclamation;
- process-safe compute leases.

The persistent file is a trusted local artifact. The default codec uses pickle
because scikit-decide model values include arbitrary Python domain objects.
Never open a cache database supplied by an untrusted party.

### Tier promotion

`TieredCacheStore` checks L1 first, then L2. An L2 hit is promoted into L1. A
newly constructed record is offered to both tiers. A record too large or too
cold for L1 can still remain in L2.

## Identity and admission

A cache entry is not identified by `repr()`, object identity, or Python's ambient
`hash()`. The key binds:

```text
key schema
+ admitted namespace
+ operation name
+ operation version
+ canonical typed arguments
```

Supported canonical values include nested mappings, lists, tuples, sets,
dataclasses, enums, paths, dates, decimals, fractions, UUIDs, ranges, slices,
NumPy arrays/scalars, bytes, and primitives.

Domain-specific objects must provide one of:

```python
class State:
    def __cache_key__(self):
        return (self.position, self.inventory, self.clock)
```

or a method policy projection:

```python
policy = MethodPolicy(
    version="transition-v4",
    key_fn=lambda args, kwargs: (
        args[0].stable_id,
        args[1].stable_id,
    ),
)
```

Unsupported objects bypass by default or raise `UnhashableCacheKeyError` when
`on_unhashable="raise"`.

### Namespace rule

Cross-instance reuse is an assertion that two domain instances represent the
same admitted model. Therefore:

- `cache_domain(domain)` without a namespace uses an instance-local namespace;
- `cache_domain_factory(...)` requires an explicit namespace;
- persistent reuse should always use a versioned namespace such as
  `warehouse-routing:map-sha256:policy-v3`.

A namespace change is a cheap, complete invalidation boundary.

## Safety fence

The cache refuses private methods and sampling families. The supplied policies
also exclude:

- `reset`
- `step`
- `sample*`
- `set_memory`
- `render`
- `close`
- scheduling graph construction that can sample durations

Methods such as `get_applicable_actions()` can silently read mutable
`domain._memory` when `memory` is omitted. Those calls are receipted as bypasses.
Pass memory explicitly to admit reuse.

Exceptions are not cached. `None` is cacheable by default but can be excluded.

## Basic domain use

```python
from autofde_lab.caching import CachePolicy, cache_domain

cached = cache_domain(
    domain,
    policy=CachePolicy.model(),
    namespace="maze:layout-8f44:model-v2",
)

first = cached.get_next_state(state, action)   # construct + store
second = cached.get_next_state(state, action)  # L1 hit

print(cached.cache_info())
print(cached.cache_fabric.last_receipt.to_json())
```

`CachedDomain` uses `wrapt.ObjectProxy`, preserving `__class__` and the mixin/MRO
capability checks used by `Solver.check_domain()`.

## Solver factory use

Solvers receive domain factories, not domain instances. Wrap the factory so all
domain copies share one namespace and fabric:

```python
from pathlib import Path

from autofde_lab.caching import (
    CacheConfig,
    CachePolicy,
    cache_domain_factory,
)

cached_factory = cache_domain_factory(
    domain_factory,
    policy=CachePolicy.scheduling(),
    namespace="rcpsp:j120-instance-17:model-v5",
    config=CacheConfig(
        memory_max_entries=100_000,
        memory_max_bytes=512 * 1024 * 1024,
        persistent_path=Path(".cache/autofde_lab/rcpsp.sqlite3"),
        persistent_max_bytes=64 * 1024 * 1024 * 1024,
    ),
)

with MySolver(domain_factory=cached_factory) as solver:
    solver.solve()
```

The factory is pickle-safe. Each worker process receives its own L1 tier and
SQLite connection while sharing the L2 database and process leases.

## Generic self-play and artifact caching

The fabric is not limited to domain methods:

```python
from autofde_lab.caching import CacheFabric, CacheConfig, MethodPolicy

fabric = CacheFabric(
    CacheConfig(persistent_path=".cache/autofde_lab/self-play.sqlite3")
)

result = fabric.execute(
    namespace="warehouse-self-play:corpus-v7",
    method="evaluate_scenario",
    args=(scenario,),
    compute=lambda: run_scenario(scenario),
    policy=MethodPolicy(
        version="evaluator-v12",
        ttl_seconds=None,
        static_tags=("self-play", "training-corpus"),
    ),
    tags=(f"scenario-family:{scenario.family}",),
)
```

This same surface can cache normalized PDDL/PPDDL parsing, deterministic
translations, heuristic tables, compiled model artifacts, solver preprocessing,
and other lawful intermediate products.

## Method-specific policy

```python
from autofde_lab.caching import CachePolicy, MethodPolicy

policy = CachePolicy.model().with_method_policy(
    "get_next_state_distribution",
    MethodPolicy(
        version="dynamics-v9",
        ttl_seconds=3600,
        stale_if_error_seconds=300,
        key_fn=lambda args, kwargs: (
            args[0].__cache_key__(),
            args[1].__cache_key__(),
        ),
        tag_fn=lambda args, kwargs: (
            f"state-region:{args[0].region}",
        ),
    ),
)
```

Version changes prevent stale reuse after semantics change. Tags support
selective invalidation when one scenario family, resource calendar, map region,
or generated model changes.

## Explicit modes

```python
from autofde_lab.caching import CacheMode

# Ignore existing values and replace the record.
with fabric.mode(CacheMode.REFRESH):
    value = compute_through_fabric()

# Compute without reading or writing the cache.
with fabric.mode(CacheMode.BYPASS):
    value = compute_through_fabric()

# Recompute and compare the value digest. Drift replaces the record.
with fabric.mode(CacheMode.VERIFY):
    value = compute_through_fabric()

# Never construct on a miss.
with fabric.mode(CacheMode.READ_ONLY):
    value = compute_through_fabric()
```

No background refresh thread exists. Every mode has an observed execution path
and an emitted receipt.

## Stampede control

Two independent boundaries prevent duplicate construction:

1. A per-key thread flight coalesces concurrent requests in one process.
2. A SQLite lease elects one constructor across processes.

A waiter polls for the newly stored record until `lease_wait_seconds`. On
expiration, policy chooses either bounded duplicate computation or a typed
`CacheLeaseTimeoutError`.

## Stale-if-error

Strict TTL entries are never treated as fresh after expiration. A method can
retain an expired record for a separate stale-if-error window:

```python
MethodPolicy(
    ttl_seconds=60,
    stale_if_error_seconds=300,
)
```

The stale value is served only after the live computation fails. The receipt is
`stale_if_error` and records the exception type. This is opt-in because stale
planning data can be semantically unsafe.

## Receipts and replay

Every decision emits `CacheReceipt` with:

- computation key digest;
- value digest;
- namespace, method, and version;
- disposition and source tier;
- creation and expiration timestamps;
- compute and load durations;
- encoded size;
- owner/process identity;
- verification state;
- dependency tags;
- error type for stale-if-error.

```python
receipt = fabric.last_receipt
replayed = fabric.replay(receipt.key_digest)
fabric.export_receipts("artifacts/cache-receipts.jsonl")
```

Replay verifies the stored value digest before decoding.

## Invalidation

```python
fabric.invalidate(namespace="warehouse:v4")
fabric.invalidate(namespace="warehouse:v4", method="get_next_state")
fabric.invalidate(tags=("scenario-family:loading-dock",))
fabric.clear()
```

Invalidation applies to both tiers. Content blobs no longer referenced by any
entry are reclaimed from SQLite.

## Observability

`fabric.info()` reports logical and resource counters:

- hits, L1 hits, L2 hits, misses, waits;
- stores, evictions, expirations, promotions;
- bypasses, refusals, errors, stale hits;
- lease contention and invalidation;
- bytes read and written;
- cumulative construction time;
- current L1/L2 entry count.

Receipts answer individual decisions; counters answer aggregate behavior.

## Operational recommendations

1. Version the namespace from the domain/model identity, not a human-friendly
   mutable name alone.
2. Version each method when its semantics or serialization changes.
3. Use explicit state and action projections for large object graphs.
4. Tag records by the smallest meaningful invalidation dependency.
5. Keep random draws and state actuation outside the cache.
6. Run `VERIFY` against a bounded sample after model or codec changes.
7. Put persistent cache files on local SSD for solver workers; SQLite WAL is not
   intended as a network-distributed database.
8. Use separate databases or namespaces for incompatible trust and lifecycle
   boundaries.
9. Treat the database as trusted-local because the default codec is pickle.
10. Export receipts for benchmark, release, and reproducibility runs.

## Verified behavior

The focused test suite covers:

- typed canonical keys and NumPy values;
- unsupported and recursive input refusal;
- compression, digest verification, and mutation isolation;
- byte/entry capacity, TinyLFU admission, SLRU promotion, and TTL;
- SQLite persistence, WAL, CAS deduplication, tag cleanup, and leases;
- L2-to-L1 promotion;
- thread and real subprocess single-flight behavior;
- stale-if-error, refresh, bypass, verify, and read-only modes;
- persistent corruption detection;
- receipt export and replay;
- namespace/method/tag invalidation;
- transparent domain capability identity;
- implicit-memory bypass and actuation exclusion;
- pickle-safe domains and domain factories;
- 1,000-call self-play reuse over 20 unique scenario topologies.
