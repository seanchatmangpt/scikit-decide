"""Dynamic F5Bench mutation and resynchronization metrics.

The benchmark observes and verifies transitions.  It cannot perform the mutation it
measures; world change remains outside AutoFDE Lab's authority boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from .readiness import (
    F5ReadinessVerifier,
    ReadinessSubmission,
    ReadinessWitness,
    _canonical_digest,
    _require_digest,
)


@dataclass(frozen=True, slots=True)
class BenchmarkMutation:
    mutation_kind: str
    pre_subject_digest: str
    post_subject_digest: str
    occurred_at_ns: int
    mutation_digest: str

    def __post_init__(self) -> None:
        if not self.mutation_kind:
            raise ValueError("REFUSED:EMPTY_MUTATION_KIND")
        _require_digest(self.pre_subject_digest, "mutation_pre_subject")
        _require_digest(self.post_subject_digest, "mutation_post_subject")
        _require_digest(self.mutation_digest, "mutation")
        if self.pre_subject_digest == self.post_subject_digest:
            raise ValueError("REFUSED:MUTATION_DID_NOT_CHANGE_SUBJECT")
        if self.occurred_at_ns < 0:
            raise ValueError("REFUSED:INVALID_MUTATION_TIME")

    @classmethod
    def observed(
        cls,
        *,
        mutation_kind: str,
        pre_subject_digest: str,
        post_subject_digest: str,
        occurred_at_ns: int,
        evidence: object,
    ) -> "BenchmarkMutation":
        return cls(
            mutation_kind=mutation_kind,
            pre_subject_digest=pre_subject_digest,
            post_subject_digest=post_subject_digest,
            occurred_at_ns=occurred_at_ns,
            mutation_digest=_canonical_digest(
                {
                    "kind": mutation_kind,
                    "pre_subject_digest": pre_subject_digest,
                    "post_subject_digest": post_subject_digest,
                    "occurred_at_ns": occurred_at_ns,
                    "evidence": evidence,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ResynchronizationWitness:
    mutation_digest: str
    readiness_witness: ReadinessWitness
    tt_delta_ea_ns: int | None
    binary_architecture_synchronization_debt_ns: int | None

    @property
    def resynchronized(self) -> bool:
        return self.readiness_witness.ready


def verify_resynchronization(
    *,
    previous: ReadinessWitness,
    mutation: BenchmarkMutation,
    submission: ReadinessSubmission,
    verifier: F5ReadinessVerifier,
    verified_at_ns: int,
) -> ResynchronizationWitness:
    if not previous.ready:
        raise ValueError("REFUSED:PREVIOUS_ARCHITECTURE_NOT_READY")
    if mutation.pre_subject_digest != previous.subject_digest:
        raise ValueError("REFUSED:MUTATION_PRE_SUBJECT_MISMATCH")
    if mutation.post_subject_digest != submission.subject_digest:
        raise ValueError("REFUSED:MUTATION_POST_SUBJECT_MISMATCH")
    if mutation.occurred_at_ns < previous.verified_at_ns:
        raise ValueError("REFUSED:MUTATION_PRECEDES_PREVIOUS_STANDING")
    if submission.started_at_ns != mutation.occurred_at_ns:
        raise ValueError("REFUSED:RESYNCHRONIZATION_CLOCK_NOT_MUTATION_BOUND")

    witness = verifier.verify(submission, verified_at_ns=verified_at_ns)
    latency = (
        witness.verified_at_ns - mutation.occurred_at_ns if witness.ready else None
    )
    return ResynchronizationWitness(
        mutation_digest=mutation.mutation_digest,
        readiness_witness=witness,
        tt_delta_ea_ns=latency,
        binary_architecture_synchronization_debt_ns=latency,
    )


def architecture_optionality_density(
    *, lawful_verified_alternatives: int, irreversible_decisions: int
) -> float:
    if lawful_verified_alternatives < 0 or irreversible_decisions < 0:
        raise ValueError("REFUSED:NEGATIVE_OPTIONALITY_INPUT")
    return lawful_verified_alternatives / (1 + irreversible_decisions)
