"""Uniform Anomaly shape for the generalized structural-anomaly scanner.

Design source: docs/autofde-lab-planner-generalized-architecture.md and
docs/c4/autofde_lab_planner_component.mmd. Every ObjectKindAnalyzer, regardless
of K8s kind or relation-class, emits this SAME dataclass -- that uniformity is
the actual generalization this package delivers over the abandoned
src/autofde_lab_planner/{models,engine}.py 14-function enumeration (commit
72c8dfa, left on disk per this repo's fix-forward git discipline, not
extended, not deleted).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RelationClass = Literal[
    "declared_vs_observed",
    "dangling_reference",
    "insufficient_capability",
    "aggregate_threshold",
]


@dataclass(frozen=True, slots=True)
class Anomaly:
    """One structural anomaly found by a scanner analyzer.

    Same shape regardless of which K8s `kind` or `relation_class` produced it.
    No per-kind or per-relation-class subclass exists in this package -- that
    absence is verified by construction: every analyzer in registry.py
    constructs `Anomaly` directly, never a subclass.
    """

    kind: str
    object_name: str
    namespace: str
    relation_class: RelationClass
    field: str
    observed: str
    expected: str | None
    detail: str
