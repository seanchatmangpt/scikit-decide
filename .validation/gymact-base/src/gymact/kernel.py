"""Fortune-scale semantic kernel for bounded executable worlds.

The kernel preserves GymAct's evidence-backed eight-operation surface while hardening
every external consequence boundary with limits, fail-closed authority, BLAKE3
evidence, idempotency and independent verification.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar
from uuid import uuid4

import anyio

from gymact.authority import AuthorityResolver, DenyAuthorityResolver
from gymact.evidence import (
    EvidenceRecord,
    MemoryReceiptLedger,
    ReceiptLedger,
    canonical_bytes,
    digest,
    evidence_graph,
)
from gymact.limits import RuntimeLimits
from gymact.models import (
    ActuationIntent,
    ActuationResult,
    AuthorityDecision,
    AuthorityRequest,
    Capability,
    Consequence,
    Episode,
    MaterializationIntent,
    MaterializationResult,
    Observation,
    Operation,
    Receipt,
    Standing,
    VerificationResult,
)
from gymact.ocel import receipts_to_ocel
from gymact.providers import Environment, EnvironmentProvider
from gymact.semantic import ProfileAuthority

T = TypeVar("T")


class BoundaryBlocked(RuntimeError):
    """Typed boundary failure for non-result-bearing read/verification operations."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class _EpisodeState:
    episode: Episode
    environment: Environment
    lock: anyio.Lock = field(default_factory=anyio.Lock)


@dataclass(frozen=True)
class _ActuationRecord:
    intent_digest: str
    result: ActuationResult


@dataclass(frozen=True)
class _MaterializationRecord:
    intent_digest: str
    result: MaterializationResult


class GymAct:
    """Reference orchestrator with public semantics and bounded consequence law."""

    def __init__(
        self,
        *,
        validate_profile: bool = True,
        authority_resolver: AuthorityResolver | None = None,
        limits: RuntimeLimits | None = None,
        receipt_ledger: ReceiptLedger | None = None,
    ) -> None:
        self._providers: dict[str, EnvironmentProvider] = {}
        self._episodes: dict[str, _EpisodeState] = {}
        self._actuation_idempotency: dict[tuple[str, str], _ActuationRecord] = {}
        self._materialization_idempotency: dict[str, _MaterializationRecord] = {}
        self._materialization_lock = anyio.Lock()
        self._teardown_receipts: dict[str, Receipt] = {}
        self._receipts: dict[str, list[Receipt]] = {}
        self._authority = authority_resolver or DenyAuthorityResolver()
        self.limits = limits or RuntimeLimits()
        self.ledger = receipt_ledger or MemoryReceiptLedger()
        self._verifications: list[VerificationResult] = []
        self.profile = ProfileAuthority()
        if validate_profile:
            result = self.profile.validate()
            if not result.conforms:
                raise RuntimeError(f"GymAct semantic profile invalid: {result.report_text}")

    @staticmethod
    def _size(value: object) -> int:
        return len(canonical_bytes(value))

    @staticmethod
    def _error_digest(exc: Exception) -> str:
        return digest({"type": type(exc).__name__, "message": str(exc)})

    def _ensure_input(self, value: object) -> None:
        if self._size(value) > self.limits.max_input_bytes:
            raise BoundaryBlocked("INPUT_LIMIT_EXCEEDED")

    def _ensure_state(self, value: object) -> None:
        if self._size(value) > self.limits.max_state_bytes:
            raise BoundaryBlocked("STATE_LIMIT_EXCEEDED")

    def _ensure_checkpoint(self, value: object) -> None:
        if self._size(value) > self.limits.max_checkpoint_bytes:
            raise BoundaryBlocked("CHECKPOINT_LIMIT_EXCEEDED")

    async def _bounded(
        self,
        timeout_s: float,
        code: str,
        call: Callable[[], Awaitable[T]],
    ) -> T:
        try:
            with anyio.fail_after(timeout_s):
                return await call()
        except TimeoutError as exc:
            raise BoundaryBlocked(code) from exc

    def _record(self, receipt: Receipt) -> Receipt:
        self.ledger.append(receipt)
        self._receipts.setdefault(receipt.episode_id, []).append(receipt)
        return receipt

    def episode_receipts(self, episode_id: str) -> list[Receipt]:
        """Real, in-order Receipt trail accumulated for one episode so far."""
        return list(self._receipts.get(episode_id, []))

    def episode_ocel_log(self, episode_id: str) -> dict[str, Any]:
        """Real OCEL 2.0 log for one episode, built from its accumulated Receipts.

        Pure wiring over the existing `receipts_to_ocel` converter -- no new
        OCEL logic here. Works after teardown too: `_receipts` is never
        cleared when an episode is torn down (only `_episodes` is).
        """
        return receipts_to_ocel(self._receipts.get(episode_id, []))

    def _materialization_result(
        self,
        *,
        intent_digest: str,
        key: str,
        result: MaterializationResult,
        cache: bool = True,
    ) -> MaterializationResult:
        self._record(result.receipt)
        if cache:
            self._materialization_idempotency[key] = _MaterializationRecord(intent_digest, result)
        return result

    def _actuation_result(
        self,
        *,
        intent_digest: str,
        key: tuple[str, str],
        result: ActuationResult,
        cache: bool = True,
    ) -> ActuationResult:
        self._record(result.receipt)
        if cache:
            self._actuation_idempotency[key] = _ActuationRecord(intent_digest, result)
        return result

    def register_provider(self, provider: EnvironmentProvider) -> None:
        """Register one provider by stable name; duplicate names are refused."""
        if not isinstance(provider, EnvironmentProvider):
            raise TypeError("provider does not satisfy EnvironmentProvider")
        if provider.name in self._providers:
            raise ValueError(f"provider already registered: {provider.name}")
        self._providers[provider.name] = provider

    def discover(self) -> tuple[str, ...]:
        """Return registered provider names without materializing a world."""
        return tuple(sorted(self._providers))

    async def _authority_decision(
        self,
        *,
        required: bool,
        episode_id: str,
        subject_ref: str,
        operation: Operation,
        capability_ref: str,
        payload: dict[str, Any],
        authority_ref: str | None,
    ) -> AuthorityDecision:
        if not required:
            return AuthorityDecision(admitted=True, reason="AUTHORITY_NOT_REQUIRED")
        request = AuthorityRequest(
            episode_id=episode_id,
            subject_ref=subject_ref,
            operation=operation,
            capability_ref=capability_ref,
            payload=payload,
            authority_ref=authority_ref,
        )
        return await self._bounded(
            self.limits.authority_timeout_s,
            "AUTHORITY_TIMEOUT",
            lambda: self._authority.authorize(request),
        )

    async def materialize(self, intent: MaterializationIntent) -> MaterializationResult:
        """Materialize one bounded world with authority, idempotency and semantic gates."""
        intent_digest = digest(intent.model_dump(mode="json"))
        async with self._materialization_lock:
            cached = self._materialization_idempotency.get(intent.idempotency_key)
            if cached is not None:
                if cached.intent_digest == intent_digest:
                    return cached.result
                receipt = Receipt(
                    episode_id=cached.result.receipt.episode_id,
                    operation=Operation.MATERIALIZE,
                    standing=Standing.REFUSED,
                    subject_ref=cached.result.receipt.subject_ref,
                    capability_ref="urn:gymact:operation:materialize",
                    authority_ref=intent.authority_ref,
                    idempotency_key=intent.idempotency_key,
                    reason="IDEMPOTENCY_KEY_CONFLICT",
                )
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.REFUSED,
                        receipt=receipt,
                    ),
                    cache=False,
                )

            episode_id = uuid4().hex
            subject_ref = f"urn:gymact:provider:{intent.provider}"
            try:
                self._ensure_input({"scenario": intent.scenario, "config": intent.config})
            except BoundaryBlocked as exc:
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.REFUSED,
                        receipt=Receipt(
                            episode_id=episode_id,
                            operation=Operation.MATERIALIZE,
                            standing=Standing.REFUSED,
                            subject_ref=subject_ref,
                            capability_ref="urn:gymact:operation:materialize",
                            idempotency_key=intent.idempotency_key,
                            reason=exc.code,
                        ),
                    ),
                )

            provider = self._providers.get(intent.provider)
            if provider is None:
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.UNSUPPORTED,
                        receipt=Receipt(
                            episode_id=episode_id,
                            operation=Operation.MATERIALIZE,
                            standing=Standing.UNSUPPORTED,
                            subject_ref=subject_ref,
                            capability_ref="urn:gymact:operation:materialize",
                            authority_ref=intent.authority_ref,
                            idempotency_key=intent.idempotency_key,
                            reason="UNKNOWN_PROVIDER",
                        ),
                    ),
                )

            try:
                authority = await self._authority_decision(
                    required=provider.materialization_requires_authority,
                    episode_id=episode_id,
                    subject_ref=subject_ref,
                    operation=Operation.MATERIALIZE,
                    capability_ref="urn:gymact:operation:materialize",
                    payload={"scenario": intent.scenario, "config": intent.config},
                    authority_ref=intent.authority_ref,
                )
            except BoundaryBlocked as exc:
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.BLOCKED,
                        receipt=Receipt(
                            episode_id=episode_id,
                            operation=Operation.MATERIALIZE,
                            standing=Standing.BLOCKED,
                            subject_ref=subject_ref,
                            capability_ref="urn:gymact:operation:materialize",
                            authority_ref=intent.authority_ref,
                            idempotency_key=intent.idempotency_key,
                            reason=exc.code,
                        ),
                    ),
                )

            if not authority.admitted:
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.REFUSED,
                        receipt=Receipt(
                            episode_id=episode_id,
                            operation=Operation.MATERIALIZE,
                            standing=Standing.REFUSED,
                            subject_ref=subject_ref,
                            capability_ref="urn:gymact:operation:materialize",
                            authority_ref=intent.authority_ref,
                            authority_evidence_ref=authority.evidence_ref,
                            idempotency_key=intent.idempotency_key,
                            reason=authority.reason,
                        ),
                    ),
                )

            try:
                environment = await self._bounded(
                    self.limits.materialize_timeout_s,
                    "MATERIALIZATION_TIMEOUT",
                    lambda: provider.materialize(scenario=intent.scenario, config=intent.config),
                )
            except BoundaryBlocked as exc:
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.BLOCKED,
                        receipt=Receipt(
                            episode_id=episode_id,
                            operation=Operation.MATERIALIZE,
                            standing=Standing.BLOCKED,
                            subject_ref=subject_ref,
                            capability_ref="urn:gymact:operation:materialize",
                            authority_ref=intent.authority_ref,
                            authority_evidence_ref=authority.evidence_ref,
                            idempotency_key=intent.idempotency_key,
                            reason=exc.code,
                        ),
                    ),
                )
            except Exception as exc:
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.BLOCKED,
                        receipt=Receipt(
                            episode_id=episode_id,
                            operation=Operation.MATERIALIZE,
                            standing=Standing.BLOCKED,
                            subject_ref=subject_ref,
                            capability_ref="urn:gymact:operation:materialize",
                            authority_ref=intent.authority_ref,
                            authority_evidence_ref=authority.evidence_ref,
                            idempotency_key=intent.idempotency_key,
                            error_digest=self._error_digest(exc),
                            reason=f"PROVIDER_ERROR:{type(exc).__name__}",
                        ),
                    ),
                )

            try:
                capabilities = environment.capabilities()
                validation = self.profile.validate_capabilities(capabilities)
                if not validation.conforms:
                    raise ValueError("provider capabilities do not conform to GymAct profile")
                initial_state = await self._bounded(
                    self.limits.observe_timeout_s,
                    "OBSERVATION_TIMEOUT",
                    environment.observe,
                )
                self._ensure_state(initial_state)
            except Exception as exc:
                with contextlib.suppress(Exception):
                    await self._bounded(
                        self.limits.teardown_timeout_s,
                        "TEARDOWN_TIMEOUT",
                        environment.teardown,
                    )
                reason = (
                    exc.code if isinstance(exc, BoundaryBlocked) else "ENVIRONMENT_ADMISSION_FAILED"
                )
                return self._materialization_result(
                    intent_digest=intent_digest,
                    key=intent.idempotency_key,
                    result=MaterializationResult(
                        accepted=False,
                        standing=Standing.BLOCKED,
                        receipt=Receipt(
                            episode_id=episode_id,
                            operation=Operation.MATERIALIZE,
                            standing=Standing.BLOCKED,
                            subject_ref=getattr(environment, "environment_id", subject_ref),
                            capability_ref="urn:gymact:operation:materialize",
                            authority_ref=intent.authority_ref,
                            authority_evidence_ref=authority.evidence_ref,
                            idempotency_key=intent.idempotency_key,
                            error_digest=None
                            if isinstance(exc, BoundaryBlocked)
                            else self._error_digest(exc),
                            reason=reason,
                        ),
                    ),
                )

            episode = Episode(
                episode_id=episode_id,
                provider=intent.provider,
                environment_id=environment.environment_id,
                scenario=intent.scenario,
            )
            self._episodes[episode_id] = _EpisodeState(episode, environment)
            observation = Observation(
                episode_id=episode_id,
                state=initial_state,
                state_digest=digest(initial_state),
            )
            return self._materialization_result(
                intent_digest=intent_digest,
                key=intent.idempotency_key,
                result=MaterializationResult(
                    accepted=True,
                    standing=Standing.ALIVE,
                    episode=episode,
                    observation=observation,
                    receipt=Receipt(
                        episode_id=episode_id,
                        operation=Operation.MATERIALIZE,
                        standing=Standing.ALIVE,
                        subject_ref=environment.environment_id,
                        capability_ref="urn:gymact:operation:materialize",
                        authority_ref=intent.authority_ref,
                        authority_evidence_ref=authority.evidence_ref,
                        idempotency_key=intent.idempotency_key,
                        post_state_digest=observation.state_digest,
                    ),
                ),
            )

    async def create_episode(
        self,
        provider: str,
        *,
        scenario: str | None = None,
        config: dict[str, Any] | None = None,
        authority_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> MaterializationResult:
        """Convenience wrapper around the receipted materialization operation."""
        values: dict[str, Any] = {
            "provider": provider,
            "scenario": scenario,
            "config": config or {},
            "authority_ref": authority_ref,
        }
        if idempotency_key is not None:
            values["idempotency_key"] = idempotency_key
        return await self.materialize(MaterializationIntent.model_validate(values))

    def _state(self, episode_id: str) -> _EpisodeState:
        try:
            return self._episodes[episode_id]
        except KeyError as exc:
            raise KeyError(f"unknown episode: {episode_id}") from exc

    async def _observe_unlocked(self, state: _EpisodeState) -> Observation:
        value = await self._bounded(
            self.limits.observe_timeout_s,
            "OBSERVATION_TIMEOUT",
            state.environment.observe,
        )
        self._ensure_state(value)
        return Observation(
            episode_id=state.episode.episode_id,
            state=value,
            state_digest=digest(value),
        )

    def capabilities(self, episode_id: str) -> tuple[Capability, ...]:
        """Return admitted semantic capabilities exposed by one environment."""
        return self._state(episode_id).environment.capabilities()

    async def observe(self, episode_id: str) -> Observation:
        """Observe current state without promoting it to verification."""
        state = self._state(episode_id)
        async with state.lock:
            return await self._observe_unlocked(state)

    async def act(self, intent: ActuationIntent) -> ActuationResult:
        """Attempt one semantic actuation with authority, limits and replay gates."""
        state = self._state(intent.episode_id)
        key = (intent.episode_id, intent.idempotency_key)
        intent_digest = digest(intent.model_dump(mode="json"))

        async with state.lock:
            cached = self._actuation_idempotency.get(key)
            if cached is not None:
                if cached.intent_digest == intent_digest:
                    return cached.result
                before = await self._observe_unlocked(state)
                return self._actuation_result(
                    intent_digest=intent_digest,
                    key=key,
                    cache=False,
                    result=ActuationResult(
                        accepted=False,
                        standing=Standing.REFUSED,
                        observation=before,
                        receipt=Receipt(
                            episode_id=intent.episode_id,
                            operation=Operation.ACT,
                            standing=Standing.REFUSED,
                            subject_ref=state.environment.environment_id,
                            capability_ref=intent.capability,
                            authority_ref=intent.authority_ref,
                            idempotency_key=intent.idempotency_key,
                            pre_state_digest=before.state_digest,
                            post_state_digest=before.state_digest,
                            reason="IDEMPOTENCY_KEY_CONFLICT",
                        ),
                    ),
                )

            before = await self._observe_unlocked(state)
            try:
                self._ensure_input(intent.payload)
            except BoundaryBlocked as exc:
                return self._actuation_result(
                    intent_digest=intent_digest,
                    key=key,
                    result=ActuationResult(
                        accepted=False,
                        standing=Standing.REFUSED,
                        observation=before,
                        receipt=Receipt(
                            episode_id=intent.episode_id,
                            operation=Operation.ACT,
                            standing=Standing.REFUSED,
                            subject_ref=state.environment.environment_id,
                            capability_ref=intent.capability,
                            idempotency_key=intent.idempotency_key,
                            pre_state_digest=before.state_digest,
                            post_state_digest=before.state_digest,
                            reason=exc.code,
                        ),
                    ),
                )

            capabilities = {item.iri: item for item in state.environment.capabilities()}
            capability = capabilities.get(intent.capability)
            if capability is None:
                return self._actuation_result(
                    intent_digest=intent_digest,
                    key=key,
                    result=ActuationResult(
                        accepted=False,
                        standing=Standing.UNSUPPORTED,
                        observation=before,
                        receipt=Receipt(
                            episode_id=intent.episode_id,
                            operation=Operation.ACT,
                            standing=Standing.UNSUPPORTED,
                            subject_ref=state.environment.environment_id,
                            capability_ref=intent.capability,
                            authority_ref=intent.authority_ref,
                            idempotency_key=intent.idempotency_key,
                            pre_state_digest=before.state_digest,
                            post_state_digest=before.state_digest,
                            reason="UNKNOWN_CAPABILITY",
                        ),
                    ),
                )
            if capability.consequence is not Consequence.DO:
                return self._actuation_result(
                    intent_digest=intent_digest,
                    key=key,
                    result=ActuationResult(
                        accepted=False,
                        standing=Standing.REFUSED,
                        observation=before,
                        receipt=Receipt(
                            episode_id=intent.episode_id,
                            operation=Operation.ACT,
                            standing=Standing.REFUSED,
                            subject_ref=state.environment.environment_id,
                            capability_ref=capability.iri,
                            authority_ref=intent.authority_ref,
                            idempotency_key=intent.idempotency_key,
                            pre_state_digest=before.state_digest,
                            post_state_digest=before.state_digest,
                            reason="READ_CAPABILITY_IS_NOT_ACTUATION",
                        ),
                    ),
                )

            try:
                authority = await self._authority_decision(
                    required=state.environment.requires_authority,
                    episode_id=intent.episode_id,
                    subject_ref=state.environment.environment_id,
                    operation=Operation.ACT,
                    capability_ref=capability.iri,
                    payload=intent.payload,
                    authority_ref=intent.authority_ref,
                )
            except BoundaryBlocked as exc:
                return self._actuation_result(
                    intent_digest=intent_digest,
                    key=key,
                    result=ActuationResult(
                        accepted=False,
                        standing=Standing.BLOCKED,
                        observation=before,
                        receipt=Receipt(
                            episode_id=intent.episode_id,
                            operation=Operation.ACT,
                            standing=Standing.BLOCKED,
                            subject_ref=state.environment.environment_id,
                            capability_ref=capability.iri,
                            authority_ref=intent.authority_ref,
                            idempotency_key=intent.idempotency_key,
                            pre_state_digest=before.state_digest,
                            post_state_digest=before.state_digest,
                            reason=exc.code,
                        ),
                    ),
                )

            if not authority.admitted:
                return self._actuation_result(
                    intent_digest=intent_digest,
                    key=key,
                    result=ActuationResult(
                        accepted=False,
                        standing=Standing.REFUSED,
                        observation=before,
                        receipt=Receipt(
                            episode_id=intent.episode_id,
                            operation=Operation.ACT,
                            standing=Standing.REFUSED,
                            subject_ref=state.environment.environment_id,
                            capability_ref=capability.iri,
                            authority_ref=intent.authority_ref,
                            authority_evidence_ref=authority.evidence_ref,
                            idempotency_key=intent.idempotency_key,
                            pre_state_digest=before.state_digest,
                            post_state_digest=before.state_digest,
                            reason=authority.reason,
                        ),
                    ),
                )

            try:
                effect = await self._bounded(
                    self.limits.actuate_timeout_s,
                    "ACTUATION_TIMEOUT",
                    lambda: state.environment.actuate(capability, intent.payload),
                )
                self._ensure_state(effect)
                after = await self._observe_unlocked(state)
            except Exception as exc:
                try:
                    after = await self._observe_unlocked(state)
                except Exception:
                    after = before
                reason = (
                    exc.code
                    if isinstance(exc, BoundaryBlocked)
                    else f"PROVIDER_ERROR:{type(exc).__name__}"
                )
                return self._actuation_result(
                    intent_digest=intent_digest,
                    key=key,
                    result=ActuationResult(
                        accepted=False,
                        standing=Standing.BLOCKED,
                        observation=after,
                        receipt=Receipt(
                            episode_id=intent.episode_id,
                            operation=Operation.ACT,
                            standing=Standing.BLOCKED,
                            subject_ref=state.environment.environment_id,
                            capability_ref=capability.iri,
                            authority_ref=intent.authority_ref,
                            authority_evidence_ref=authority.evidence_ref,
                            idempotency_key=intent.idempotency_key,
                            pre_state_digest=before.state_digest,
                            post_state_digest=after.state_digest,
                            error_digest=None
                            if isinstance(exc, BoundaryBlocked)
                            else self._error_digest(exc),
                            reason=reason,
                        ),
                    ),
                )

            return self._actuation_result(
                intent_digest=intent_digest,
                key=key,
                result=ActuationResult(
                    accepted=True,
                    standing=Standing.ALIVE,
                    effect=effect,
                    observation=after,
                    receipt=Receipt(
                        episode_id=intent.episode_id,
                        operation=Operation.ACT,
                        standing=Standing.ALIVE,
                        subject_ref=state.environment.environment_id,
                        capability_ref=capability.iri,
                        authority_ref=intent.authority_ref,
                        authority_evidence_ref=authority.evidence_ref,
                        idempotency_key=intent.idempotency_key,
                        pre_state_digest=before.state_digest,
                        post_state_digest=after.state_digest,
                    ),
                ),
            )

    async def verify(self, episode_id: str, expected: dict[str, Any]) -> VerificationResult:
        """Independently evaluate expected partial state against the environment."""
        self._ensure_input(expected)
        state = self._state(episode_id)
        async with state.lock:
            passed, observed = await self._bounded(
                self.limits.verify_timeout_s,
                "VERIFICATION_TIMEOUT",
                lambda: state.environment.verify(expected),
            )
            self._ensure_state(observed)
            result = VerificationResult(
                episode_id=episode_id,
                passed=passed,
                expected=expected,
                observed=observed,
                state_digest=digest(observed),
            )
            self._verifications.append(result)
            return result

    async def checkpoint(self, episode_id: str) -> dict[str, Any]:
        """Return bounded provider-defined recovery state."""
        state = self._state(episode_id)
        async with state.lock:
            checkpoint = await self._bounded(
                self.limits.recovery_timeout_s,
                "CHECKPOINT_TIMEOUT",
                state.environment.checkpoint,
            )
            self._ensure_checkpoint(checkpoint)
            return checkpoint

    async def restore(
        self,
        episode_id: str,
        checkpoint: dict[str, Any],
        *,
        authority_ref: str | None = None,
    ) -> Receipt:
        """Restore a bounded checkpoint after explicit authority admission when required."""
        state = self._state(episode_id)
        async with state.lock:
            before = await self._observe_unlocked(state)
            try:
                self._ensure_checkpoint(checkpoint)
            except BoundaryBlocked as exc:
                return self._record(
                    Receipt(
                        episode_id=episode_id,
                        operation=Operation.RESTORE,
                        standing=Standing.REFUSED,
                        subject_ref=state.environment.environment_id,
                        capability_ref="urn:gymact:operation:restore",
                        authority_ref=authority_ref,
                        pre_state_digest=before.state_digest,
                        post_state_digest=before.state_digest,
                        reason=exc.code,
                    )
                )

            try:
                authority = await self._authority_decision(
                    required=state.environment.requires_authority,
                    episode_id=episode_id,
                    subject_ref=state.environment.environment_id,
                    operation=Operation.RESTORE,
                    capability_ref="urn:gymact:operation:restore",
                    payload={"checkpoint_digest": digest(checkpoint)},
                    authority_ref=authority_ref,
                )
            except BoundaryBlocked as exc:
                return self._record(
                    Receipt(
                        episode_id=episode_id,
                        operation=Operation.RESTORE,
                        standing=Standing.BLOCKED,
                        subject_ref=state.environment.environment_id,
                        capability_ref="urn:gymact:operation:restore",
                        authority_ref=authority_ref,
                        pre_state_digest=before.state_digest,
                        post_state_digest=before.state_digest,
                        reason=exc.code,
                    )
                )

            if not authority.admitted:
                return self._record(
                    Receipt(
                        episode_id=episode_id,
                        operation=Operation.RESTORE,
                        standing=Standing.REFUSED,
                        subject_ref=state.environment.environment_id,
                        capability_ref="urn:gymact:operation:restore",
                        authority_ref=authority_ref,
                        authority_evidence_ref=authority.evidence_ref,
                        pre_state_digest=before.state_digest,
                        post_state_digest=before.state_digest,
                        reason=authority.reason,
                    )
                )

            try:
                await self._bounded(
                    self.limits.recovery_timeout_s,
                    "RESTORE_TIMEOUT",
                    lambda: state.environment.restore(checkpoint),
                )
                after = await self._observe_unlocked(state)
            except Exception as exc:
                try:
                    after = await self._observe_unlocked(state)
                except Exception:
                    after = before
                return self._record(
                    Receipt(
                        episode_id=episode_id,
                        operation=Operation.RESTORE,
                        standing=Standing.BLOCKED,
                        subject_ref=state.environment.environment_id,
                        capability_ref="urn:gymact:operation:restore",
                        authority_ref=authority_ref,
                        authority_evidence_ref=authority.evidence_ref,
                        pre_state_digest=before.state_digest,
                        post_state_digest=after.state_digest,
                        error_digest=None
                        if isinstance(exc, BoundaryBlocked)
                        else self._error_digest(exc),
                        reason=exc.code
                        if isinstance(exc, BoundaryBlocked)
                        else f"PROVIDER_ERROR:{type(exc).__name__}",
                    )
                )
            return self._record(
                Receipt(
                    episode_id=episode_id,
                    operation=Operation.RESTORE,
                    standing=Standing.ALIVE,
                    subject_ref=state.environment.environment_id,
                    capability_ref="urn:gymact:operation:restore",
                    authority_ref=authority_ref,
                    authority_evidence_ref=authority.evidence_ref,
                    pre_state_digest=before.state_digest,
                    post_state_digest=after.state_digest,
                )
            )

    async def teardown(self, episode_id: str, *, authority_ref: str | None = None) -> Receipt:
        """Idempotently tear down an environment after authority admission when required."""
        prior = self._teardown_receipts.get(episode_id)
        if prior is not None:
            return prior
        state = self._state(episode_id)
        async with state.lock:
            before = await self._observe_unlocked(state)
            try:
                authority = await self._authority_decision(
                    required=state.environment.requires_authority,
                    episode_id=episode_id,
                    subject_ref=state.environment.environment_id,
                    operation=Operation.TEARDOWN,
                    capability_ref="urn:gymact:operation:teardown",
                    payload={},
                    authority_ref=authority_ref,
                )
            except BoundaryBlocked as exc:
                return self._record(
                    Receipt(
                        episode_id=episode_id,
                        operation=Operation.TEARDOWN,
                        standing=Standing.BLOCKED,
                        subject_ref=state.environment.environment_id,
                        capability_ref="urn:gymact:operation:teardown",
                        authority_ref=authority_ref,
                        pre_state_digest=before.state_digest,
                        post_state_digest=before.state_digest,
                        reason=exc.code,
                    )
                )
            if not authority.admitted:
                return self._record(
                    Receipt(
                        episode_id=episode_id,
                        operation=Operation.TEARDOWN,
                        standing=Standing.REFUSED,
                        subject_ref=state.environment.environment_id,
                        capability_ref="urn:gymact:operation:teardown",
                        authority_ref=authority_ref,
                        authority_evidence_ref=authority.evidence_ref,
                        pre_state_digest=before.state_digest,
                        post_state_digest=before.state_digest,
                        reason=authority.reason,
                    )
                )
            try:
                await self._bounded(
                    self.limits.teardown_timeout_s,
                    "TEARDOWN_TIMEOUT",
                    state.environment.teardown,
                )
            except Exception as exc:
                return self._record(
                    Receipt(
                        episode_id=episode_id,
                        operation=Operation.TEARDOWN,
                        standing=Standing.BLOCKED,
                        subject_ref=state.environment.environment_id,
                        capability_ref="urn:gymact:operation:teardown",
                        authority_ref=authority_ref,
                        authority_evidence_ref=authority.evidence_ref,
                        pre_state_digest=before.state_digest,
                        error_digest=None
                        if isinstance(exc, BoundaryBlocked)
                        else self._error_digest(exc),
                        reason=exc.code
                        if isinstance(exc, BoundaryBlocked)
                        else f"PROVIDER_ERROR:{type(exc).__name__}",
                    )
                )
            receipt = self._record(
                Receipt(
                    episode_id=episode_id,
                    operation=Operation.TEARDOWN,
                    standing=Standing.ALIVE,
                    subject_ref=state.environment.environment_id,
                    capability_ref="urn:gymact:operation:teardown",
                    authority_ref=authority_ref,
                    authority_evidence_ref=authority.evidence_ref,
                    pre_state_digest=before.state_digest,
                )
            )
            self._teardown_receipts[episode_id] = receipt
            del self._episodes[episode_id]
            return receipt

    def evidence_records(self) -> tuple[EvidenceRecord, ...]:
        """Return the append-only evidence chain."""
        return self.ledger.records()

    def receipt_record(self, receipt_id: str) -> EvidenceRecord | None:
        """Resolve a receipt to its chained evidence record."""
        return self.ledger.find(receipt_id)

    def verify_evidence_chain(self) -> bool:
        """Mechanically verify the complete in-process receipt chain."""
        return self.ledger.verify()

    def evidence_rdf(self):
        """Return a public PROV/EARL RDF projection of receipts and verifications."""
        return evidence_graph(self.ledger.records(), self._verifications)
