"""Independent verifier composition for consequential postconditions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class DifferentialStanding(str, Enum):
    CORROBORATED = "CORROBORATED"
    REFUSED_INSUFFICIENT_INDEPENDENCE = "REFUSED:INSUFFICIENT_VERIFIER_INDEPENDENCE"
    REFUSED_SUBJECT_MISMATCH = "REFUSED:VERIFIER_SUBJECT_MISMATCH"
    REFUSED_POSTCONDITION_MISMATCH = "REFUSED:VERIFIER_POSTCONDITION_MISMATCH"
    REFUSED_DISAGREEMENT = "REFUSED:VERIFIER_DISAGREEMENT"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verifier_id: str
    subject_digest: str
    postcondition_digest: str
    passed: bool
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class DifferentialVerification:
    standing: DifferentialStanding
    verifier_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    reason: str


def corroborate(
    results: Iterable[VerificationResult], *, minimum_independent_verifiers: int = 2
) -> DifferentialVerification:
    """Require independent verifier identities over the exact same claim."""
    rows = tuple(results)
    if minimum_independent_verifiers < 2:
        raise ValueError("minimum_independent_verifiers must be >= 2")
    verifier_ids = tuple(sorted({row.verifier_id for row in rows}))
    refs = tuple(sorted({row.evidence_ref for row in rows if row.evidence_ref}))
    if len(verifier_ids) < minimum_independent_verifiers:
        return DifferentialVerification(
            DifferentialStanding.REFUSED_INSUFFICIENT_INDEPENDENCE,
            verifier_ids,
            refs,
            "fewer independent verifier identities than required",
        )
    if len({row.subject_digest for row in rows}) != 1:
        return DifferentialVerification(
            DifferentialStanding.REFUSED_SUBJECT_MISMATCH,
            verifier_ids,
            refs,
            "verifiers did not inspect the same content-bound subject",
        )
    if len({row.postcondition_digest for row in rows}) != 1:
        return DifferentialVerification(
            DifferentialStanding.REFUSED_POSTCONDITION_MISMATCH,
            verifier_ids,
            refs,
            "verifiers did not evaluate the same postcondition identity",
        )
    if not all(row.passed for row in rows):
        return DifferentialVerification(
            DifferentialStanding.REFUSED_DISAGREEMENT,
            verifier_ids,
            refs,
            "at least one independent verifier rejected the postcondition",
        )
    return DifferentialVerification(
        DifferentialStanding.CORROBORATED,
        verifier_ids,
        refs,
        "independent verifiers agree on the exact subject and postcondition",
    )
