"""Bridge the exhaustive solver coverage court into empirical planner receipts.

``coverage.py`` already owns solver execution and goal-reaching cost
measurement. This module consumes that evidence instead of creating a second
solver runner.
"""

from __future__ import annotations

import re
from typing import Protocol

from autofde_lab.fabric.selection import EvidenceStanding, PlannerReceipt

_COST_RE = re.compile(
    r"(?:^|,\s)cost\s+(?P<cost>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$"
)


class CoverageEvidence(Protocol):
    capability: str
    standing: str
    disposition: str
    execution_evidence: str


def measured_cost(row: CoverageEvidence) -> float | None:
    """Extract only the machine runner's terminal ``cost N`` evidence form."""
    if row.disposition not in {"selected", "tied_optimal", "dominated"}:
        return None
    match = _COST_RE.search(row.execution_evidence.strip())
    if match is None:
        return None
    cost = float(match.group("cost"))
    return cost if cost >= 0 else None


def coverage_row_to_receipt(
    row: CoverageEvidence,
    *,
    signature_key: str,
    objective: str = "minimize_rollout_cost",
    environment: str = "default",
    hardware: str = "default",
) -> PlannerReceipt | None:
    """Convert verified goal-reaching coverage evidence to a selector receipt.

    Coverage cost is a minimization objective, so normalized quality is the
    monotone positive transform ``1 / (1 + cost)``. Failed, unavailable and
    inapplicable rows produce no positive receipt; their exclusion evidence
    remains owned by the exhaustive coverage report.
    """

    cost = measured_cost(row)
    if cost is None:
        return None
    try:
        standing = EvidenceStanding(row.standing)
    except ValueError:
        standing = EvidenceStanding.CANDIDATE
    return PlannerReceipt(
        signature_key=signature_key,
        planner_id=row.capability,
        objective=objective,
        environment=environment,
        hardware=hardware,
        success=True,
        verified=True,
        standing=standing,
        quality=1.0 / (1.0 + cost),
    )
