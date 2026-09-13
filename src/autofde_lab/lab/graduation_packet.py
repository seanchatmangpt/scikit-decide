# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Graduation packet for a promoted knowledge hook (`V2030.1.1-PRD-ARD.md`
capability 8: "produce graduation packets containing exact observations,
policy identity, benchmark corpus, results, falsifiers, limits, and
required downstream admission").

**Naming-overlap decision, made explicitly rather than silently reusing or
duplicating a bare name.** `autofde_lab.reasoning.lab_standing.GraduationPacket`
already exists (PR #111, capability 9) and already implements capability 8's
field list for one lineage of lab candidate: an `ArchitectureCandidate`
falsified by `autofde_lab.reasoning.laboratory.falsify_candidate`. This
module's `PromotionGraduationPacket` is a **second, genuinely different**
graduation packet, for a **different admitted thing**: a `CandidateHook`
that `autofde_lab.reflex.promotion.PromotionCourt` has cleared for the
powerless BRCE fast path. A falsified architecture candidate and a promoted
deterministic reflex hook are not two representations of one concept --
they come from unrelated producers (`laboratory.falsify_candidate` vs.
`reflex.promotion.PromotionCourt.evaluate`), carry unrelated identity
(`candidate_id`/`world_ref_digest` vs. `hook_id`/`promotion_digest`), and
answer different PRD line items in the same bullet (a falsified DfCM
architecture candidate vs. a compiled-cognition reflex candidate). Giving
this module's type the *same* bare name `GraduationPacket` in a different
module would be exactly the two-classes-one-name defect
`.claude/rules/no-dual-bookkeeping.md` warns against for evidence generally
-- so it is named `PromotionGraduationPacket` instead, module-qualified
(`autofde_lab.lab.graduation_packet.PromotionGraduationPacket`), with this
cross-reference. If a third lab candidate lineage ever needs a graduation
packet, it should get its own distinctly-named type here too, not a third
overload of the bare name.

**What this module adds over `reflex.promotion.PromotionCandidate` alone**:
`PromotionCandidate` already carries `requires_brce`/`direct_do_authority`
(required downstream admission, in that subsystem's vocabulary) and
`envelope` (limits), but discards the `EpisodeEvidence` objects after
counting them (only `evidence_ids` survive) and carries no policy identity
or benchmark corpus at all -- `reflex/promotion.py` and `planner_league/`
share no type and no import. `PromotionGraduationPacket` closes that gap by
joining a `PromotionCandidate` to a real `planner_league.core.PolicySpec`
(the PRD's `Planner x Parameters x Objective x ObservationProjection x
ActionProjection`) and a benchmark corpus of real
`planner_league.core.LeagueMatch.identity_sha256` values, and by retaining
the exact `EpisodeEvidence` objects (not just their ids) as `observations`
and `falsifiers`.

This module selects nothing and actuates nothing. `required_downstream_admission`
is fixed to `"autofde"`; the packet carries no `authority_grant` and no
`standing`/`alive` field (`.claude/rules/no-dual-bookkeeping.md`,
`.claude/rules/absence-is-not-evidence.md`) -- production admission is a
decision the downstream admitter makes over these identities, never a
verdict this repo stores and hands forward.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, fields
from typing import Literal

from autofde_lab.planner_league.core import LeagueMatch, PolicySpec
from autofde_lab.reflex.promotion import (
    CandidateHook,
    EpisodeEvidence,
    EvidenceKind,
    PromotionCandidate,
    PromotionCourt,
    PromotionRefusal,
)

PROMOTION_GRADUATION_SCHEMA = "urn:autofde-lab:promotion-graduation-packet:v1"

REQUIRED_DOWNSTREAM_ADMISSION: Literal["autofde"] = "autofde"

__all__ = [
    "PROMOTION_GRADUATION_SCHEMA",
    "REQUIRED_DOWNSTREAM_ADMISSION",
    "PromotionGraduationPacket",
    "build_promotion_graduation_packet",
]


@dataclass(frozen=True, slots=True)
class PromotionGraduationPacket:
    """Exact evidence handed to `autofde` for a promoted knowledge hook.

    Every field is a reference, a real object, or a real digest -- none is a
    verdict. See the module docstring for why this is a distinct type from
    `autofde_lab.reasoning.lab_standing.GraduationPacket`, not a duplicate of
    it.
    """

    schema: str
    policy: PolicySpec
    benchmark_corpus: tuple[str, ...]
    observations: tuple[EpisodeEvidence, ...]
    falsifiers: tuple[EpisodeEvidence, ...]
    results: tuple[tuple[str, str, bool, bool], ...]
    limits: tuple[str, ...]
    promotion: PromotionCandidate
    required_downstream_admission: Literal["autofde"] = REQUIRED_DOWNSTREAM_ADMISSION

    def __post_init__(self) -> None:
        # Guard the no-dual-bookkeeping contract structurally, so a later
        # edit cannot quietly add a stored verdict to this packet.
        forbidden = {"standing", "alive", "is_alive", "technical_standing"}
        present = forbidden & {f.name for f in fields(self)}
        if present:
            raise ValueError(
                f"PROMOTION_GRADUATION_PACKET_CARRIES_STANDING:{sorted(present)}"
            )
        if not isinstance(self.policy, PolicySpec):
            raise TypeError("PROMOTION_GRADUATION_REQUIRES_REAL_POLICY_SPEC")
        if not isinstance(self.promotion, PromotionCandidate):
            raise TypeError("PROMOTION_GRADUATION_REQUIRES_REAL_PROMOTION_CANDIDATE")
        if not self.benchmark_corpus:
            raise ValueError("PROMOTION_GRADUATION_REQUIRES_NONEMPTY_BENCHMARK_CORPUS")
        if not self.promotion.requires_brce or self.promotion.direct_do_authority:
            raise ValueError("PROMOTION_GRADUATION_REQUIRES_BRCE_ONLY_PROMOTION")
        # `PromotionCourt.evaluate` already refused a real promotion with
        # fewer falsifiers/observations than it requires; a packet for a
        # real promotion must therefore never carry empty evidence tuples.
        # This is the structural backstop for the exhausted-iterable bug the
        # adversarial refute pass found: even if a future caller passes a
        # one-shot iterable again, an empty-but-"successful"-looking packet
        # now fails loudly here instead of shipping silently.
        if not self.observations or not self.falsifiers or not self.results:
            raise ValueError("PROMOTION_GRADUATION_EVIDENCE_TUPLES_MUST_BE_NONEMPTY")
        if self.required_downstream_admission != REQUIRED_DOWNSTREAM_ADMISSION:
            raise ValueError(
                "PROMOTION_GRADUATION_REQUIRES_AUTOFDE_ADMISSION:"
                f"{self.required_downstream_admission}"
            )

    @property
    def packet_digest(self) -> str:
        """Deterministic digest over policy/promotion/corpus identity.

        Computed on demand from the real fields (never stored) so it cannot
        drift from the objects it summarises, and is insensitive to the
        order evidence was supplied in (`observations`/`falsifiers` are
        sorted by `evidence_id` at construction time via the builder below).
        """
        payload = {
            "schema": self.schema,
            "promotion_digest": self.promotion.promotion_digest,
            "policy": {
                "planner_id": self.policy.planner_id,
                "parameters": [list(pair) for pair in self.policy.parameters],
                "objective_id": self.policy.objective_id,
                "observation_projection_id": self.policy.observation_projection_id,
                "action_projection_id": self.policy.action_projection_id,
                "budget_id": self.policy.budget_id,
            },
            "benchmark_corpus": sorted(self.benchmark_corpus),
            "observation_ids": sorted(e.evidence_id for e in self.observations),
            "falsifier_ids": sorted(e.evidence_id for e in self.falsifiers),
            "required_downstream_admission": self.required_downstream_admission,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(canonical).hexdigest()


def build_promotion_graduation_packet(
    hook: CandidateHook,
    evidence: Iterable[EpisodeEvidence],
    policy: PolicySpec,
    matches: Iterable[LeagueMatch],
    *,
    court: PromotionCourt | None = None,
    limits: tuple[str, ...] = (),
) -> PromotionGraduationPacket:
    """Join a real `PromotionCourt.evaluate` result to a real benchmark corpus.

    Nothing here decides whether the hook graduates -- `PromotionCourt.evaluate`
    already made that call, fail-closed, over the real evidence. This
    function only makes the policy identity and benchmark corpus exact
    alongside it, and retains the exact `EpisodeEvidence` objects rather than
    just their ids.
    """
    match_list = list(matches)
    if not match_list:
        raise PromotionRefusal(
            "REFUSED:CORPUS_EMPTY", "at least one league match is required"
        )
    if not isinstance(policy, PolicySpec):
        raise TypeError("PROMOTION_GRADUATION_REQUIRES_REAL_POLICY_SPEC")

    # `evidence` is declared `Iterable`, not `Sequence`, so a caller may
    # legally pass a one-shot generator. Materialise it exactly once, up
    # front, before anything consumes it -- the adversarial refute pass on
    # this module found the earlier two-pass version (once inside
    # `PromotionCourt.evaluate`, once in the loop below) silently building a
    # packet whose `observations`/`falsifiers`/`results` were empty tuples
    # while `promotion.evidence_ids` still showed every real id: no
    # exception, a packet that "looks valid" but records nothing -- exactly
    # the absence-is-not-evidence failure this module's own docstring claims
    # to guard against.
    evidence_list = list(evidence)

    active_court = court or PromotionCourt()
    promotion = active_court.evaluate(hook, evidence_list)

    unique: dict[str, EpisodeEvidence] = {}
    for receipt in evidence_list:
        unique[receipt.evidence_id] = receipt

    observations = tuple(
        sorted(
            (e for e in unique.values() if e.kind is EvidenceKind.POSITIVE),
            key=lambda e: e.evidence_id,
        )
    )
    falsifiers = tuple(
        sorted(
            (e for e in unique.values() if e.kind is EvidenceKind.FALSIFIER),
            key=lambda e: e.evidence_id,
        )
    )
    results = tuple(
        sorted(
            (e.evidence_id, e.standing, e.postcondition_verified, e.replay_verified)
            for e in unique.values()
        )
    )
    benchmark_corpus = tuple(sorted({match.identity_sha256 for match in match_list}))
    declared_limits = tuple(limits) + (
        "LAB_ONLY",
        f"max_age_ticks={hook.envelope.max_age_ticks}",
        f"compensation={hook.envelope.compensation}",
    )

    return PromotionGraduationPacket(
        schema=PROMOTION_GRADUATION_SCHEMA,
        policy=policy,
        benchmark_corpus=benchmark_corpus,
        observations=observations,
        falsifiers=falsifiers,
        results=results,
        limits=declared_limits,
        promotion=promotion,
    )
