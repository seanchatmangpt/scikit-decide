"""Verified-consequence execution and reconciliation above the generic GymAct kernel."""

from __future__ import annotations

from typing import Any, Protocol

from gymact.action_contract import (
    ActionDefinition,
    ExecutionGrant,
    PreparedAction,
    ReconciliationDisposition,
    ReconciliationResult,
    admit_execution,
)
from gymact.models import (
    ActuationIntent,
    ActuationResult,
    FrozenModel,
    Operation,
    Receipt,
    Standing,
    VerificationResult,
)


class CrownRuntimeLike(Protocol):
    async def act(self, intent: ActuationIntent) -> ActuationResult: ...

    async def verify(
        self, episode_id: str, expected: dict[str, Any]
    ) -> VerificationResult: ...

    def _record(self, receipt: Receipt) -> Receipt: ...


class VerifiedTransition(FrozenModel):
    """One candidate DO path with objective-verification standing kept explicit."""

    standing: Standing
    actuation: ActuationResult
    verification: VerificationResult | None = None
    receipt: Receipt


class ReconciledTransition(FrozenModel):
    """Observed disposition of a prior uncertain execution; never an implicit retry."""

    reconciliation: ReconciliationResult
    verification: VerificationResult
    receipt: Receipt


def _world_changed(receipt: Receipt) -> bool | None:
    if receipt.pre_state_digest is None or receipt.post_state_digest is None:
        return None
    return receipt.pre_state_digest != receipt.post_state_digest


def _possible_unacknowledged_effect(result: ActuationResult) -> bool:
    receipt = result.receipt
    if receipt.reason == "ACTUATION_TIMEOUT":
        return True
    return not result.accepted and _world_changed(receipt) is True


def _verification_receipt(
    *,
    actuation: ActuationResult,
    verification: VerificationResult,
    standing: Standing,
    reason: str | None,
) -> Receipt:
    source = actuation.receipt
    return Receipt(
        episode_id=source.episode_id,
        operation=Operation.VERIFY,
        standing=standing,
        subject_ref=source.subject_ref,
        capability_ref=source.capability_ref,
        authority_ref=source.authority_ref,
        authority_evidence_ref=source.authority_evidence_ref,
        principal=source.principal,
        delegated_principal=source.delegated_principal,
        policy_revision=source.policy_revision,
        intended_effects=source.intended_effects,
        idempotency_key=source.idempotency_key,
        pre_state_digest=source.pre_state_digest,
        post_state_digest=verification.state_digest,
        acknowledgement_status="ACKNOWLEDGED" if actuation.accepted else "UNKNOWN",
        world_changed=_world_changed(source),
        verification_id=verification.verification_id,
        verified=verification.passed,
        observation_confidence=source.observation_confidence,
        parent_receipt_ids=(source.receipt_id,),
        reason=reason,
    )


async def execute_verified(
    runtime: CrownRuntimeLike,
    intent: ActuationIntent,
    expected: dict[str, Any],
) -> VerifiedTransition:
    """DO then independently verify; only the verified transition may be Crown ALIVE."""

    actuation = await runtime.act(intent)
    if not actuation.accepted:
        if _possible_unacknowledged_effect(actuation):
            source = actuation.receipt
            uncertain = Receipt(
                episode_id=source.episode_id,
                operation=Operation.ACT,
                standing=Standing.UNCERTAIN,
                subject_ref=source.subject_ref,
                capability_ref=source.capability_ref,
                authority_ref=source.authority_ref,
                authority_evidence_ref=source.authority_evidence_ref,
                principal=source.principal,
                delegated_principal=source.delegated_principal,
                policy_revision=source.policy_revision,
                intended_effects=source.intended_effects,
                idempotency_key=source.idempotency_key,
                pre_state_digest=source.pre_state_digest,
                post_state_digest=source.post_state_digest,
                acknowledgement_status="LOST",
                world_changed=_world_changed(source),
                verified=False,
                parent_receipt_ids=(source.receipt_id,),
                error_digest=source.error_digest,
                reason="ACTUATION_OUTCOME_UNCERTAIN",
            )
            runtime._record(uncertain)
            return VerifiedTransition(
                standing=Standing.UNCERTAIN,
                actuation=actuation,
                receipt=uncertain,
            )
        return VerifiedTransition(
            standing=actuation.standing,
            actuation=actuation,
            receipt=actuation.receipt,
        )

    verification = await runtime.verify(intent.episode_id, expected)
    standing = Standing.ALIVE if verification.passed else Standing.REFUSED
    receipt = _verification_receipt(
        actuation=actuation,
        verification=verification,
        standing=standing,
        reason=None if verification.passed else "POSTCONDITION_FAILED",
    )
    runtime._record(receipt)
    return VerifiedTransition(
        standing=standing,
        actuation=actuation,
        verification=verification,
        receipt=receipt,
    )


async def reconcile_uncertain(
    runtime: CrownRuntimeLike,
    transition: VerifiedTransition,
    expected: dict[str, Any],
) -> ReconciledTransition:
    """Observe/verify an uncertain execution. This function never performs a retry."""

    if transition.standing is not Standing.UNCERTAIN:
        raise ValueError("RECONCILIATION_REQUIRES_UNCERTAIN_TRANSITION")

    verification = await runtime.verify(transition.actuation.receipt.episode_id, expected)
    source = transition.actuation.receipt
    if verification.passed:
        disposition = ReconciliationDisposition.EFFECT_CONFIRMED
        standing = Standing.ALIVE
        reason = "RECONCILIATION_EFFECT_CONFIRMED"
    elif (
        source.pre_state_digest is not None
        and verification.state_digest == source.pre_state_digest
    ):
        disposition = ReconciliationDisposition.NO_EFFECT
        standing = Standing.REFUSED
        reason = "RECONCILIATION_NO_EFFECT_RETRY_NOT_ADMITTED"
    else:
        disposition = ReconciliationDisposition.PARTIAL_EFFECT
        standing = Standing.UNCERTAIN
        reason = "RECONCILIATION_PARTIAL_EFFECT"

    reconciliation = ReconciliationResult(
        disposition=disposition,
        standing=standing,
        observed_state_digest=verification.state_digest,
        verification_ref=verification.verification_id,
        retry_admitted=False,
        reason=reason,
    )
    receipt = _verification_receipt(
        actuation=transition.actuation,
        verification=verification,
        standing=standing,
        reason=reason,
    )
    runtime._record(receipt)
    return ReconciledTransition(
        reconciliation=reconciliation,
        verification=verification,
        receipt=receipt,
    )


def _grant_fields(action: ActionDefinition, grant: ExecutionGrant) -> dict[str, Any]:
    return {
        "principal": grant.principal,
        "delegated_principal": grant.delegated_principal,
        "policy_revision": grant.policy_revision,
        "intended_effects": tuple(
            effect.model_dump(mode="json") for effect in action.expected_effects
        ),
    }


async def execute_admitted(
    runtime: CrownRuntimeLike,
    action: ActionDefinition,
    prepared: PreparedAction,
    grant: ExecutionGrant,
    *,
    current_revision: str | None,
    expected: dict[str, Any],
) -> VerifiedTransition:
    """Bridge CONSTRUCT to DO only after identity/revision admission closes."""

    admission = admit_execution(
        action,
        prepared,
        grant,
        current_revision=current_revision,
    )
    grant_fields = _grant_fields(action, grant)
    if not admission.admitted:
        receipt = Receipt(
            episode_id=prepared.episode_id,
            operation=Operation.ACT,
            standing=Standing.REFUSED,
            subject_ref=prepared.subject.provider_ref,
            capability_ref=action.capability_ref,
            authority_ref=grant.authority_ref,
            idempotency_key=prepared.idempotency_key,
            acknowledgement_status="NOT_ATTEMPTED",
            verified=False,
            reason=admission.reason,
            **grant_fields,
        )
        runtime._record(receipt)
        actuation = ActuationResult(
            accepted=False,
            standing=Standing.REFUSED,
            receipt=receipt,
        )
        return VerifiedTransition(
            standing=Standing.REFUSED,
            actuation=actuation,
            receipt=receipt,
        )

    intent = ActuationIntent(
        episode_id=prepared.episode_id,
        capability=action.capability_ref,
        payload=prepared.payload,
        authority_ref=grant.authority_ref,
        idempotency_key=prepared.idempotency_key,
    )
    transition = await execute_verified(runtime, intent, expected)
    source = transition.receipt
    bound = Receipt(
        episode_id=source.episode_id,
        operation=source.operation,
        standing=source.standing,
        subject_ref=prepared.subject.provider_ref,
        capability_ref=action.capability_ref,
        authority_ref=grant.authority_ref,
        authority_evidence_ref=source.authority_evidence_ref,
        idempotency_key=prepared.idempotency_key,
        pre_state_digest=source.pre_state_digest,
        post_state_digest=source.post_state_digest,
        acknowledgement_status=source.acknowledgement_status,
        world_changed=source.world_changed,
        verification_id=source.verification_id,
        verified=source.verified,
        observation_confidence=source.observation_confidence,
        parent_receipt_ids=(source.receipt_id,),
        error_digest=source.error_digest,
        reason=source.reason,
        **grant_fields,
    )
    runtime._record(bound)
    return VerifiedTransition(
        standing=transition.standing,
        actuation=transition.actuation,
        verification=transition.verification,
        receipt=bound,
    )
