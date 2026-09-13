from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from autofde_lab._cache.enterprise import (
    CacheFailureMode,
    EnterpriseCacheGateway,
    EnterpriseGatewayConfig,
)
from autofde_lab._cache.governance import (
    CacheGovernanceError,
    DataClassification,
    EnterpriseContext,
    GovernancePolicy,
    NamespaceRule,
    PolicyEngine,
)
from autofde_lab._cache.observability import (
    ObserverFailurePolicy,
    ReceiptFanout,
    SLOTargets,
    SLOTracker,
)
from autofde_lab._cache.provenance import (
    AttestationKeyring,
    AttestationSigner,
    CacheAttestation,
    ProvenanceLedger,
)
from autofde_lab._cache.quarantine import QuarantineJournal
from autofde_lab._cache.quotas import QuotaExceededError, QuotaManager, QuotaSpec
from autofde_lab._cache.rollout import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    RolloutController,
    RolloutPolicy,
)
from autofde_lab._cache.types import (
    CacheCorruptionError,
    CacheMode,
    CacheResult,
    MethodPolicy,
)


def context(**overrides):
    values = {
        "tenant": "flight-controls",
        "application": "optimizer",
        "environment": "prod",
        "release_id": "r26.8.5",
        "model_fingerprint": "model-a1",
        "data_fingerprint": "data-b2",
        "classification": DataClassification.INTERNAL,
        "actor": "solver-worker",
        "change_ticket": "CHG-1234",
    }
    values.update(overrides)
    return EnterpriseContext(**values)


def engine(*, persistence=True):
    policy = GovernancePolicy(
        rules=(
            NamespaceRule(
                namespace_pattern="flight-controls/optimizer/prod/*",
                allow_persistence=persistence,
            ),
        )
    )
    return PolicyEngine(policy)


@pytest.mark.parametrize(
    ("classification", "ttl", "stale", "persistent"),
    [
        (DataClassification.PUBLIC, 7 * 86400, True, True),
        (DataClassification.INTERNAL, 86400, True, True),
        (DataClassification.CONFIDENTIAL, 3600, True, True),
        (DataClassification.RESTRICTED, 300, False, False),
    ],
)
def test_classification_policy(classification, ttl, stale, persistent):
    decision = (
        engine(persistence=persistent)
        .evaluate(
            context=context(classification=classification),
            namespace="flight-controls/optimizer/prod/model",
            method="evaluate",
            persistent_enabled=False,
        )
        .require()
    )
    assert decision.max_ttl_seconds == ttl
    assert decision.allow_stale_if_error is stale
    assert decision.allow_persistence is persistent
    assert len(decision.policy_digest) == 64


def test_namespace_binding_refuses_cross_tenant_access():
    decision = engine().evaluate(
        context=context(),
        namespace="other/optimizer/prod/model",
        method="evaluate",
        persistent_enabled=True,
    )
    with pytest.raises(CacheGovernanceError):
        decision.require()


def test_production_invalidation_requires_change_ticket():
    policy = engine()
    policy.authorize_invalidation(context=context(), reason="new model")
    with pytest.raises(CacheGovernanceError):
        policy.authorize_invalidation(
            context=context(change_ticket=None),
            reason="new model",
        )


def test_quota_enforces_rate_concurrency_and_bytes():
    now = [0.0]
    rate = QuotaManager(
        QuotaSpec(requests_per_second=1, burst=1),
        monotonic=lambda: now[0],
    )
    with rate.admit("a"):
        pass
    with pytest.raises(QuotaExceededError, match="rate"):
        with rate.admit("a"):
            pass
    now[0] = 1.0
    with rate.admit("a"):
        pass

    bounded = QuotaManager(
        QuotaSpec(
            requests_per_second=100,
            burst=10,
            max_concurrent=1,
            max_inflight_estimated_bytes=10,
        ),
        monotonic=lambda: now[0],
    )
    with bounded.admit("a", estimated_bytes=10):
        with pytest.raises(QuotaExceededError, match="concurrency"):
            with bounded.admit("a"):
                pass
    with pytest.raises(QuotaExceededError, match="byte"):
        with bounded.admit("b", estimated_bytes=11):
            pass


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (RolloutPolicy(kill_switch=True), CacheMode.BYPASS),
        (RolloutPolicy(enabled_percent=100, verify_percent=100), CacheMode.VERIFY),
    ],
)
def test_rollout_modes_are_deterministic(policy, expected):
    controller = RolloutController(policy)
    first = controller.mode_for(identity="subject", breaker_key="namespace")
    second = controller.mode_for(identity="subject", breaker_key="namespace")
    assert first is second is expected


def test_circuit_breaker_opens_and_recovers_half_open():
    now = [0.0]
    breaker = CircuitBreaker(
        CircuitBreakerConfig(
            failure_threshold=2,
            recovery_seconds=10,
            half_open_max_calls=1,
        ),
        monotonic=lambda: now[0],
    )
    breaker.record_failure("x")
    breaker.record_failure("x")
    assert breaker.snapshot("x").state is CircuitState.OPEN
    assert not breaker.allow("x")
    now[0] = 11
    assert breaker.allow("x")
    assert not breaker.allow("x")
    breaker.record_success("x")
    assert breaker.snapshot("x").state is CircuitState.CLOSED


def attestation(observed_at=1.0):
    return CacheAttestation(
        subject_id="tenant/app/prod/worker",
        namespace="tenant/app/prod/model",
        method="evaluate",
        key_digest="a" * 64,
        value_digest="b" * 64,
        disposition="miss_stored",
        policy_digest="c" * 64,
        release_id="release-1",
        model_fingerprint="model-1",
        data_fingerprint="data-1",
        rollout_reason="normal",
        rollout_cohort=42.0,
        observed_at=observed_at,
        owner="worker-1",
    )


def test_key_rotation_preserves_historical_ledger_verification(tmp_path: Path):
    old = AttestationSigner(b"o" * 32, key_id="old")
    new = AttestationSigner(b"n" * 32, key_id="new")
    path = tmp_path / "ledger.jsonl"
    ProvenanceLedger(path, signer=old, fsync=False).append(attestation())
    rotated = ProvenanceLedger(
        path,
        signer=new,
        keyring=AttestationKeyring((old, new)),
        fsync=False,
    )
    rotated.append(dataclasses.replace(attestation(), observed_at=2.0))
    result = rotated.verify()
    assert result.valid and result.records == 2


def test_ledger_detects_tampering(tmp_path: Path):
    signer = AttestationSigner(b"k" * 32, key_id="k1")
    path = tmp_path / "ledger.jsonl"
    ledger = ProvenanceLedger(path, signer=signer, fsync=False)
    ledger.append(attestation())
    record = json.loads(path.read_text())
    record["signed_attestation"]["attestation"]["release_id"] = "tampered"
    path.write_text(json.dumps(record) + "\n")
    assert not ledger.verify().valid


def test_multiple_processes_append_one_valid_ledger(tmp_path: Path):
    path = tmp_path / "shared.jsonl"
    script = textwrap.dedent(
        """
        import sys
        from autofde_lab._cache.provenance import (
            AttestationSigner, CacheAttestation, ProvenanceLedger,
        )
        path, worker = sys.argv[1], sys.argv[2]
        ledger = ProvenanceLedger(
            path,
            signer=AttestationSigner(b'p' * 32, key_id='shared'),
            fsync=False,
        )
        for index in range(10):
            ledger.append(CacheAttestation(
                subject_id=worker,
                namespace='tenant/app/prod/model',
                method='evaluate',
                key_digest=f'{worker}-{index}',
                value_digest='v',
                disposition='miss_stored',
                policy_digest='p',
                release_id='r',
                model_fingerprint='m',
                data_fingerprint='d',
                rollout_reason='normal',
                rollout_cohort=1.0,
                observed_at=float(index),
                owner=worker,
            ))
        """
    )
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = "src"
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(path), f"w{index}"],
            cwd=Path(__file__).parents[1],
            env=env,
        )
        for index in range(3)
    ]
    assert [worker.wait() for worker in workers] == [0, 0, 0]
    signer = AttestationSigner(b"p" * 32, key_id="shared")
    result = ProvenanceLedger(path, signer=signer, fsync=False).verify()
    assert result.valid and result.records == 30


def test_quarantine_rotates_without_copying_payloads(tmp_path: Path):
    journal = QuarantineJournal(
        tmp_path / "quarantine.jsonl",
        max_bytes=1024,
        max_files=2,
        fsync=False,
    )
    for index in range(20):
        journal.record(
            subject_id="tenant/app/prod/worker",
            namespace="tenant/app/prod/model",
            method="evaluate",
            error=CacheCorruptionError("bad payload"),
            action="bypass",
            attributes={"attempt": str(index)},
        )
    assert journal.path.exists()
    assert journal.path.with_suffix(".jsonl.1").exists()
    assert "payload" not in journal.events(limit=1)[0].to_dict()


def test_observer_isolation_and_slo_window():
    observed = []

    def broken(_receipt):
        raise RuntimeError("metrics unavailable")

    fanout = ReceiptFanout(
        (observed.append, broken),
        failure_policy=ObserverFailurePolicy.COLLECT,
    )
    receipt = SimpleNamespace(
        disposition=SimpleNamespace(value="hit_l1"),
        load_ns=1_000_000,
        compute_ns=5_000_000,
        error_type=None,
    )
    fanout(receipt)
    tracker = SLOTracker(
        SLOTargets(
            minimum_hit_rate=1,
            maximum_error_rate=0,
            maximum_p95_load_ms=2,
            maximum_p95_compute_ms=10,
        )
    )
    tracker.observe(receipt)
    assert len(observed) == 1
    assert fanout.errors() == ("RuntimeError: metrics unavailable",)
    assert tracker.snapshot().compliant


@dataclasses.dataclass
class FakeReceipt:
    key_digest: str = "a" * 64
    value_digest: str | None = "b" * 64
    disposition: object = dataclasses.field(
        default_factory=lambda: SimpleNamespace(value="miss_stored")
    )
    observed_at: float = 1.0
    owner: str = "fake-owner"
    load_ns: int = 0
    compute_ns: int = 1
    error_type: str | None = None


class FakeFabric:
    def __init__(self, *, error=None, persistent_path=None):
        self.config = SimpleNamespace(persistent_path=persistent_path)
        self.error = error
        self.calls = []
        self.invalidations = []

    def execute_with_receipt(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None and kwargs["mode"] is not CacheMode.BYPASS:
            raise self.error
        return CacheResult(value=kwargs["compute"](), receipt=FakeReceipt())

    def invalidate(self, **kwargs):
        self.invalidations.append(kwargs)
        return 7

    def info(self):
        return {"currsize": 3}


def gateway(tmp_path: Path, fabric: FakeFabric, **config):
    signer = AttestationSigner(b"s" * 32, key_id="enterprise")
    return EnterpriseCacheGateway(
        fabric,
        policy_engine=engine(),
        ledger=ProvenanceLedger(
            tmp_path / "attestations.jsonl",
            signer=signer,
            fsync=False,
        ),
        quarantine=QuarantineJournal(
            tmp_path / "quarantine.jsonl",
            fsync=False,
        ),
        slo_tracker=SLOTracker(SLOTargets(minimum_hit_rate=0)),
        config=EnterpriseGatewayConfig(**config),
    )


def test_gateway_clamps_policy_injects_identity_and_attests(tmp_path: Path):
    fabric = FakeFabric()
    managed = gateway(tmp_path, fabric)
    result = managed.execute_with_receipt(
        context=context(),
        namespace="flight-controls/optimizer/prod/model",
        method="evaluate",
        compute=lambda: 42,
        policy=MethodPolicy(
            ttl_seconds=10 * 86400,
            stale_if_error_seconds=60,
        ),
        tags=("scenario:1",),
    )
    assert result.value == 42
    call = fabric.calls[0]
    assert call["policy"].ttl_seconds == 86400
    assert "tenant:flight-controls" in call["tags"]
    assert call["metadata"]["autofde_lab.enterprise.release_id"] == "r26.8.5"
    assert managed.health().ledger_records == 1


def test_gateway_bypasses_only_typed_cache_failures(tmp_path: Path):
    fabric = FakeFabric(error=CacheCorruptionError("bad payload"))
    managed = gateway(
        tmp_path,
        fabric,
        failure_mode=CacheFailureMode.BYPASS,
    )
    assert (
        managed.execute(
            context=context(),
            namespace="flight-controls/optimizer/prod/model",
            method="evaluate",
            compute=lambda: 9,
        )
        == 9
    )
    assert [call["mode"] for call in fabric.calls] == [
        CacheMode.NORMAL,
        CacheMode.BYPASS,
    ]
    assert managed.health().quarantine_events == 1

    class UserFailureFabric(FakeFabric):
        def execute_with_receipt(self, **kwargs):
            return CacheResult(value=kwargs["compute"](), receipt=FakeReceipt())

    user = gateway(
        tmp_path / "user",
        UserFailureFabric(),
        failure_mode=CacheFailureMode.BYPASS,
    )
    with pytest.raises(OSError, match="domain I/O failed"):
        user.execute(
            context=context(),
            namespace="flight-controls/optimizer/prod/model",
            method="evaluate-io",
            compute=lambda: (_ for _ in ()).throw(OSError("domain I/O failed")),
        )


def test_gateway_governs_invalidation_and_refuses_metadata_spoofing(tmp_path: Path):
    fabric = FakeFabric()
    managed = gateway(tmp_path, fabric)
    removed = managed.invalidate(
        context=context(),
        reason="new model",
        namespace="flight-controls/optimizer/prod/model",
    )
    assert removed == 7
    assert "tenant:flight-controls" in fabric.invalidations[0]["tags"]
    with pytest.raises(ValueError, match="reserved enterprise metadata"):
        managed.execute(
            context=context(),
            namespace="flight-controls/optimizer/prod/model",
            method="evaluate",
            compute=lambda: 1,
            metadata={"autofde_lab.enterprise.release_id": "spoofed"},
        )
