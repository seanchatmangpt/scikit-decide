# Enterprise cache control plane

The cache fabric can now operate as a governed company capability rather than a
process-local optimization. Existing `CacheFabric`, `CachedDomain`, and
`CachedDomainFactory` callers remain valid. Teams requiring governed cross-service
reuse place `EnterpriseCacheGateway` around a fabric.

## Control path

```text
request identity
  -> policy-as-code admission
  -> tenant quota
  -> deterministic rollout / circuit breaker
  -> CacheFabric L1 + L2
  -> signed provenance, SLOs, quarantine evidence
```

## Added capabilities

### Policy and data classification

`GovernancePolicy` is immutable and content-addressed. `PolicyEngine` evaluates a
request before key construction or user computation. It binds namespaces to
`tenant/application/environment`, enforces allow rules, clamps TTL, controls
persistence and stale-on-error, protects enterprise metadata, emits mandatory
identity tags, and requires a change ticket for production invalidation.

Default TTL ceilings are seven days for public data, 24 hours for internal data,
one hour for confidential data, and five minutes for restricted data. Restricted
persistence and stale-on-error are refused by default.

### Multi-tenant fairness

`QuotaManager` provides an independent token bucket, burst limit, concurrency
limit, and in-flight estimated-byte envelope per tenant. Admission fails before
computation, preventing one solver fleet from consuming another tenant's budget.

### Safe rollout and containment

`RolloutController` uses stable salted BLAKE2b cohorts for percentage rollout and
verification. It supports forced modes and a global kill switch. Per-namespace
circuit breakers transition through closed, open, and half-open states. A bypass
caused by an open breaker does not falsely count as recovery.

### Signed evidence and key rotation

`AttestationSigner` produces HMAC-SHA256 attestations binding subject, namespace,
method, computation/value digests, policy digest, release/model/data fingerprints,
rollout decision, observation time, and owner. `ProvenanceLedger` appends them to a
sequence-checked, hash-chained JSONL ledger with flush and optional fsync.

`AttestationKeyring` allows a new active signing key while retaining historical
keys only for verification. `InterProcessFileLock` serializes ledger and quarantine
writes using POSIX `flock` or Windows `msvcrt` locking with bounded acquisition.
HMAC authenticates evidence; it does not encrypt cached values.

### Failure handling and SLOs

`QuarantineJournal` records metadata-only dead-letter evidence and rotates by byte
size and file count. Values and computation arguments are never copied into it.
`ReceiptFanout isolates metrics, tracing, logging, and audit observers under an
explicit ignore/collect/raise policy. `SLOTracker` evaluates hit rate, error rate,
p95 load latency, and p95 compute latency over a bounded receipt window.

Fail-open mode applies only to typed cache infrastructure failures such as payload
corruption and lease timeout. User computation exceptions and ambiguous operating-
system errors remain fail-closed and are never recomputed.

## Governed execution

```python
from pathlib import Path
from autofde_lab.caching import (
    AttestationSigner,
    CacheConfig,
    CacheFabric,
    DataClassification,
    EnterpriseCacheGateway,
    EnterpriseContext,
    GovernancePolicy,
    PolicyEngine,
    ProvenanceLedger,
)

fabric = CacheFabric(CacheConfig(persistent_path=Path("/var/cache/app/cache.sqlite")))
signer = AttestationSigner(secret_from_vault, key_id="cache-attest-2026-08")
gateway = EnterpriseCacheGateway(
    fabric,
    policy_engine=PolicyEngine(GovernancePolicy.company_default()),
    ledger=ProvenanceLedger("/var/log/app/cache-attestations.jsonl", signer=signer),
)
context = EnterpriseContext(
    tenant="flight-controls",
    application="optimizer",
    environment="prod",
    release_id="optimizer-26.8.5",
    model_fingerprint="model-a1",
    data_fingerprint="navdata-b2",
    classification=DataClassification.INTERNAL,
    actor="solver-worker",
    change_ticket="CHG-1234",
)
value = gateway.execute(
    context=context,
    namespace="flight-controls/optimizer/prod/transition-model",
    method="get_next_state",
    args=(state, action),
    compute=lambda: domain.get_next_state(state, action),
)
```

## Operational standing

The focused verifier covers policy digest stability, classification refusal,
namespace binding, TTL clamping, production invalidation, quotas, deterministic
rollout, kill switch, circuit recovery, signing-key rotation, tamper detection,
concurrent multi-process ledger writes, quarantine rotation, observer isolation,
SLO evaluation, protected metadata, governed invalidation, and typed fail-open
behavior. The GitHub Actions matrix runs on Python 3.10, 3.12, and 3.13 and also
executes the original cache verifier.

Persistent SQLite/pickle remains a trusted-local cache artifact. Signing secrets
must come from a company secret manager. Full repository integration and platform-
specific deployment qualification remain release gates beyond the focused suite.
