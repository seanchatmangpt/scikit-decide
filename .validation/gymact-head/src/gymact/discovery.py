"""BRCE-exclusive black-box probing and replay for procedure discovery."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from gymact.action_contract import (
    ActionDefinition,
    AuthorityRequirement,
    ExecutionGrant,
    IdempotencyClass,
    SubjectRef,
    VerificationKind,
    VerificationStrategy,
    construct_prepared_action,
)
from gymact.brce import BRCEBroker, BrokerRequest
from gymact.models import FrozenModel, Standing
from gymact.runtime import ProductionGymAct


class ProbeEvidence(FrozenModel):
    action_id: str
    prefix: tuple[str, ...]
    accepted: bool
    standing: Standing
    before_facts: tuple[str, ...]
    after_facts: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    reason: str | None = None


class ReplayEvidence(FrozenModel):
    plan: tuple[str, ...]
    goal_reached: bool
    standing: Standing
    final_facts: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    ocel_log: dict[str, Any]


class DiscoveryProbeRunner:
    """Execute planner-authored probes through ProductionGymAct + BRCE only."""

    def __init__(
        self,
        runtime: ProductionGymAct,
        *,
        provider: str,
        subject: str,
        private_config: dict[str, Any],
        authority_ref: str = "urn:gymact:authority:autonomous-discovery",
        principal: str = "urn:gymact:principal:autofde-lab",
    ) -> None:
        self.runtime = runtime
        self.provider = provider
        self.subject = subject
        self.private_config = dict(private_config)
        self.authority_ref = authority_ref
        self.principal = principal
        self._broker = BRCEBroker(runtime)

    async def challenge(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        materialized = await self.runtime.create_episode(
            self.provider,
            scenario=self.subject,
            config=self.private_config,
            idempotency_key=f"challenge-{uuid4().hex}",
        )
        if (
            not materialized.accepted
            or materialized.episode is None
            or materialized.observation is None
        ):
            raise RuntimeError(
                f"DISCOVERY_MATERIALIZATION_FAILED:{materialized.receipt.reason}"
            )
        episode_id = materialized.episode.episode_id
        try:
            facts = self._facts(materialized.observation.state)
            capabilities = tuple(
                cap.iri for cap in self.runtime.capabilities(episode_id)
            )
            return facts, capabilities
        finally:
            await self.runtime.teardown(episode_id)

    @staticmethod
    def _facts(state: dict[str, Any]) -> tuple[str, ...]:
        raw = state.get("facts")
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise RuntimeError("OPAQUE_OBSERVATION_FACTS_REQUIRED")
        return tuple(sorted(raw))

    def _action(
        self, *, capability_ref: str, environment_id: str
    ) -> ActionDefinition:
        return ActionDefinition(
            semantic_id=(
                "urn:gymact:discovery:action:"
                f"{capability_ref.rsplit(':', 1)[-1]}"
            ),
            provider_ref=environment_id,
            capability_ref=capability_ref,
            subject_type="urn:gymact:opaque:subject",
            input_schema={"type": "object", "additionalProperties": False},
            authority=AuthorityRequirement(capability_refs=(capability_ref,)),
            expected_effects=(),
            verification=VerificationStrategy(
                kind=VerificationKind.PREDICATE,
                observer_ref=environment_id,
                expected={},
            ),
            idempotency=IdempotencyClass.UNKNOWN,
        )

    async def _execute(
        self,
        *,
        episode_id: str,
        environment_id: str,
        capability_ref: str,
        expected: dict[str, Any],
    ):
        observation = await self.runtime.observe(episode_id)
        action = self._action(
            capability_ref=capability_ref,
            environment_id=environment_id,
        )
        subject = SubjectRef(semantic_id=self.subject, provider_ref=environment_id)
        key = f"probe-{uuid4().hex}"
        prepared = construct_prepared_action(
            action,
            episode_id=episode_id,
            subject=subject,
            payload={},
            admission_digest=observation.state_digest,
            idempotency_key=key,
        )
        grant = ExecutionGrant(
            principal=self.principal,
            action_ref=action.semantic_id,
            subject=subject,
            capability_ref=capability_ref,
            authority_ref=self.authority_ref,
            policy_revision="autonomous-discovery-v1",
            admitted_observation_ref=observation.state_digest,
            intended_effects=action.expected_effects,
            scope_refs=(self.subject, environment_id),
            nonce=uuid4().hex,
        )
        return await self._broker.execute(
            BrokerRequest(
                action=action,
                prepared=prepared,
                grant=grant,
                expected=expected,
            )
        )

    async def probe(
        self, *, prefix: tuple[str, ...], action_id: str
    ) -> ProbeEvidence:
        materialized = await self.runtime.create_episode(
            self.provider,
            scenario=self.subject,
            config=self.private_config,
            idempotency_key=f"probe-episode-{uuid4().hex}",
        )
        if not materialized.accepted or materialized.episode is None:
            raise RuntimeError(
                f"DISCOVERY_MATERIALIZATION_FAILED:{materialized.receipt.reason}"
            )
        episode_id = materialized.episode.episode_id
        environment_id = materialized.episode.environment_id
        try:
            for replay_action in prefix:
                transition = await self._execute(
                    episode_id=episode_id,
                    environment_id=environment_id,
                    capability_ref=replay_action,
                    expected={},
                )
                if transition.standing is not Standing.ALIVE:
                    raise RuntimeError(
                        "DISCOVERY_PREFIX_REPLAY_FAILED:"
                        f"{replay_action}:{transition.receipt.reason}"
                    )
            before = await self.runtime.observe(episode_id)
            transition = await self._execute(
                episode_id=episode_id,
                environment_id=environment_id,
                capability_ref=action_id,
                expected={},
            )
            after = await self.runtime.observe(episode_id)
            receipts = self.runtime.episode_receipts(episode_id)
            return ProbeEvidence(
                action_id=action_id,
                prefix=prefix,
                accepted=transition.actuation.accepted,
                standing=transition.standing,
                before_facts=self._facts(before.state),
                after_facts=self._facts(after.state),
                receipt_ids=tuple(receipt.receipt_id for receipt in receipts),
                reason=transition.receipt.reason,
            )
        finally:
            await self.runtime.teardown(episode_id)

    async def replay(self, *, plan: tuple[str, ...]) -> ReplayEvidence:
        """Execute a discovered plan from scratch and verify the hidden provider goal."""
        if not plan:
            raise ValueError("DISCOVERED_PLAN_MUST_BE_NON_EMPTY")
        materialized = await self.runtime.create_episode(
            self.provider,
            scenario=self.subject,
            config=self.private_config,
            idempotency_key=f"replay-episode-{uuid4().hex}",
        )
        if not materialized.accepted or materialized.episode is None:
            raise RuntimeError(
                f"DISCOVERY_MATERIALIZATION_FAILED:{materialized.receipt.reason}"
            )
        episode_id = materialized.episode.episode_id
        environment_id = materialized.episode.environment_id
        final_transition = None
        for index, action_id in enumerate(plan):
            expected = {"goal_reached": True} if index == len(plan) - 1 else {}
            final_transition = await self._execute(
                episode_id=episode_id,
                environment_id=environment_id,
                capability_ref=action_id,
                expected=expected,
            )
            if final_transition.standing is not Standing.ALIVE:
                break
        observation = await self.runtime.observe(episode_id)
        verification = await self.runtime.verify(
            episode_id, {"goal_reached": True}
        )
        await self.runtime.teardown(episode_id)
        receipts = self.runtime.episode_receipts(episode_id)
        log = self.runtime.episode_ocel_log(episode_id)
        standing = (
            Standing.ALIVE
            if final_transition is not None
            and final_transition.standing is Standing.ALIVE
            and verification.passed
            else Standing.REFUSED
        )
        return ReplayEvidence(
            plan=plan,
            goal_reached=verification.passed,
            standing=standing,
            final_facts=self._facts(observation.state),
            receipt_ids=tuple(receipt.receipt_id for receipt in receipts),
            ocel_log=log,
        )
