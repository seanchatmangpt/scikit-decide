"""Knowledge Hook promotion court for compiling cognition into bounded reflexes.

AutoFDE Lab remains non-actuating. This module can prove that a deterministic hook is
eligible for downstream production admission and can manufacture a powerless BRCE request.
It never executes that request and never grants DO authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

CONSEQUENCE_IR_PACK = "ggen-marketplace:consequence-ir-pack@0.2.0"
PROMOTION_SCHEMA = "urn:autofde-lab:knowledge-hook-promotion:v1"


class HookClass(str, Enum):
    CONSTRUCT = "CONSTRUCT"
    ACTUATION = "ACTUATION"
    REFLEX = "REFLEX"


class EvidenceKind(str, Enum):
    POSITIVE = "POSITIVE"
    FALSIFIER = "FALSIFIER"


class RouteDecision(str, Enum):
    BRCE_ELIGIBLE = "BRCE_ELIGIBLE"
    ESCALATE_TO_COGNITION = "ESCALATE_TO_COGNITION"


class PromotionRefusal(ValueError):
    """Fail-closed refusal raised by the promotion court."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class HookEnvelope:
    """Exact subject/action/scope/policy and verification boundary for a hook."""

    subjects: frozenset[str]
    action: str
    scopes: frozenset[str]
    policy: str
    verifier: str
    max_age_ticks: int
    compensation: str | None = None

    def __post_init__(self) -> None:
        if not self.subjects or not self.scopes:
            raise PromotionRefusal(
                "REFUSED:VACUOUS_ENVELOPE", "subjects and scopes are required"
            )
        if not self.action or not self.policy or not self.verifier:
            raise PromotionRefusal(
                "REFUSED:VACUOUS_ENVELOPE",
                "action, policy, and verifier are required",
            )
        if self.max_age_ticks <= 0:
            raise PromotionRefusal(
                "REFUSED:VACUOUS_ENVELOPE", "max_age_ticks must be positive"
            )


@dataclass(frozen=True)
class CandidateHook:
    hook_id: str
    hook_class: HookClass
    implementation_digest: str
    predicate_id: str
    envelope: HookEnvelope
    direct_do_authority: bool = False
    requires_brce: bool = True
    embedded_authority_token: str | None = None

    def __post_init__(self) -> None:
        if not self.hook_id or not self.predicate_id:
            raise PromotionRefusal(
                "REFUSED:INVALID_HOOK", "hook_id and predicate_id are required"
            )
        if not self.implementation_digest.startswith("sha256:"):
            raise PromotionRefusal(
                "REFUSED:INVALID_DIGEST",
                "implementation digest must be sha256-bound",
            )


@dataclass(frozen=True)
class EpisodeEvidence:
    evidence_id: str
    kind: EvidenceKind
    standing: str
    hook_id: str
    implementation_digest: str
    subject: str
    action: str
    scope: str
    policy: str
    verifier: str
    postcondition_verified: bool
    replay_verified: bool
    falsifier_killed: bool = False


@dataclass(frozen=True)
class PromotionCandidate:
    """Lab output: evidence-bound candidate for production admission, not authority."""

    schema: str
    hook_id: str
    hook_class: HookClass
    implementation_digest: str
    envelope: HookEnvelope
    evidence_ids: tuple[str, ...]
    promotion_digest: str
    standing: str = "CANDIDATE"
    requires_brce: bool = True
    direct_do_authority: bool = False
    consequence_ir_pack: str = CONSEQUENCE_IR_PACK


@dataclass(frozen=True)
class Observation:
    subject: str
    scope: str
    policy: str
    age_ticks: int
    predicate_matches: bool


@dataclass(frozen=True)
class BrceRequest:
    """Powerless request data. Production BRCE must independently admit authority."""

    promotion_digest: str
    hook_id: str
    subject: str
    action: str
    scope: str
    policy: str
    verifier: str
    authority_grant: None = None
    do_authority: bool = False


@dataclass(frozen=True)
class RouteResult:
    decision: RouteDecision
    request: BrceRequest | None
    reason: str
    cognition_required: bool


class PromotionCourt:
    """Falsification court for converting repeated cognition into deterministic reflexes."""

    def __init__(
        self, minimum_positive_receipts: int = 2, minimum_falsifiers: int = 1
    ) -> None:
        if minimum_positive_receipts < 2:
            raise ValueError(
                "promotion requires at least two independent positive receipts"
            )
        if minimum_falsifiers < 1:
            raise ValueError("promotion requires at least one falsifier")
        self.minimum_positive_receipts = minimum_positive_receipts
        self.minimum_falsifiers = minimum_falsifiers

    def evaluate(
        self, hook: CandidateHook, evidence: Iterable[EpisodeEvidence]
    ) -> PromotionCandidate:
        if hook.hook_class is HookClass.CONSTRUCT:
            raise PromotionRefusal(
                "REFUSED:CONSTRUCT_ONLY",
                "construct hooks cannot enter the BRCE fast path",
            )
        if hook.direct_do_authority:
            raise PromotionRefusal(
                "REFUSED:DIRECT_DO_AUTHORITY",
                "hooks may request BRCE but may never own DO",
            )
        if not hook.requires_brce:
            raise PromotionRefusal(
                "REFUSED:BRCE_BYPASS", "promoted hooks must route through BRCE"
            )
        if hook.embedded_authority_token is not None:
            raise PromotionRefusal(
                "REFUSED:EMBEDDED_AUTHORITY",
                "authority must be external to the hook bundle",
            )
        if hook.hook_class is HookClass.REFLEX and not hook.envelope.compensation:
            raise PromotionRefusal(
                "REFUSED:REFLEX_COMPENSATION_REQUIRED",
                "reflex hooks require bounded compensation",
            )

        unique: dict[str, EpisodeEvidence] = {}
        for receipt in evidence:
            prior = unique.get(receipt.evidence_id)
            if prior is not None and prior != receipt:
                raise PromotionRefusal(
                    "REFUSED:EVIDENCE_ID_COLLISION", receipt.evidence_id
                )
            unique[receipt.evidence_id] = receipt

        positives = []
        falsifiers = []
        for receipt in unique.values():
            self._validate_binding(hook, receipt)
            if receipt.kind is EvidenceKind.POSITIVE:
                if (
                    receipt.standing != "ALIVE"
                    or not receipt.postcondition_verified
                    or not receipt.replay_verified
                ):
                    raise PromotionRefusal(
                        "REFUSED:POSITIVE_NOT_ALIVE", receipt.evidence_id
                    )
                positives.append(receipt)
            else:
                if not receipt.falsifier_killed or receipt.standing not in {
                    "ALIVE",
                    "REFUSED",
                }:
                    raise PromotionRefusal(
                        "REFUSED:FALSIFIER_NOT_PROVEN", receipt.evidence_id
                    )
                falsifiers.append(receipt)

        if len(positives) < self.minimum_positive_receipts:
            raise PromotionRefusal(
                "REFUSED:INSUFFICIENT_POSITIVE_EVIDENCE", str(len(positives))
            )
        if len(falsifiers) < self.minimum_falsifiers:
            raise PromotionRefusal(
                "REFUSED:INSUFFICIENT_FALSIFIERS", str(len(falsifiers))
            )

        evidence_ids = tuple(sorted(unique))
        digest = self._promotion_digest(hook, evidence_ids)
        return PromotionCandidate(
            schema=PROMOTION_SCHEMA,
            hook_id=hook.hook_id,
            hook_class=hook.hook_class,
            implementation_digest=hook.implementation_digest,
            envelope=hook.envelope,
            evidence_ids=evidence_ids,
            promotion_digest=digest,
        )

    @staticmethod
    def _validate_binding(hook: CandidateHook, receipt: EpisodeEvidence) -> None:
        expected = {
            "hook_id": hook.hook_id,
            "implementation_digest": hook.implementation_digest,
            "action": hook.envelope.action,
            "policy": hook.envelope.policy,
            "verifier": hook.envelope.verifier,
        }
        actual = {
            "hook_id": receipt.hook_id,
            "implementation_digest": receipt.implementation_digest,
            "action": receipt.action,
            "policy": receipt.policy,
            "verifier": receipt.verifier,
        }
        if actual != expected:
            raise PromotionRefusal(
                "REFUSED:EVIDENCE_BINDING_DRIFT", receipt.evidence_id
            )
        if (
            receipt.subject not in hook.envelope.subjects
            or receipt.scope not in hook.envelope.scopes
        ):
            raise PromotionRefusal("REFUSED:EVIDENCE_SCOPE_DRIFT", receipt.evidence_id)

    @staticmethod
    def _promotion_digest(hook: CandidateHook, evidence_ids: tuple[str, ...]) -> str:
        payload = {
            "schema": PROMOTION_SCHEMA,
            "hook_id": hook.hook_id,
            "hook_class": hook.hook_class.value,
            "implementation_digest": hook.implementation_digest,
            "predicate_id": hook.predicate_id,
            "subjects": sorted(hook.envelope.subjects),
            "action": hook.envelope.action,
            "scopes": sorted(hook.envelope.scopes),
            "policy": hook.envelope.policy,
            "verifier": hook.envelope.verifier,
            "max_age_ticks": hook.envelope.max_age_ticks,
            "compensation": hook.envelope.compensation,
            "requires_brce": hook.requires_brce,
            "evidence_ids": list(evidence_ids),
            "consequence_ir_pack": CONSEQUENCE_IR_PACK,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(canonical).hexdigest()


def route_promoted_hook(
    promotion: PromotionCandidate, observation: Observation
) -> RouteResult:
    """Select the BRCE fast path only inside the exact promoted envelope.

    This function does not call BRCE. It manufactures powerless request data that a production
    broker must independently authorize.
    """

    envelope = promotion.envelope
    reasons = []
    if not observation.predicate_matches:
        reasons.append("predicate")
    if observation.subject not in envelope.subjects:
        reasons.append("subject")
    if observation.scope not in envelope.scopes:
        reasons.append("scope")
    if observation.policy != envelope.policy:
        reasons.append("policy")
    if observation.age_ticks < 0 or observation.age_ticks > envelope.max_age_ticks:
        reasons.append("time")

    if reasons:
        return RouteResult(
            decision=RouteDecision.ESCALATE_TO_COGNITION,
            request=None,
            reason="OUTSIDE_PROMOTED_ENVELOPE:" + ",".join(reasons),
            cognition_required=True,
        )

    request = BrceRequest(
        promotion_digest=promotion.promotion_digest,
        hook_id=promotion.hook_id,
        subject=observation.subject,
        action=envelope.action,
        scope=observation.scope,
        policy=envelope.policy,
        verifier=envelope.verifier,
    )
    return RouteResult(
        decision=RouteDecision.BRCE_ELIGIBLE,
        request=request,
        reason="PROMOTED_PATTERN_MATCH",
        cognition_required=False,
    )


def cognition_elimination_rate(initial_cognitive: int, current_cognitive: int) -> float:
    """Fraction of initially cognitive episodes compiled into deterministic machinery."""

    if initial_cognitive <= 0:
        raise ValueError("initial_cognitive must be positive")
    if current_cognitive < 0 or current_cognitive > initial_cognitive:
        raise ValueError("current_cognitive must be within [0, initial_cognitive]")
    return 1.0 - (current_cognitive / initial_cognitive)


def implementation_digest(source: bytes) -> str:
    return "sha256:" + hashlib.sha256(source).hexdigest()
