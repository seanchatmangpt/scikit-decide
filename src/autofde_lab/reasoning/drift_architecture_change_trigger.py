# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real wiring: `ocel.wasm4pm_bridge.detect_drift`'s real `DriftPoint`
output into `laboratory.ArchitectureChangeTrigger`.

Closes a real, previously-named gap
(`docs/2026-08-11-van-der-aalst-audit-gap-report.md`): every real
`ArchitectureChangeTrigger` construction site (before this module,
`tests/reasoning/test_laboratory_chicago.py` only) hand-typed `confidence`
as a literal float -- `detect_drift()`'s real `jaccard_distance`/
`tv_distance` fields (both real, in `[0.0, 1.0]`, proven by
`tests/ocel/test_wasm4pm_bridge.py::test_real_drift_detects_vocabulary_shift`)
had never fed it.

Real, deterministic, never fabricated: with zero real `DriftPoint`s,
`confidence` is honestly `0.0` and the trigger honestly does not
`.fire()` -- mirroring `laboratory.falsify_candidate`'s own "zero receipts
-> honest non-fabricated `UNKNOWN`" law, applied here to a `confidence`
literal instead of a `FalsificationStanding`.
"""

from __future__ import annotations

from autofde_lab.ocel.wasm4pm_bridge import DriftPoint
from autofde_lab.reasoning.laboratory import ArchitectureChangeTrigger

__all__ = ["architecture_change_trigger_from_drift"]


def architecture_change_trigger_from_drift(
    points: tuple[DriftPoint, ...],
    *,
    affected_requirement_refs: tuple[str, ...],
    trigger_policy: str = "drift-max-distance-0.5",
    prior_architecture_ref: str | None = None,
) -> ArchitectureChangeTrigger:
    """Real, deterministic `ArchitectureChangeTrigger` construction from
    real `detect_drift()` output. `confidence` is the real worst-case
    (maximum) real distance across every real point and every real metric
    (`jaccard_distance`, `tv_distance`) -- never averaged or otherwise
    softened, since a single real, sharp vocabulary shift at one point is
    exactly the kind of signal `ArchitectureChangeTrigger.fires`'s
    `confidence >= 0.5` threshold exists to catch."""
    if not points:
        return ArchitectureChangeTrigger(
            evidence_refs=(),
            detected_drift="no real drift points detected",
            affected_requirement_refs=affected_requirement_refs,
            confidence=0.0,
            trigger_policy=trigger_policy,
            prior_architecture_ref=prior_architecture_ref,
        )

    confidence = max(max(p.jaccard_distance, p.tv_distance) for p in points)
    evidence_refs = tuple(
        f"drift:pos={p.position}:method={p.method}:jaccard={p.jaccard_distance:.4f}:tv={p.tv_distance:.4f}"
        for p in points
    )
    return ArchitectureChangeTrigger(
        evidence_refs=evidence_refs,
        detected_drift=f"{len(points)} real drift point(s) detected via wasm4pm mining drift",
        affected_requirement_refs=affected_requirement_refs,
        confidence=confidence,
        trigger_policy=trigger_policy,
        prior_architecture_ref=prior_architecture_ref,
    )
