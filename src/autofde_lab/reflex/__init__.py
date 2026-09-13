"""Reflex discovery and promotion experiments.

This package is EXPLORE-only. It manufactures promotion candidates and powerless BRCE
requests; it does not grant authority or actuate consequences.
"""

from .promotion import (
    CONSEQUENCE_IR_PACK,
    BrceRequest,
    CandidateHook,
    EpisodeEvidence,
    EvidenceKind,
    HookClass,
    HookEnvelope,
    Observation,
    PromotionCandidate,
    PromotionCourt,
    PromotionRefusal,
    RouteDecision,
    RouteResult,
    cognition_elimination_rate,
    implementation_digest,
    route_promoted_hook,
)

__all__ = [
    "BrceRequest",
    "CandidateHook",
    "CONSEQUENCE_IR_PACK",
    "cognition_elimination_rate",
    "EpisodeEvidence",
    "EvidenceKind",
    "HookClass",
    "HookEnvelope",
    "implementation_digest",
    "Observation",
    "PromotionCandidate",
    "PromotionCourt",
    "PromotionRefusal",
    "RouteDecision",
    "RouteResult",
    "route_promoted_hook",
]
