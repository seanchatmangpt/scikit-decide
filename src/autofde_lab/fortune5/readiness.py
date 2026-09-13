"""Receipt-bound measurement primitives for Fortune-5-class architecture readiness.

This module is read-only.  It verifies supplied evidence and emits a deterministic
measurement witness; it never admits authority, actuates, deploys, or manufactures
customer/organizational acceptance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

REQUIRED_GATES: tuple[str, ...] = (
    "identity",
    "strategy",
    "business",
    "information",
    "application",
    "technology",
    "governance",
    "security",
    "transition",
    "production",
    "actuation",
    "evidence",
)
GATE_DECISIONS = frozenset({"PASS", "FAIL", "UNKNOWN"})
PROFILE_NAME = "TTF5-AR"
PROFILE_VERSION = "1"


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _require_digest(value: str, label: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"REFUSED:INVALID_DIGEST:{label}")
    return value


def reference_profile_digest(gates: Sequence[str] = REQUIRED_GATES) -> str:
    if not gates or len(gates) != len(set(gates)):
        raise ValueError("REFUSED:INVALID_READINESS_PROFILE_GATE_SET")
    return _canonical_digest(
        {"name": PROFILE_NAME, "version": PROFILE_VERSION, "gates": list(gates)}
    )


def subject_identity_digest(
    *,
    benchmark_id: str,
    benchmark_version: str,
    scenario_digest: str,
    admitted_observation_digest: str,
    reference_profile: str,
) -> str:
    if not benchmark_id or not benchmark_version:
        raise ValueError("REFUSED:EMPTY_BENCHMARK_IDENTITY")
    return _canonical_digest(
        {
            "benchmark_id": benchmark_id,
            "benchmark_version": benchmark_version,
            "scenario_digest": _require_digest(scenario_digest, "scenario"),
            "admitted_observation_digest": _require_digest(
                admitted_observation_digest, "admitted_observation"
            ),
            "reference_profile_digest": _require_digest(
                reference_profile, "reference_profile"
            ),
        }
    )


@dataclass(frozen=True, slots=True)
class GateEvidence:
    gate: str
    decision: str
    evidence_digest: str
    subject_digest: str

    def __post_init__(self) -> None:
        if self.gate not in REQUIRED_GATES:
            raise ValueError(f"REFUSED:UNKNOWN_READINESS_GATE:{self.gate}")
        if self.decision not in GATE_DECISIONS:
            raise ValueError(f"REFUSED:UNKNOWN_GATE_DECISION:{self.decision}")
        _require_digest(self.evidence_digest, f"gate_evidence:{self.gate}")
        _require_digest(self.subject_digest, f"gate_subject:{self.gate}")

    def canonical(self) -> dict[str, str]:
        return {
            "gate": self.gate,
            "decision": self.decision,
            "evidence_digest": self.evidence_digest,
            "subject_digest": self.subject_digest,
        }


@dataclass(frozen=True, slots=True)
class ReadinessSubmission:
    benchmark_id: str
    benchmark_version: str
    scenario_digest: str
    admitted_observation_digest: str
    reference_profile_digest: str
    subject_digest: str
    started_at_ns: int
    submitted_at_ns: int
    evidence: tuple[GateEvidence, ...]

    def __post_init__(self) -> None:
        if self.started_at_ns < 0 or self.submitted_at_ns < self.started_at_ns:
            raise ValueError("REFUSED:INVALID_READINESS_TIME_WINDOW")
        _require_digest(self.scenario_digest, "scenario")
        _require_digest(self.admitted_observation_digest, "admitted_observation")
        _require_digest(self.reference_profile_digest, "reference_profile")
        _require_digest(self.subject_digest, "subject")
        expected = subject_identity_digest(
            benchmark_id=self.benchmark_id,
            benchmark_version=self.benchmark_version,
            scenario_digest=self.scenario_digest,
            admitted_observation_digest=self.admitted_observation_digest,
            reference_profile=self.reference_profile_digest,
        )
        if self.subject_digest != expected:
            raise ValueError("REFUSED:READINESS_SUBJECT_IDENTITY_MISMATCH")
        gates = [item.gate for item in self.evidence]
        if len(gates) != len(set(gates)):
            raise ValueError("REFUSED:DUPLICATE_READINESS_GATE_EVIDENCE")
        for item in self.evidence:
            if item.subject_digest != self.subject_digest:
                raise ValueError(f"REFUSED:GATE_EVIDENCE_SUBJECT_MISMATCH:{item.gate}")

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "benchmark_id": self.benchmark_id,
                "benchmark_version": self.benchmark_version,
                "scenario_digest": self.scenario_digest,
                "admitted_observation_digest": self.admitted_observation_digest,
                "reference_profile_digest": self.reference_profile_digest,
                "subject_digest": self.subject_digest,
                "started_at_ns": self.started_at_ns,
                "submitted_at_ns": self.submitted_at_ns,
                "evidence": [item.canonical() for item in self.evidence],
            }
        )


@dataclass(frozen=True, slots=True)
class ReadinessWitness:
    subject_digest: str
    submission_digest: str
    reference_profile_digest: str
    verified_at_ns: int
    technical_standing: str
    gate_decisions: tuple[tuple[str, str], ...]
    missing_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    unknown_gates: tuple[str, ...]
    evidence_coverage_ratio: float
    ttf5_ns: int | None
    witness_digest: str

    @property
    def ready(self) -> bool:
        return self.technical_standing == "ALIVE"

    def canonical_without_digest(self) -> dict[str, object]:
        return {
            "subject_digest": self.subject_digest,
            "submission_digest": self.submission_digest,
            "reference_profile_digest": self.reference_profile_digest,
            "verified_at_ns": self.verified_at_ns,
            "technical_standing": self.technical_standing,
            "gate_decisions": [list(item) for item in self.gate_decisions],
            "missing_gates": list(self.missing_gates),
            "failed_gates": list(self.failed_gates),
            "unknown_gates": list(self.unknown_gates),
            "evidence_coverage_ratio": self.evidence_coverage_ratio,
            "ttf5_ns": self.ttf5_ns,
        }

    def canonical(self) -> dict[str, object]:
        payload = self.canonical_without_digest()
        payload["witness_digest"] = self.witness_digest
        return payload


class F5ReadinessVerifier:
    """Independent, non-authoritative verifier for the TTF5-AR predicate."""

    def __init__(self, gates: Sequence[str] = REQUIRED_GATES) -> None:
        if not gates or len(gates) != len(set(gates)):
            raise ValueError("REFUSED:INVALID_READINESS_PROFILE_GATE_SET")
        unknown = sorted(set(gates) - set(REQUIRED_GATES))
        if unknown:
            raise ValueError(f"REFUSED:UNKNOWN_PROFILE_GATES:{','.join(unknown)}")
        self._gates = tuple(gates)
        self._profile_digest = reference_profile_digest(self._gates)

    @property
    def gates(self) -> tuple[str, ...]:
        return self._gates

    @property
    def profile_digest(self) -> str:
        return self._profile_digest

    def verify(
        self, submission: ReadinessSubmission, *, verified_at_ns: int
    ) -> ReadinessWitness:
        if submission.reference_profile_digest != self.profile_digest:
            raise ValueError("REFUSED:READINESS_PROFILE_IDENTITY_MISMATCH")
        if verified_at_ns < submission.submitted_at_ns:
            raise ValueError("REFUSED:VERIFICATION_PRECEDES_SUBMISSION")

        decisions = {item.gate: item.decision for item in submission.evidence}
        missing = tuple(gate for gate in self.gates if gate not in decisions)
        failed = tuple(gate for gate in self.gates if decisions.get(gate) == "FAIL")
        unknown = tuple(gate for gate in self.gates if decisions.get(gate) == "UNKNOWN")
        passing = tuple(gate for gate in self.gates if decisions.get(gate) == "PASS")
        coverage = (len(self.gates) - len(missing)) / len(self.gates)

        if (
            not missing
            and not failed
            and not unknown
            and len(passing) == len(self.gates)
        ):
            standing = "ALIVE"
            ttf5_ns: int | None = verified_at_ns - submission.started_at_ns
        elif decisions:
            standing = "PARTIAL_ALIVE"
            ttf5_ns = None
        else:
            standing = "UNKNOWN"
            ttf5_ns = None

        gate_decisions = tuple(
            (gate, decisions.get(gate, "MISSING")) for gate in self.gates
        )
        base = {
            "subject_digest": submission.subject_digest,
            "submission_digest": submission.digest,
            "reference_profile_digest": self.profile_digest,
            "verified_at_ns": verified_at_ns,
            "technical_standing": standing,
            "gate_decisions": [list(item) for item in gate_decisions],
            "missing_gates": list(missing),
            "failed_gates": list(failed),
            "unknown_gates": list(unknown),
            "evidence_coverage_ratio": coverage,
            "ttf5_ns": ttf5_ns,
        }
        return ReadinessWitness(
            subject_digest=submission.subject_digest,
            submission_digest=submission.digest,
            reference_profile_digest=self.profile_digest,
            verified_at_ns=verified_at_ns,
            technical_standing=standing,
            gate_decisions=gate_decisions,
            missing_gates=missing,
            failed_gates=failed,
            unknown_gates=unknown,
            evidence_coverage_ratio=coverage,
            ttf5_ns=ttf5_ns,
            witness_digest=_canonical_digest(base),
        )

    def replay(
        self, submission: ReadinessSubmission, witness: ReadinessWitness
    ) -> ReadinessWitness:
        if witness.submission_digest != submission.digest:
            raise ValueError("REFUSED:READINESS_REPLAY_SUBMISSION_MISMATCH")
        replayed = self.verify(submission, verified_at_ns=witness.verified_at_ns)
        if replayed != witness:
            raise ValueError("REFUSED:READINESS_REPLAY_DIVERGENCE")
        return replayed


def build_submission(
    *,
    benchmark_id: str,
    benchmark_version: str,
    scenario_digest: str,
    admitted_observation_digest: str,
    started_at_ns: int,
    submitted_at_ns: int,
    evidence_by_gate: Mapping[str, tuple[str, str]],
    gates: Sequence[str] = REQUIRED_GATES,
) -> ReadinessSubmission:
    """Construct the immutable verifier input from already-observed evidence.

    ``evidence_by_gate`` maps gate -> (decision, evidence_digest).  Construction
    does not synthesize missing evidence or convert absence into PASS.
    """
    profile = reference_profile_digest(gates)
    subject = subject_identity_digest(
        benchmark_id=benchmark_id,
        benchmark_version=benchmark_version,
        scenario_digest=scenario_digest,
        admitted_observation_digest=admitted_observation_digest,
        reference_profile=profile,
    )
    evidence = tuple(
        GateEvidence(
            gate=gate,
            decision=decision,
            evidence_digest=evidence_digest,
            subject_digest=subject,
        )
        for gate, (decision, evidence_digest) in evidence_by_gate.items()
    )
    return ReadinessSubmission(
        benchmark_id=benchmark_id,
        benchmark_version=benchmark_version,
        scenario_digest=scenario_digest,
        admitted_observation_digest=admitted_observation_digest,
        reference_profile_digest=profile,
        subject_digest=subject,
        started_at_ns=started_at_ns,
        submitted_at_ns=submitted_at_ns,
        evidence=evidence,
    )


def evidence_digest(value: object) -> str:
    """Digest observed evidence without assigning it truth or authority."""
    return _canonical_digest(value)


def failure_rate(witnesses: Iterable[ReadinessWitness]) -> float:
    materialized = tuple(witnesses)
    if not materialized:
        raise ValueError("REFUSED:EMPTY_READINESS_ATTEMPT_SET")
    failures = sum(not witness.ready for witness in materialized)
    return failures / len(materialized)
