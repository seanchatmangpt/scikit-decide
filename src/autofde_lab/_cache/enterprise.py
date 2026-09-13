# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Governed company control plane over :class:`CacheFabric`."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar

from .governance import (
    EnterpriseContext,
    GovernanceDecision,
    PolicyEngine,
)
from .observability import SLOSnapshot, SLOTracker
from .provenance import CacheAttestation, ProvenanceLedger
from .quarantine import QuarantineJournal
from .quotas import QuotaManager, QuotaSnapshot
from .rollout import RolloutController, RolloutDecision

# Superseded spellings of `EnterpriseGatewayConfig.reserved_metadata_prefix`.
# Read-side only: never emitted, always rejected as caller-supplied keys.
LEGACY_RESERVED_METADATA_PREFIXES: tuple[str, ...] = ("skdecide.enterprise.",)
from .types import (
    CacheCorruptionError,
    CacheLeaseTimeoutError,
    CacheMode,
    CacheResult,
    MethodPolicy,
)

__all__ = [
    "CacheFailureMode",
    "EnterpriseCacheGateway",
    "EnterpriseGatewayConfig",
    "EnterpriseHealth",
]

_T = TypeVar("_T")


class _Fabric(Protocol):
    config: Any

    def execute_with_receipt(self, **kwargs: Any) -> CacheResult: ...

    def invalidate(
        self,
        *,
        namespace: str | None = None,
        method: str | None = None,
        tags: Iterable[str] = (),
    ) -> int: ...

    def info(self) -> Any: ...


class CacheFailureMode(str, Enum):
    """Behavior for cache infrastructure failures, never user compute errors."""

    RAISE = "raise"
    BYPASS = "bypass"


@dataclass(frozen=True)
class EnterpriseGatewayConfig:
    persistent_enabled: bool = False
    failure_mode: CacheFailureMode = CacheFailureMode.RAISE
    attest_bypass_results: bool = True
    # Namespace for cache metadata keys the gateway reserves for itself.
    # This value is WRITTEN into persisted ledger records, so the legacy
    # spelling below is not decoration: records produced before the rename
    # still carry `skdecide.enterprise.*` keys, and -- more sharply -- the
    # collision guard in `_metadata` is the read side of this prefix. If it
    # checked only the current value, a caller could supply
    # `skdecide.enterprise.subject_id` and walk straight through a guard
    # whose entire purpose is to keep the reserved namespace reserved. Both
    # are rejected; only this one is emitted.
    reserved_metadata_prefix: str = "autofde_lab.enterprise."

    def __post_init__(self) -> None:
        if not self.reserved_metadata_prefix:
            raise ValueError("reserved_metadata_prefix must be non-empty")


@dataclass(frozen=True)
class EnterpriseHealth:
    policy_digest: str
    cache_info: Any
    slo: SLOSnapshot | None
    quotas: tuple[QuotaSnapshot, ...]
    ledger_valid: bool | None
    ledger_records: int | None
    ledger_error: str | None
    quarantine_events: int


class EnterpriseCacheGateway:
    """Bind cache execution to identity, quotas, rollout, and evidence."""

    _INFRASTRUCTURE_ERRORS = (
        CacheCorruptionError,
        CacheLeaseTimeoutError,
    )

    def __init__(
        self,
        fabric: _Fabric,
        *,
        policy_engine: PolicyEngine,
        quotas: QuotaManager | None = None,
        rollout: RolloutController | None = None,
        ledger: ProvenanceLedger | None = None,
        quarantine: QuarantineJournal | None = None,
        slo_tracker: SLOTracker | None = None,
        config: EnterpriseGatewayConfig | None = None,
    ) -> None:
        self.fabric = fabric
        self.policy_engine = policy_engine
        self.quotas = quotas or QuotaManager()
        self.rollout = rollout or RolloutController()
        self.ledger = ledger
        self.quarantine = quarantine
        self.slo_tracker = slo_tracker
        detected_persistence = (
            getattr(getattr(fabric, "config", None), "persistent_path", None)
            is not None
        )
        self.config = config or EnterpriseGatewayConfig(
            persistent_enabled=detected_persistence
        )
        if detected_persistence and not self.config.persistent_enabled:
            raise ValueError(
                "gateway configuration cannot hide an enabled persistent store"
            )

    def _effective_policy(
        self,
        requested: MethodPolicy | None,
        decision: GovernanceDecision,
    ) -> MethodPolicy:
        policy = requested or MethodPolicy()
        ttl = policy.ttl_seconds
        if ttl is None or ttl > decision.max_ttl_seconds:
            ttl = decision.max_ttl_seconds
        stale = policy.stale_if_error_seconds
        if not decision.allow_stale_if_error:
            stale = 0.0
        return dataclasses.replace(
            policy,
            ttl_seconds=ttl,
            stale_if_error_seconds=stale,
        )

    def _metadata(
        self,
        *,
        context: EnterpriseContext,
        decision: GovernanceDecision,
        supplied: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        prefix = self.config.reserved_metadata_prefix
        metadata = dict(supplied or {})
        guarded = (prefix, *LEGACY_RESERVED_METADATA_PREFIXES)
        collisions = sorted(
            key for key in metadata if str(key).startswith(guarded)
        )
        if collisions:
            raise ValueError(
                "reserved enterprise metadata cannot be supplied by callers: "
                f"{collisions!r}"
            )
        metadata.update(
            {
                prefix + "subject_id": context.subject_id,
                prefix + "release_id": context.release_id,
                prefix + "model_fingerprint": context.model_fingerprint,
                prefix + "data_fingerprint": context.data_fingerprint,
                prefix + "classification": context.classification.value,
                prefix + "policy_digest": decision.policy_digest,
            }
        )
        return metadata

    def _attest(
        self,
        *,
        context: EnterpriseContext,
        namespace: str,
        method: str,
        decision: GovernanceDecision,
        result: CacheResult,
        rollout_decision: RolloutDecision,
    ) -> None:
        if self.slo_tracker is not None:
            self.slo_tracker.observe(result.receipt)
        if self.ledger is None:
            return
        disposition = getattr(result.receipt.disposition, "value", None)
        disposition = disposition or str(result.receipt.disposition)
        if disposition == "bypass" and not self.config.attest_bypass_results:
            return
        attestation = CacheAttestation(
            subject_id=context.subject_id,
            namespace=namespace,
            method=method,
            key_digest=result.receipt.key_digest,
            value_digest=result.receipt.value_digest,
            disposition=disposition,
            policy_digest=decision.policy_digest,
            release_id=context.release_id,
            model_fingerprint=context.model_fingerprint,
            data_fingerprint=context.data_fingerprint,
            rollout_reason=rollout_decision.reason.value,
            rollout_cohort=rollout_decision.cohort,
            observed_at=result.receipt.observed_at,
            owner=result.receipt.owner,
        )
        self.ledger.append(attestation)

    def execute(
        self,
        *,
        context: EnterpriseContext,
        namespace: str,
        method: str,
        compute: Callable[[], _T],
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
        policy: MethodPolicy | None = None,
        mode: CacheMode | None = None,
        tags: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> _T:
        return self.execute_with_receipt(
            context=context,
            namespace=namespace,
            method=method,
            compute=compute,
            args=args,
            kwargs=kwargs,
            policy=policy,
            mode=mode,
            tags=tags,
            metadata=metadata,
        ).value

    def execute_with_receipt(
        self,
        *,
        context: EnterpriseContext,
        namespace: str,
        method: str,
        compute: Callable[[], _T],
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
        policy: MethodPolicy | None = None,
        mode: CacheMode | None = None,
        tags: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> CacheResult:
        decision = self.policy_engine.evaluate(
            context=context,
            namespace=namespace,
            method=method,
            persistent_enabled=self.config.persistent_enabled,
        ).require()
        effective_policy = self._effective_policy(policy, decision)
        identity = ":".join(
            (
                context.subject_id,
                context.release_id,
                namespace,
                method,
            )
        )
        breaker_key = f"{context.tenant}:{namespace}"
        rollout_decision = self.rollout.decide(
            identity=identity,
            breaker_key=breaker_key,
            requested=mode,
        )
        active_mode = rollout_decision.mode
        effective_tags = tuple(sorted(set((*tags, *decision.required_tags))))
        effective_metadata = self._metadata(
            context=context,
            decision=decision,
            supplied=metadata,
        )
        prefix = self.config.reserved_metadata_prefix
        effective_metadata[prefix + "rollout_reason"] = rollout_decision.reason.value
        effective_metadata[prefix + "rollout_cohort"] = rollout_decision.cohort

        with self.quotas.admit(
            context.tenant,
            estimated_bytes=context.estimated_bytes,
        ):
            try:
                result = self.fabric.execute_with_receipt(
                    namespace=namespace,
                    method=method,
                    args=args,
                    kwargs=kwargs,
                    compute=compute,
                    policy=effective_policy,
                    mode=active_mode,
                    tags=effective_tags,
                    metadata=effective_metadata,
                )
            except self._INFRASTRUCTURE_ERRORS as error:
                self.rollout.breaker.record_failure(breaker_key)
                action = self.config.failure_mode.value
                if self.quarantine is not None:
                    self.quarantine.record(
                        subject_id=context.subject_id,
                        namespace=namespace,
                        method=method,
                        error=error,
                        action=action,
                        attributes=context.attributes,
                    )
                if self.config.failure_mode is CacheFailureMode.RAISE:
                    raise
                result = self.fabric.execute_with_receipt(
                    namespace=namespace,
                    method=method,
                    args=args,
                    kwargs=kwargs,
                    compute=compute,
                    policy=effective_policy,
                    mode=CacheMode.BYPASS,
                    tags=effective_tags,
                    metadata=effective_metadata,
                )
            else:
                if active_mode is not CacheMode.BYPASS:
                    self.rollout.breaker.record_success(breaker_key)
        self._attest(
            context=context,
            namespace=namespace,
            method=method,
            decision=decision,
            result=result,
            rollout_decision=rollout_decision,
        )
        return result

    def invalidate(
        self,
        *,
        context: EnterpriseContext,
        reason: str,
        namespace: str | None = None,
        method: str | None = None,
        tags: Iterable[str] = (),
    ) -> int:
        self.policy_engine.authorize_invalidation(
            context=context,
            reason=reason,
        )
        scoped_tags = tuple(
            sorted(
                set(
                    (
                        *tags,
                        f"tenant:{context.tenant}",
                        f"application:{context.application}",
                        f"environment:{context.environment}",
                    )
                )
            )
        )
        return self.fabric.invalidate(
            namespace=namespace,
            method=method,
            tags=scoped_tags,
        )

    def health(self) -> EnterpriseHealth:
        ledger = self.ledger.verify() if self.ledger is not None else None
        quarantined = (
            len(self.quarantine.events(limit=1000))
            if self.quarantine is not None
            else 0
        )
        return EnterpriseHealth(
            policy_digest=self.policy_engine.policy_digest,
            cache_info=self.fabric.info(),
            slo=(self.slo_tracker.snapshot() if self.slo_tracker else None),
            quotas=self.quotas.snapshots(),
            ledger_valid=(ledger.valid if ledger else None),
            ledger_records=(ledger.records if ledger else None),
            ledger_error=(ledger.error if ledger else None),
            quarantine_events=quarantined,
        )
