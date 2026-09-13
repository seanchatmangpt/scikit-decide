# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Governed cache fabric for planning, RL, and scheduling.

The public module intentionally remains small. The implementation lives in
``autofde_lab._cache`` and provides:

* deterministic, typed, content-addressed keys;
* mutation-isolated values with digest verification and compression;
* byte-bounded TinyLFU/segmented-LRU memory caching;
* persistent SQLite/WAL storage with content deduplication;
* thread and process single-flight construction leases;
* dependency tags, explicit invalidation, receipts, and replay;
* transparent domain proxies and pickle-safe solver domain factories;
* policy-as-code admission and data-classification TTL ceilings;
* per-tenant rate, concurrency, and in-flight byte quotas;
* deterministic canary, verification, kill-switch, and circuit-breaker modes;
* signed attestations, hash-chained provenance, SLOs, and quarantine evidence.

Only explicitly admitted deterministic operations are cacheable. State
actuation, random sampling, rendering, external I/O, and implicit mutable-memory
queries remain outside the cache. The enterprise gateway adds deployment
identity, release/model/data fingerprints, persistent-storage governance, and
production invalidation controls without changing the base ``CacheFabric`` API.
"""

from autofde_lab import _cache as _implementation
from autofde_lab._cache import *

__all__ = _implementation.__all__
