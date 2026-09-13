# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.lab.graduation_packet`
(`V2030.1.1-PRD-ARD.md` capability 8: exact observations, policy identity,
benchmark corpus, results, falsifiers, limits, required downstream
admission).

Every collaborator is real: a real `CandidateHook`/`HookEnvelope`/
`EpisodeEvidence` built exactly as `tests/reflex/test_knowledge_hook_promotion.py`
builds them, a real `PromotionCourt.evaluate`, a real `PolicySpec.for_role`
and real `LeagueMatch` from `autofde_lab.planner_league.core`. Assertions
are on returned state only. No `unittest.mock` / `Mock` / `MagicMock` /
`patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from autofde_lab.lab.graduation_packet import (
    PROMOTION_GRADUATION_SCHEMA,
    PromotionGraduationPacket,
    build_promotion_graduation_packet,
)
from autofde_lab.planner_league.core import LeagueMatch, PolicySpec
from autofde_lab.reflex.promotion import (
    CandidateHook,
    EpisodeEvidence,
    EvidenceKind,
    HookClass,
    HookEnvelope,
    PromotionRefusal,
    implementation_digest,
)

DIGEST = implementation_digest(b"known-safe-hook-v1-cap8")


def _envelope() -> HookEnvelope:
    return HookEnvelope(
        subjects=frozenset({"urn:tenant:acme"}),
        action="urn:action:restart-service",
        scopes=frozenset({"urn:scope:service-a"}),
        policy="urn:policy:sre-bounded-restart",
        verifier="urn:verifier:service-health",
        max_age_ticks=5,
        compensation=None,
    )


def _hook() -> CandidateHook:
    return CandidateHook(
        hook_id="urn:hook:restart-service-after-known-failure",
        hook_class=HookClass.ACTUATION,
        implementation_digest=DIGEST,
        predicate_id="urn:predicate:known-failure-signature",
        envelope=_envelope(),
    )


def _receipt(
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


def _evidence() -> list[EpisodeEvidence]:
    return [
        _receipt("urn:receipt:positive-1"),
        _receipt("urn:receipt:positive-2"),
        _receipt("urn:receipt:counterfactual-1", EvidenceKind.FALSIFIER),
    ]


def _policy() -> PolicySpec:
    return PolicySpec.for_role("Astar", "red_disturbance")


def _match(world_id: str = "cyber_incident") -> LeagueMatch:
    policy = _policy()
    return LeagueMatch(
        world_id=world_id,
        left_role_id="red_disturbance",
        left_policy=policy,
        right_role_id="blue_defender",
        right_policy=PolicySpec.for_role("Astar", "blue_defender"),
    )


def test_packet_carries_exact_observations_policy_corpus_and_no_standing() -> None:
    match = _match()
    packet = build_promotion_graduation_packet(_hook(), _evidence(), _policy(), [match])

    assert isinstance(packet, PromotionGraduationPacket)
    assert packet.schema == PROMOTION_GRADUATION_SCHEMA
    assert hasattr(packet, "standing") is False
    assert hasattr(packet, "alive") is False

    # policy identity: the real PolicySpec, not a copied summary
    assert packet.policy == _policy()
    assert packet.policy.planner_id == "Astar"

    # benchmark corpus: real LeagueMatch identities, not opaque strings
    assert packet.benchmark_corpus == (match.identity_sha256,)

    # observations/falsifiers: exact EpisodeEvidence objects, not just ids
    assert len(packet.observations) == 2
    assert all(e.kind is EvidenceKind.POSITIVE for e in packet.observations)
    assert {e.evidence_id for e in packet.observations} == {
        "urn:receipt:positive-1",
        "urn:receipt:positive-2",
    }
    assert len(packet.falsifiers) >= 1
    assert all(e.falsifier_killed for e in packet.falsifiers)

    # results: derived from the exact same evidence, not a separate copy
    assert len(packet.results) == 3
    for (
        evidence_id,
        standing,
        postcondition_verified,
        replay_verified,
    ) in packet.results:
        assert standing == "ALIVE"
        assert postcondition_verified is True
        assert replay_verified is True
        assert evidence_id.startswith("urn:receipt:")

    # required downstream admission
    assert packet.required_downstream_admission == "autofde"
    assert packet.promotion.requires_brce is True
    assert packet.promotion.direct_do_authority is False

    # limits carry the real envelope bounds
    assert "LAB_ONLY" in packet.limits
    assert any("max_age_ticks=5" in limit for limit in packet.limits)


def test_packet_digest_is_deterministic_across_evidence_reordering() -> None:
    match = _match()
    evidence_forward = _evidence()
    evidence_reversed = list(reversed(_evidence()))

    packet_a = build_promotion_graduation_packet(
        _hook(), evidence_forward, _policy(), [match]
    )
    packet_b = build_promotion_graduation_packet(
        _hook(), evidence_reversed, _policy(), [match]
    )

    assert packet_a.packet_digest == packet_b.packet_digest


def test_packet_digest_is_sensitive_to_a_changed_policy() -> None:
    match = _match()
    packet_a = build_promotion_graduation_packet(
        _hook(), _evidence(), _policy(), [match]
    )
    changed_policy = PolicySpec.for_role(
        "Astar", "red_disturbance", budget_id="deep_search"
    )
    packet_b = build_promotion_graduation_packet(
        _hook(), _evidence(), changed_policy, [match]
    )

    assert packet_a.packet_digest != packet_b.packet_digest


def test_packet_digest_is_sensitive_to_a_changed_match() -> None:
    packet_a = build_promotion_graduation_packet(
        _hook(), _evidence(), _policy(), [_match("cyber_incident")]
    )
    packet_b = build_promotion_graduation_packet(
        _hook(), _evidence(), _policy(), [_match("generic_enterprise")]
    )

    assert packet_a.packet_digest != packet_b.packet_digest


def test_empty_benchmark_corpus_is_refused_not_silently_admitted() -> None:
    with pytest.raises(PromotionRefusal, match="REFUSED:CORPUS_EMPTY"):
        build_promotion_graduation_packet(_hook(), _evidence(), _policy(), [])


def test_insufficient_promotion_evidence_still_refuses_through_the_real_court() -> None:
    with pytest.raises(PromotionRefusal, match="REFUSED:INSUFFICIENT_FALSIFIERS"):
        build_promotion_graduation_packet(
            _hook(),
            [_receipt("urn:receipt:positive-1"), _receipt("urn:receipt:positive-2")],
            _policy(),
            [_match()],
        )


def test_packet_refuses_a_non_policy_spec() -> None:
    with pytest.raises(
        TypeError, match="PROMOTION_GRADUATION_REQUIRES_REAL_POLICY_SPEC"
    ):
        build_promotion_graduation_packet(
            _hook(),
            _evidence(),
            "astar-attacker",
            [_match()],  # type: ignore[arg-type]
        )


def test_a_one_shot_generator_of_evidence_still_populates_the_packet() -> None:
    # The adversarial refute pass on this module found that passing a
    # generator (a legal `Iterable[EpisodeEvidence]`, matching the
    # declared parameter type) instead of a list silently built a packet
    # whose `observations`/`falsifiers`/`results` were all empty --
    # `PromotionCourt.evaluate` consumed the generator first, real
    # promotion succeeded, and the evidence-materialising loop then found
    # nothing left, with no exception raised. Real reproduction: the same
    # evidence, as a generator this time.
    match = _match()
    receipts = _evidence()

    packet = build_promotion_graduation_packet(
        _hook(), (r for r in receipts), _policy(), (m for m in [match])
    )

    assert packet.observations, "observations must not be silently empty"
    assert packet.falsifiers, "falsifiers must not be silently empty"
    assert packet.results, "results must not be silently empty"
    assert {e.evidence_id for e in packet.observations + packet.falsifiers} == {
        r.evidence_id for r in receipts
    }
    assert packet.promotion.evidence_ids == tuple(
        sorted(r.evidence_id for r in receipts)
    )
