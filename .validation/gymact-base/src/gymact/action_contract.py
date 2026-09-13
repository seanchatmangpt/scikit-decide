"""Crown semantic-action contracts for consequential GymAct providers.

These models are intentionally transport-neutral. They describe candidate actions,
authority requirements, expected effects, observation/verification, retry law, cost,
and causal locality without granting execution authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from gymact.models import FrozenModel, Standing


class IdempotencyClass(StrEnum):
    IDEMPOTENT = "IDEMPOTENT"
    CONDITIONALLY_IDEMPOTENT = "CONDITIONALLY_IDEMPOTENT"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    UNKNOWN = "UNKNOWN"


class ReversalClass(StrEnum):
    REVERSIBLE = "REVERSIBLE"
    COMPENSATABLE = "COMPENSATABLE"
    IRREVERSIBLE = "IRREVERSIBLE"
    UNKNOWN = "UNKNOWN"


class ObservationConfidence(StrEnum):
    SELF_REPORTED = "SELF_REPORTED"
    SAME_PROVIDER_OBSERVED = "SAME_PROVIDER_OBSERVED"
    INDEPENDENT_CHANNEL = "INDEPENDENT_CHANNEL"
    MULTI_ORACLE = "MULTI_ORACLE"
    PHYSICAL_SENSOR = "PHYSICAL_SENSOR"


class VerificationKind(StrEnum):
    EXACT_STATE = "EXACT_STATE"
    PREDICATE = "PREDICATE"
    SHACL = "SHACL"
    QUERY = "QUERY"
    DIGEST = "DIGEST"
    RESOURCE_EXISTS = "RESOURCE_EXISTS"
    RESOURCE_ABSENT = "RESOURCE_ABSENT"
    REVISION = "REVISION"
    EVENT = "EVENT"
    PROCESS_CONFORMANCE = "PROCESS_CONFORMANCE"
    TEMPORAL_STABILIZATION = "TEMPORAL_STABILIZATION"
    QUORUM = "QUORUM"


class AcknowledgementStatus(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    LOST = "LOST"
    UNKNOWN = "UNKNOWN"


class RefusalCode(StrEnum):
    AUTHORITY_REFUSED = "AUTHORITY_REFUSED"
    IDENTITY_REFUSED = "IDENTITY_REFUSED"
    CAPABILITY_REFUSED = "CAPABILITY_REFUSED"
    PRECONDITION_REFUSED = "PRECONDITION_REFUSED"
    STALE_OBSERVATION_REFUSED = "STALE_OBSERVATION_REFUSED"
    REVISION_MISMATCH_REFUSED = "REVISION_MISMATCH_REFUSED"
    POLICY_REFUSED = "POLICY_REFUSED"
    UNSAFE_RETRY_REFUSED = "UNSAFE_RETRY_REFUSED"
    AMBIGUOUS_SUBJECT_REFUSED = "AMBIGUOUS_SUBJECT_REFUSED"
    VERIFICATION_REFUSED = "VERIFICATION_REFUSED"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    PROVIDER_CONFIGURATION_REQUIRED = "PROVIDER_CONFIGURATION_REQUIRED"


class ReconciliationDisposition(StrEnum):
    EFFECT_CONFIRMED = "EFFECT_CONFIRMED"
    NO_EFFECT = "NO_EFFECT"
    PARTIAL_EFFECT = "PARTIAL_EFFECT"
    STILL_UNCERTAIN = "STILL_UNCERTAIN"
    RETRY_ADMITTED = "RETRY_ADMITTED"
    RETRY_REFUSED = "RETRY_REFUSED"


class SubjectRef(FrozenModel):
    semantic_id: str = Field(min_length=1)
    provider_ref: str = Field(min_length=1)
    revision: str | None = None


class AuthorityRequirement(FrozenModel):
    capability_refs: tuple[str, ...] = ()
    policy_refs: tuple[str, ...] = ()
    autonomous_policy_may_be_stricter: bool = True


class ExpectedEffect(FrozenModel):
    predicate: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class VerificationStrategy(FrozenModel):
    kind: VerificationKind
    observer_ref: str = Field(min_length=1)
    expected: dict[str, Any] = Field(default_factory=dict)
    minimum_confidence: ObservationConfidence = ObservationConfidence.SAME_PROVIDER_OBSERVED
    settle_timeout_s: float = Field(default=0.0, ge=0.0)
    quorum: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def require_quorum_for_quorum_strategy(self) -> Self:
        if self.kind is VerificationKind.QUORUM and self.quorum < 2:
            raise ValueError("QUORUM_VERIFICATION_REQUIRES_AT_LEAST_TWO_ORACLES")
        return self


class CostModel(FrozenModel):
    monetary: float = Field(default=0.0, ge=0.0)
    expected_wall_time_s: float = Field(default=0.0, ge=0.0)
    compute_units: float = Field(default=0.0, ge=0.0)
    expected_human_approvals: float = Field(default=0.0, ge=0.0)
    expected_failure_probability: float = Field(default=0.0, ge=0.0, le=1.0)


class CausalLocality(FrozenModel):
    execution_site: str = "unspecified"
    observer_site: str = "unspecified"
    estimated_hops: int | None = Field(default=None, ge=0)
    estimated_effect_latency_s: float | None = Field(default=None, ge=0.0)
    estimated_observation_latency_s: float | None = Field(default=None, ge=0.0)


class ActionDefinition(FrozenModel):
    """Machine-inspectable semantic action definition; never an execution grant."""

    semantic_id: str = Field(min_length=1)
    provider_ref: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    subject_type: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = Field(default_factory=dict)
    preconditions: tuple[str, ...] = ()
    authority: AuthorityRequirement = Field(default_factory=AuthorityRequirement)
    expected_effects: tuple[ExpectedEffect, ...]
    verification: VerificationStrategy
    idempotency: IdempotencyClass = IdempotencyClass.UNKNOWN
    idempotency_fields: tuple[str, ...] = ()
    reversal: ReversalClass = ReversalClass.UNKNOWN
    compensation_action_ref: str | None = None
    cost: CostModel = Field(default_factory=CostModel)
    locality: CausalLocality = Field(default_factory=CausalLocality)
    standing: Standing = Standing.UNKNOWN
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def enforce_execution_semantics(self) -> Self:
        if (
            self.idempotency is IdempotencyClass.CONDITIONALLY_IDEMPOTENT
            and not self.idempotency_fields
        ):
            raise ValueError("CONDITIONAL_IDEMPOTENCY_REQUIRES_KEY_FIELDS")
        if self.reversal is ReversalClass.COMPENSATABLE and not self.compensation_action_ref:
            raise ValueError("COMPENSATABLE_ACTION_REQUIRES_COMPENSATION_ACTION_REF")
        if self.standing is Standing.ALIVE and not self.evidence_refs:
            raise ValueError("ALIVE_ACTION_REQUIRES_EXECUTION_EVIDENCE")
        if self.standing is Standing.ADOPTED and not self.evidence_refs:
            raise ValueError("ADOPTED_ACTION_REQUIRES_EXTERNAL_EVIDENCE")
        return self


class ExecutionGrant(FrozenModel):
    """Identity-bound authority token consumed by the BRCE DO boundary."""

    principal: str = Field(min_length=1)
    delegated_principal: str | None = None
    action_ref: str = Field(min_length=1)
    subject: SubjectRef
    capability_ref: str = Field(min_length=1)
    authority_ref: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)
    admitted_observation_ref: str = Field(min_length=1)
    intended_effects: tuple[ExpectedEffect, ...]
    scope_refs: tuple[str, ...] = ()
    expires_at: datetime | None = None
    nonce: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_aware_expiry(self) -> Self:
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("EXECUTION_GRANT_EXPIRY_MUST_BE_TIMEZONE_AWARE")
        return self


class PreparedAction(FrozenModel):
    """Constructed executable intent. Possession does not authorize DO."""

    episode_id: str = Field(min_length=1)
    action_ref: str = Field(min_length=1)
    subject: SubjectRef
    payload: dict[str, Any] = Field(default_factory=dict)
    admission_digest: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class ExecutionAcknowledgement(FrozenModel):
    status: AcknowledgementStatus
    provider_operation_ref: str | None = None
    provider_payload: dict[str, Any] = Field(default_factory=dict)


class UncertainExecution(FrozenModel):
    action_ref: str = Field(min_length=1)
    subject: SubjectRef
    idempotency_key: str = Field(min_length=1)
    pre_state_digest: str = Field(min_length=1)
    last_observed_state_digest: str | None = None
    acknowledgement: ExecutionAcknowledgement
    reason: str = Field(min_length=1)


class ReconciliationResult(FrozenModel):
    disposition: ReconciliationDisposition
    standing: Standing
    observed_state_digest: str | None = None
    verification_ref: str | None = None
    retry_admitted: bool = False
    reason: str | None = None

    @model_validator(mode="after")
    def retry_requires_explicit_disposition(self) -> Self:
        if self.disposition is ReconciliationDisposition.STILL_UNCERTAIN and self.retry_admitted:
            raise ValueError("UNCERTAIN_OUTCOME_CANNOT_IMPLY_RETRY")
        if self.retry_admitted and self.disposition is not ReconciliationDisposition.RETRY_ADMITTED:
            raise ValueError("RETRY_REQUIRES_RETRY_ADMITTED_DISPOSITION")
        return self


class ProviderMetadata(FrozenModel):
    semantic_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    provider_families: tuple[str, ...]
    supports_independent_observation: bool
    locality: CausalLocality = Field(default_factory=CausalLocality)


class ProviderHealth(FrozenModel):
    standing: Standing
    observed_at: str
    subject_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    reason: str | None = None


class AdmissionResult(FrozenModel):
    """Mechanical admission of a prepared action against an identity-bound grant."""

    admitted: bool
    reason: str


def construct_prepared_action(
    action: ActionDefinition,
    *,
    episode_id: str,
    subject: SubjectRef,
    payload: dict[str, Any],
    admission_digest: str,
    idempotency_key: str,
) -> PreparedAction:
    """CONSTRUCT only: validate input shape and manufacture a powerless intent."""
    try:
        from jsonschema import ValidationError, validate

        validate(instance=payload, schema=action.input_schema)
    except ImportError as exc:
        raise RuntimeError("JSONSCHEMA_RUNTIME_REQUIRED") from exc
    except ValidationError as exc:
        raise ValueError("PRECONDITION_REFUSED:INPUT_SCHEMA") from exc
    return PreparedAction(
        episode_id=episode_id,
        action_ref=action.semantic_id,
        subject=subject,
        payload=payload,
        admission_digest=admission_digest,
        idempotency_key=idempotency_key,
    )


def admit_execution(
    action: ActionDefinition,
    prepared: PreparedAction,
    grant: ExecutionGrant,
    *,
    current_revision: str | None = None,
    now: datetime | None = None,
) -> AdmissionResult:
    """Admit identity/revision closure; this still does not itself perform DO."""
    moment = now or datetime.now(UTC)
    if grant.expires_at is not None and grant.expires_at <= moment:
        return AdmissionResult(admitted=False, reason=RefusalCode.POLICY_REFUSED.value)
    if prepared.action_ref != action.semantic_id or grant.action_ref != action.semantic_id:
        return AdmissionResult(admitted=False, reason=RefusalCode.IDENTITY_REFUSED.value)
    if grant.capability_ref != action.capability_ref:
        return AdmissionResult(admitted=False, reason=RefusalCode.CAPABILITY_REFUSED.value)
    if prepared.subject.semantic_id != grant.subject.semantic_id:
        return AdmissionResult(admitted=False, reason=RefusalCode.IDENTITY_REFUSED.value)
    if prepared.subject.provider_ref != grant.subject.provider_ref:
        return AdmissionResult(admitted=False, reason=RefusalCode.IDENTITY_REFUSED.value)
    if grant.scope_refs and not (
        {prepared.subject.semantic_id, prepared.subject.provider_ref}
        & set(grant.scope_refs)
    ):
        return AdmissionResult(admitted=False, reason=RefusalCode.AUTHORITY_REFUSED.value)
    if (
        grant.subject.revision is not None
        and prepared.subject.revision is not None
        and grant.subject.revision != prepared.subject.revision
    ):
        return AdmissionResult(
            admitted=False,
            reason=RefusalCode.REVISION_MISMATCH_REFUSED.value,
        )
    admitted_revision = grant.subject.revision or prepared.subject.revision
    if (
        current_revision is not None
        and admitted_revision is not None
        and current_revision != admitted_revision
    ):
        return AdmissionResult(
            admitted=False,
            reason=RefusalCode.REVISION_MISMATCH_REFUSED.value,
        )
    if grant.intended_effects != action.expected_effects:
        return AdmissionResult(
            admitted=False,
            reason=RefusalCode.PRECONDITION_REFUSED.value,
        )
    return AdmissionResult(admitted=True, reason="ADMITTED")


def admit_retry(
    action: ActionDefinition, reconciliation: ReconciliationResult
) -> ReconciliationResult:
    """Manufacture a retry candidate only after NO_EFFECT; never grant retry authority."""
    if reconciliation.disposition is not ReconciliationDisposition.NO_EFFECT:
        return ReconciliationResult(
            disposition=ReconciliationDisposition.RETRY_REFUSED,
            standing=Standing.REFUSED,
            observed_state_digest=reconciliation.observed_state_digest,
            verification_ref=reconciliation.verification_ref,
            retry_admitted=False,
            reason=RefusalCode.UNSAFE_RETRY_REFUSED.value,
        )
    if action.idempotency not in {
        IdempotencyClass.IDEMPOTENT,
        IdempotencyClass.CONDITIONALLY_IDEMPOTENT,
    }:
        return ReconciliationResult(
            disposition=ReconciliationDisposition.RETRY_REFUSED,
            standing=Standing.REFUSED,
            observed_state_digest=reconciliation.observed_state_digest,
            verification_ref=reconciliation.verification_ref,
            retry_admitted=False,
            reason=RefusalCode.UNSAFE_RETRY_REFUSED.value,
        )
    return ReconciliationResult(
        disposition=ReconciliationDisposition.RETRY_ADMITTED,
        standing=Standing.CANDIDATE,
        observed_state_digest=reconciliation.observed_state_digest,
        verification_ref=reconciliation.verification_ref,
        retry_admitted=True,
        reason="RETRY_CANDIDATE_ADMITTED_AUTHORITY_STILL_REQUIRED",
    )
