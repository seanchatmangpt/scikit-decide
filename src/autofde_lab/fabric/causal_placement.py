"""Evidence-bounded placement selection for manufactured controllers.

Placement optimizes measured/declared causal diameter only after authority and
safety admission. A nearby controller never outranks an unauthorized one by
performance alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autofde_lab.fabric.metrics import CausalLatency


class PlacementStanding(str, Enum):
    SELECTED = "SELECTED"
    TIED = "TIED"
    REFUSED_NO_ADMISSIBLE_PLACEMENT = "REFUSED:NO_ADMISSIBLE_PLACEMENT"


@dataclass(frozen=True, slots=True)
class ControllerPlacement:
    placement_id: str
    authority_admitted: bool
    safety_admitted: bool
    latency: CausalLatency
    model_required: bool = False
    evidence_ref: str = ""

    @property
    def causal_diameter_s(self) -> float:
        return self.latency.causal_diameter_s


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    standing: PlacementStanding
    selected: tuple[str, ...]
    causal_diameter_s: float | None
    reason: str


def select_causal_placement(
    candidates: tuple[ControllerPlacement, ...] | list[ControllerPlacement],
) -> PlacementDecision:
    admitted = tuple(
        c for c in candidates if c.authority_admitted and c.safety_admitted
    )
    if not admitted:
        return PlacementDecision(
            PlacementStanding.REFUSED_NO_ADMISSIBLE_PLACEMENT,
            (),
            None,
            "no candidate has both admitted authority and admitted safety",
        )
    best = min(c.causal_diameter_s for c in admitted)
    selected = tuple(
        sorted(c.placement_id for c in admitted if c.causal_diameter_s == best)
    )
    return PlacementDecision(
        PlacementStanding.SELECTED if len(selected) == 1 else PlacementStanding.TIED,
        selected,
        best,
        (
            "minimum admitted causal diameter"
            if len(selected) == 1
            else "multiple admitted placements share the minimum causal diameter"
        ),
    )
