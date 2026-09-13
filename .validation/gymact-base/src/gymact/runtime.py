"""Public GymAct runtimes over the hardened semantic kernel."""
from __future__ import annotations

import rfc8785

from gymact.kernel import BoundaryBlocked
from gymact.kernel import GymAct as _KernelGymAct
from gymact.models import ActuationIntent, ActuationResult, Operation, Receipt, Standing

_PRODUCTION_BRCE_SEAL = object()


class GymAct(_KernelGymAct):
    """Reference kernel with RFC8785 failures promoted to typed boundary standing."""

    def _ensure_input(self, value: object) -> None:
        try:
            super()._ensure_input(value)
        except rfc8785.CanonicalizationError as exc:
            raise BoundaryBlocked("INPUT_NOT_RFC8785_CANONICAL") from exc

    def _ensure_state(self, value: object) -> None:
        try:
            super()._ensure_state(value)
        except rfc8785.CanonicalizationError as exc:
            raise BoundaryBlocked("STATE_NOT_RFC8785_CANONICAL") from exc

    def _ensure_checkpoint(self, value: object) -> None:
        try:
            super()._ensure_checkpoint(value)
        except rfc8785.CanonicalizationError as exc:
            raise BoundaryBlocked("CHECKPOINT_NOT_RFC8785_CANONICAL") from exc


class ProductionGymAct(GymAct):
    """Production runtime whose consequential ``act`` port is BRCE-exclusive.

    ``GymAct`` remains the compatibility/reference kernel for existing integrations and
    conformance tests. Production surfaces should instantiate this class. A direct call
    to ``act`` is a typed, receipted refusal; ``BRCEBroker`` alone receives the sealed
    private DO port after an identity-bound ExecutionGrant has been admitted.
    """

    async def act(self, intent: ActuationIntent) -> ActuationResult:
        state = self._state(intent.episode_id)
        async with state.lock:
            before = await self._observe_unlocked(state)
            receipt = Receipt(
                episode_id=intent.episode_id,
                operation=Operation.ACT,
                standing=Standing.REFUSED,
                subject_ref=state.environment.environment_id,
                capability_ref=intent.capability,
                authority_ref=intent.authority_ref,
                idempotency_key=intent.idempotency_key,
                pre_state_digest=before.state_digest,
                post_state_digest=before.state_digest,
                acknowledgement_status="NOT_ATTEMPTED",
                world_changed=False,
                verified=False,
                reason="BRCE_EXECUTION_GRANT_REQUIRED",
            )
            self._record(receipt)
            return ActuationResult(
                accepted=False,
                standing=Standing.REFUSED,
                observation=before,
                receipt=receipt,
            )

    async def _act_from_brce(
        self,
        intent: ActuationIntent,
        *,
        seal: object,
    ) -> ActuationResult:
        """Sealed DO port consumed by BRCE only after execution-grant admission."""
        if seal is not _PRODUCTION_BRCE_SEAL:
            state = self._state(intent.episode_id)
            async with state.lock:
                before = await self._observe_unlocked(state)
                receipt = Receipt(
                    episode_id=intent.episode_id,
                    operation=Operation.ACT,
                    standing=Standing.REFUSED,
                    subject_ref=state.environment.environment_id,
                    capability_ref=intent.capability,
                    authority_ref=intent.authority_ref,
                    idempotency_key=intent.idempotency_key,
                    pre_state_digest=before.state_digest,
                    post_state_digest=before.state_digest,
                    acknowledgement_status="NOT_ATTEMPTED",
                    world_changed=False,
                    verified=False,
                    reason="BRCE_EXECUTION_SEAL_REFUSED",
                )
                self._record(receipt)
                return ActuationResult(
                    accepted=False,
                    standing=Standing.REFUSED,
                    observation=before,
                    receipt=receipt,
                )
        return await super().act(intent)


__all__ = ["BoundaryBlocked", "GymAct", "ProductionGymAct"]
