from __future__ import annotations

import importlib.util
import sys
import unittest
from dataclasses import replace
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "autofde_lab"
    / "reflex"
    / "promotion.py"
)
SPEC = importlib.util.spec_from_file_location(
    "autofde_lab_reflex_promotion", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
promotion = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = promotion
SPEC.loader.exec_module(promotion)

CandidateHook = promotion.CandidateHook
cognition_elimination_rate = promotion.cognition_elimination_rate
EpisodeEvidence = promotion.EpisodeEvidence
EvidenceKind = promotion.EvidenceKind
HookClass = promotion.HookClass
HookEnvelope = promotion.HookEnvelope
implementation_digest = promotion.implementation_digest
Observation = promotion.Observation
PromotionCourt = promotion.PromotionCourt
PromotionRefusal = promotion.PromotionRefusal
RouteDecision = promotion.RouteDecision
route_promoted_hook = promotion.route_promoted_hook


DIGEST = implementation_digest(b"known-safe-hook-v1")


def envelope(*, compensation: str | None = None) -> HookEnvelope:
    return HookEnvelope(
        subjects=frozenset({"urn:tenant:acme"}),
        action="urn:action:restart-service",
        scopes=frozenset({"urn:scope:service-a"}),
        policy="urn:policy:sre-bounded-restart",
        verifier="urn:verifier:service-health",
        max_age_ticks=5,
        compensation=compensation,
    )


def hook(
    hook_class: HookClass = HookClass.ACTUATION, **changes: object
) -> CandidateHook:
    value = CandidateHook(
        hook_id="urn:hook:restart-service-after-known-failure",
        hook_class=hook_class,
        implementation_digest=DIGEST,
        predicate_id="urn:predicate:known-failure-signature",
        envelope=envelope(
            compensation=(
                "urn:compensate:restore-service"
                if hook_class is HookClass.REFLEX
                else None
            )
        ),
    )
    return replace(value, **changes)


def receipt(
    evidence_id: str,
    kind: EvidenceKind = EvidenceKind.POSITIVE,
    **changes: object,
) -> EpisodeEvidence:
    value = EpisodeEvidence(
        evidence_id=evidence_id,
        kind=kind,
        standing="ALIVE",
        hook_id="urn:hook:restart-service-after-known-failure",
        implementation_digest=DIGEST,
        subject="urn:tenant:acme",
        action="urn:action:restart-service",
        scope="urn:scope:service-a",
        policy="urn:policy:sre-bounded-restart",
        verifier="urn:verifier:service-health",
        postcondition_verified=True,
        replay_verified=True,
        falsifier_killed=kind is EvidenceKind.FALSIFIER,
    )
    return replace(value, **changes)


def evidence() -> list[EpisodeEvidence]:
    return [
        receipt("urn:receipt:positive-1"),
        receipt("urn:receipt:positive-2"),
        receipt("urn:receipt:counterfactual-1", EvidenceKind.FALSIFIER),
    ]


class PromotionCourtTests(unittest.TestCase):
    def setUp(self) -> None:
        self.court = PromotionCourt()

    def test_actuation_hook_promotes_to_powerless_brce_fast_path(self) -> None:
        promoted = self.court.evaluate(hook(), evidence())
        result = route_promoted_hook(
            promoted,
            Observation(
                subject="urn:tenant:acme",
                scope="urn:scope:service-a",
                policy="urn:policy:sre-bounded-restart",
                age_ticks=2,
                predicate_matches=True,
            ),
        )

        self.assertEqual("CANDIDATE", promoted.standing)
        self.assertEqual(RouteDecision.BRCE_ELIGIBLE, result.decision)
        self.assertFalse(result.cognition_required)
        self.assertIsNotNone(result.request)
        assert result.request is not None
        self.assertFalse(result.request.do_authority)
        self.assertIsNone(result.request.authority_grant)
        self.assertEqual(promoted.promotion_digest, result.request.promotion_digest)

    def test_reflex_hook_requires_compensation_and_can_promote(self) -> None:
        promoted = self.court.evaluate(hook(HookClass.REFLEX), evidence())
        self.assertEqual(HookClass.REFLEX, promoted.hook_class)
        self.assertIsNotNone(promoted.envelope.compensation)

        with self.assertRaisesRegex(
            PromotionRefusal, "REFUSED:REFLEX_COMPENSATION_REQUIRED"
        ):
            self.court.evaluate(hook(HookClass.REFLEX, envelope=envelope()), evidence())

    def test_construct_hook_never_enters_fast_path(self) -> None:
        with self.assertRaisesRegex(PromotionRefusal, "REFUSED:CONSTRUCT_ONLY"):
            self.court.evaluate(hook(HookClass.CONSTRUCT), evidence())

    def test_direct_do_brce_bypass_and_embedded_authority_are_refused(self) -> None:
        attacks = [
            (hook(direct_do_authority=True), "REFUSED:DIRECT_DO_AUTHORITY"),
            (hook(requires_brce=False), "REFUSED:BRCE_BYPASS"),
            (hook(embedded_authority_token="secret"), "REFUSED:EMBEDDED_AUTHORITY"),
        ]
        for attacked, refusal in attacks:
            with (
                self.subTest(refusal=refusal),
                self.assertRaisesRegex(PromotionRefusal, refusal),
            ):
                self.court.evaluate(attacked, evidence())

    def test_duplicate_receipt_does_not_satisfy_independent_evidence_threshold(
        self,
    ) -> None:
        duplicate = receipt("urn:receipt:positive-1")
        with self.assertRaisesRegex(
            PromotionRefusal, "REFUSED:INSUFFICIENT_POSITIVE_EVIDENCE"
        ):
            self.court.evaluate(
                hook(),
                [
                    duplicate,
                    duplicate,
                    receipt("urn:receipt:f1", EvidenceKind.FALSIFIER),
                ],
            )

    def test_missing_or_unproven_falsifier_is_refused(self) -> None:
        with self.assertRaisesRegex(
            PromotionRefusal, "REFUSED:INSUFFICIENT_FALSIFIERS"
        ):
            self.court.evaluate(hook(), evidence()[:2])
        with self.assertRaisesRegex(PromotionRefusal, "REFUSED:FALSIFIER_NOT_PROVEN"):
            self.court.evaluate(
                hook(),
                evidence()[:2]
                + [
                    receipt(
                        "urn:receipt:f1",
                        EvidenceKind.FALSIFIER,
                        falsifier_killed=False,
                    )
                ],
            )

    def test_unverified_positive_evidence_is_refused(self) -> None:
        for field in ("postcondition_verified", "replay_verified"):
            bad = replace(receipt("urn:receipt:positive-2"), **{field: False})
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(PromotionRefusal, "REFUSED:POSITIVE_NOT_ALIVE"),
            ):
                self.court.evaluate(
                    hook(),
                    [
                        receipt("urn:receipt:positive-1"),
                        bad,
                        receipt("urn:receipt:f1", EvidenceKind.FALSIFIER),
                    ],
                )

    def test_digest_authority_and_scope_drift_fail_closed(self) -> None:
        attacks = [
            (
                receipt(
                    "urn:receipt:p2",
                    implementation_digest="sha256:" + "0" * 64,
                ),
                "REFUSED:EVIDENCE_BINDING_DRIFT",
            ),
            (
                receipt("urn:receipt:p2", action="urn:action:delete-everything"),
                "REFUSED:EVIDENCE_BINDING_DRIFT",
            ),
            (
                receipt("urn:receipt:p2", policy="urn:policy:other"),
                "REFUSED:EVIDENCE_BINDING_DRIFT",
            ),
            (
                receipt("urn:receipt:p2", subject="urn:tenant:other"),
                "REFUSED:EVIDENCE_SCOPE_DRIFT",
            ),
            (
                receipt("urn:receipt:p2", scope="urn:scope:other"),
                "REFUSED:EVIDENCE_SCOPE_DRIFT",
            ),
        ]
        for attacked, refusal in attacks:
            with (
                self.subTest(refusal=refusal),
                self.assertRaisesRegex(PromotionRefusal, refusal),
            ):
                self.court.evaluate(
                    hook(),
                    [
                        receipt("urn:receipt:p1"),
                        attacked,
                        receipt("urn:receipt:f1", EvidenceKind.FALSIFIER),
                    ],
                )

    def test_out_of_envelope_observations_escalate_to_cognition(self) -> None:
        promoted = self.court.evaluate(hook(), evidence())
        attacks = [
            Observation(
                "urn:tenant:other",
                "urn:scope:service-a",
                "urn:policy:sre-bounded-restart",
                1,
                True,
            ),
            Observation(
                "urn:tenant:acme",
                "urn:scope:other",
                "urn:policy:sre-bounded-restart",
                1,
                True,
            ),
            Observation(
                "urn:tenant:acme",
                "urn:scope:service-a",
                "urn:policy:other",
                1,
                True,
            ),
            Observation(
                "urn:tenant:acme",
                "urn:scope:service-a",
                "urn:policy:sre-bounded-restart",
                6,
                True,
            ),
            Observation(
                "urn:tenant:acme",
                "urn:scope:service-a",
                "urn:policy:sre-bounded-restart",
                1,
                False,
            ),
        ]
        for observation in attacks:
            with self.subTest(observation=observation):
                result = route_promoted_hook(promoted, observation)
                self.assertEqual(RouteDecision.ESCALATE_TO_COGNITION, result.decision)
                self.assertTrue(result.cognition_required)
                self.assertIsNone(result.request)

    def test_promotion_receipt_is_deterministic_and_evidence_order_independent(
        self,
    ) -> None:
        forward = self.court.evaluate(hook(), evidence())
        reverse = self.court.evaluate(hook(), reversed(evidence()))
        self.assertEqual(forward.promotion_digest, reverse.promotion_digest)
        self.assertEqual(forward.evidence_ids, reverse.evidence_ids)

    def test_evidence_id_collision_is_refused(self) -> None:
        first = receipt("urn:receipt:collision")
        second = replace(first, postcondition_verified=False)
        with self.assertRaisesRegex(PromotionRefusal, "REFUSED:EVIDENCE_ID_COLLISION"):
            self.court.evaluate(
                hook(),
                [
                    first,
                    second,
                    receipt("urn:receipt:p2"),
                    receipt("urn:receipt:f1", EvidenceKind.FALSIFIER),
                ],
            )

    def test_cognition_elimination_rate_measures_compiled_known_patterns(
        self,
    ) -> None:
        self.assertEqual(0.0, cognition_elimination_rate(100, 100))
        self.assertEqual(0.95, cognition_elimination_rate(100, 5))
        self.assertEqual(1.0, cognition_elimination_rate(100, 0))
        with self.assertRaises(ValueError):
            cognition_elimination_rate(0, 0)


if __name__ == "__main__":
    unittest.main()
