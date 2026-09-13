"""Fortune-5 enterprise-architecture conformance over admitted technical evidence.

This module is SELECT/CONSTRUCT only. It verifies architecture-package conformance
against an explicit reference profile. It cannot issue customer adoption decisions,
grant organizational authority, actuate a transition plan, or manufacture enterprise
standing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Sequence

from .readiness import ReadinessWitness

MANDATORY = "MANDATORY"
ADVISORY = "ADVISORY"
REQUIREMENT_LEVELS = frozenset({MANDATORY, ADVISORY})
CONFORMANCE_DECISIONS = frozenset({"PASS", "FAIL", "UNKNOWN"})
EXCEPTION_DECISIONS = frozenset({"APPROVED", "REJECTED", "UNKNOWN"})

REQUIRED_REFERENCE_ARTIFACTS: tuple[str, ...] = (
    "capability_model",
    "reference_architecture",
    "standards_catalog",
    "nfr_slo_policy",
    "security_control_profile",
    "data_governance_policy",
    "finops_policy",
    "transition_principles",
    "vendor_exit_policy",
)

REQUIRED_ARCHITECTURE_VIEWS: tuple[str, ...] = (
    "capability_map",
    "business_architecture",
    "information_data_architecture",
    "application_architecture",
    "technology_architecture",
    "security_architecture",
    "nfr_slo_envelope",
    "finops_envelope",
    "governance_decisions",
    "transition_roadmap",
)

PUBLIC_INTERCHANGE_ALIGNMENT: tuple[tuple[str, str], ...] = (
    ("ArchitecturePackage", "prov:Entity"),
    ("ArchitectureEvidence", "prov:Entity"),
    ("ArchitecturePolicy", "odrl:Policy"),
    ("ArchitectureRequirement", "odrl:Constraint"),
    ("ArchitectureConcept", "skos:Concept"),
    ("TransitionActivity", "prov:Activity"),
)


def _digest(value: object) -> str:
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


@dataclass(frozen=True, slots=True)
class ArchitectureRequirement:
    requirement_id: str
    domain: str
    level: str
    description: str
    policy_iri: str

    def __post_init__(self) -> None:
        if not self.requirement_id or not self.domain or not self.description:
            raise ValueError("REFUSED:INCOMPLETE_ARCHITECTURE_REQUIREMENT")
        if self.level not in REQUIREMENT_LEVELS:
            raise ValueError(f"REFUSED:UNKNOWN_REQUIREMENT_LEVEL:{self.level}")
        if ":" not in self.policy_iri:
            raise ValueError("REFUSED:INVALID_POLICY_IRI")

    def canonical(self) -> dict[str, str]:
        return {
            "requirement_id": self.requirement_id,
            "domain": self.domain,
            "level": self.level,
            "description": self.description,
            "policy_iri": self.policy_iri,
        }


FORTUNE5_EA_REQUIREMENTS: tuple[ArchitectureRequirement, ...] = (
    ArchitectureRequirement(
        "CAP-OWN-001",
        "business_capability",
        MANDATORY,
        "Capabilities bind accountable owners, measurable outcomes, and supported value streams.",
        "urn:autofde-lab:fortune5:policy:capability-ownership",
    ),
    ArchitectureRequirement(
        "DATA-GOV-001",
        "information_data",
        MANDATORY,
        "Data products bind classification, residency, lineage, retention, and stewardship.",
        "urn:autofde-lab:fortune5:policy:data-governance",
    ),
    ArchitectureRequirement(
        "APP-LIFE-001",
        "application",
        MANDATORY,
        "Applications bind product ownership, lifecycle state, dependencies, and retirement path.",
        "urn:autofde-lab:fortune5:policy:application-lifecycle",
    ),
    ArchitectureRequirement(
        "TECH-STD-001",
        "technology",
        MANDATORY,
        "Technology choices conform to an identified reference architecture and standards catalog.",
        "urn:autofde-lab:fortune5:policy:technology-standards",
    ),
    ArchitectureRequirement(
        "SEC-ZT-001",
        "security",
        MANDATORY,
        "Trust boundaries, identity, least privilege, secrets, and control obligations are explicit.",
        "urn:autofde-lab:fortune5:policy:security-control",
    ),
    ArchitectureRequirement(
        "RES-RTO-RPO-001",
        "resilience",
        MANDATORY,
        "Availability, RTO, RPO, capacity, degradation, and recovery objectives are evidence-bound.",
        "urn:autofde-lab:fortune5:policy:resilience",
    ),
    ArchitectureRequirement(
        "OBS-SLO-001",
        "operations",
        MANDATORY,
        "Services bind SLOs, telemetry, ownership, alerting, and operating evidence.",
        "urn:autofde-lab:fortune5:policy:observability",
    ),
    ArchitectureRequirement(
        "FIN-UNIT-001",
        "finops",
        MANDATORY,
        "Architecture binds cost envelopes, allocation dimensions, and unit-economic accountability.",
        "urn:autofde-lab:fortune5:policy:finops",
    ),
    ArchitectureRequirement(
        "GOV-ADR-001",
        "governance",
        MANDATORY,
        "Material decisions and deviations bind rationale, authority evidence, expiry, and review.",
        "urn:autofde-lab:fortune5:policy:architecture-governance",
    ),
    ArchitectureRequirement(
        "TRANS-WAVE-001",
        "transition",
        MANDATORY,
        "Transition waves form an acyclic dependency graph with reversible boundaries.",
        "urn:autofde-lab:fortune5:policy:transition",
    ),
    ArchitectureRequirement(
        "VENDOR-EXIT-001",
        "vendor",
        MANDATORY,
        "Material vendor concentration binds portability, replacement, and exit evidence.",
        "urn:autofde-lab:fortune5:policy:vendor-exit",
    ),
    ArchitectureRequirement(
        "SUSTAIN-001",
        "sustainability",
        ADVISORY,
        "Material resource and sustainability tradeoffs are visible in architecture decisions.",
        "urn:autofde-lab:fortune5:policy:sustainability",
    ),
)


@dataclass(frozen=True, slots=True)
class EnterpriseArchitectureProfile:
    profile_id: str
    profile_version: str
    requirements: tuple[ArchitectureRequirement, ...]
    reference_artifacts: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.profile_id or not self.profile_version:
            raise ValueError("REFUSED:EMPTY_ENTERPRISE_ARCHITECTURE_PROFILE_IDENTITY")
        ids = [requirement.requirement_id for requirement in self.requirements]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("REFUSED:INVALID_ARCHITECTURE_REQUIREMENT_SET")
        refs = dict(self.reference_artifacts)
        if len(refs) != len(self.reference_artifacts):
            raise ValueError("REFUSED:DUPLICATE_REFERENCE_ARTIFACT")
        missing = tuple(
            name for name in REQUIRED_REFERENCE_ARTIFACTS if name not in refs
        )
        if missing:
            raise ValueError(
                "REFUSED:REFERENCE_ARTIFACTS_INCOMPLETE:" + ",".join(missing)
            )
        for name, digest in self.reference_artifacts:
            if not name:
                raise ValueError("REFUSED:EMPTY_REFERENCE_ARTIFACT_NAME")
            _require_digest(digest, f"reference_artifact:{name}")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "profile_id": self.profile_id,
                "profile_version": self.profile_version,
                "requirements": [
                    requirement.canonical() for requirement in self.requirements
                ],
                "reference_artifacts": [
                    list(item) for item in sorted(self.reference_artifacts)
                ],
                "public_interchange_alignment": [
                    list(item) for item in PUBLIC_INTERCHANGE_ALIGNMENT
                ],
            }
        )


def build_enterprise_profile(
    *,
    profile_id: str,
    profile_version: str,
    reference_artifact_digests: dict[str, str],
    requirements: Sequence[ArchitectureRequirement] = FORTUNE5_EA_REQUIREMENTS,
) -> EnterpriseArchitectureProfile:
    return EnterpriseArchitectureProfile(
        profile_id=profile_id,
        profile_version=profile_version,
        requirements=tuple(requirements),
        reference_artifacts=tuple(sorted(reference_artifact_digests.items())),
    )


@dataclass(frozen=True, slots=True)
class EnterpriseArchitecturePackage:
    subject_digest: str
    artifacts: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_digest(self.subject_digest, "enterprise_architecture_subject")
        artifacts = dict(self.artifacts)
        if len(artifacts) != len(self.artifacts):
            raise ValueError("REFUSED:DUPLICATE_ARCHITECTURE_VIEW")
        missing = tuple(
            name for name in REQUIRED_ARCHITECTURE_VIEWS if name not in artifacts
        )
        if missing:
            raise ValueError(
                "REFUSED:ARCHITECTURE_PACKAGE_INCOMPLETE:" + ",".join(missing)
            )
        for name, digest in self.artifacts:
            if not name:
                raise ValueError("REFUSED:EMPTY_ARCHITECTURE_VIEW_NAME")
            _require_digest(digest, f"architecture_view:{name}")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "subject_digest": self.subject_digest,
                "artifacts": [list(item) for item in sorted(self.artifacts)],
            }
        )


@dataclass(frozen=True, slots=True)
class TransitionPlan:
    subject_digest: str
    waves: tuple[str, ...]
    dependencies: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_digest(self.subject_digest, "transition_subject")
        if not self.waves or len(self.waves) != len(set(self.waves)):
            raise ValueError("REFUSED:INVALID_TRANSITION_WAVES")
        known = set(self.waves)
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("REFUSED:DUPLICATE_TRANSITION_DEPENDENCY")
        for before, after in self.dependencies:
            if before not in known or after not in known:
                raise ValueError("REFUSED:UNKNOWN_TRANSITION_WAVE")
            if before == after:
                raise ValueError("REFUSED:TRANSITION_SELF_DEPENDENCY")
        self._topological_order()

    def _topological_order(self) -> tuple[str, ...]:
        successors = {wave: set() for wave in self.waves}
        indegree = {wave: 0 for wave in self.waves}
        for before, after in self.dependencies:
            successors[before].add(after)
            indegree[after] += 1
        ready = sorted(wave for wave, degree in indegree.items() if degree == 0)
        ordered: list[str] = []
        while ready:
            wave = ready.pop(0)
            ordered.append(wave)
            for successor in sorted(successors[wave]):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
                    ready.sort()
        if len(ordered) != len(self.waves):
            raise ValueError("REFUSED:CYCLIC_TRANSITION_PLAN")
        return tuple(ordered)

    @property
    def topological_order(self) -> tuple[str, ...]:
        return self._topological_order()

    @property
    def digest(self) -> str:
        return _digest(
            {
                "subject_digest": self.subject_digest,
                "waves": list(self.waves),
                "dependencies": [list(item) for item in sorted(self.dependencies)],
                "topological_order": list(self.topological_order),
            }
        )


@dataclass(frozen=True, slots=True)
class RequirementEvidence:
    requirement_id: str
    decision: str
    evidence_digest: str
    subject_digest: str
    package_digest: str
    profile_digest: str

    def __post_init__(self) -> None:
        if not self.requirement_id:
            raise ValueError("REFUSED:EMPTY_REQUIREMENT_EVIDENCE_ID")
        if self.decision not in CONFORMANCE_DECISIONS:
            raise ValueError(f"REFUSED:UNKNOWN_CONFORMANCE_DECISION:{self.decision}")
        _require_digest(
            self.evidence_digest, f"requirement_evidence:{self.requirement_id}"
        )
        _require_digest(
            self.subject_digest, f"requirement_subject:{self.requirement_id}"
        )
        _require_digest(
            self.package_digest, f"requirement_package:{self.requirement_id}"
        )
        _require_digest(
            self.profile_digest, f"requirement_profile:{self.requirement_id}"
        )

    def canonical(self) -> dict[str, str]:
        return {
            "requirement_id": self.requirement_id,
            "decision": self.decision,
            "evidence_digest": self.evidence_digest,
            "subject_digest": self.subject_digest,
            "package_digest": self.package_digest,
            "profile_digest": self.profile_digest,
        }


@dataclass(frozen=True, slots=True)
class ExceptionEvidence:
    requirement_id: str
    authority_decision: str
    authority_evidence_digest: str
    approver_identity_digest: str
    authority_verifier_iri: str
    subject_digest: str
    package_digest: str
    profile_digest: str
    issued_at_ns: int
    expires_at_ns: int
    compensating_control_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.requirement_id or not self.authority_verifier_iri:
            raise ValueError("REFUSED:INCOMPLETE_EXCEPTION_EVIDENCE")
        if self.authority_decision not in EXCEPTION_DECISIONS:
            raise ValueError(
                f"REFUSED:UNKNOWN_EXCEPTION_DECISION:{self.authority_decision}"
            )
        if self.issued_at_ns < 0 or self.expires_at_ns <= self.issued_at_ns:
            raise ValueError("REFUSED:INVALID_EXCEPTION_TIME_WINDOW")
        _require_digest(
            self.authority_evidence_digest,
            f"exception_authority_evidence:{self.requirement_id}",
        )
        _require_digest(
            self.approver_identity_digest,
            f"exception_approver:{self.requirement_id}",
        )
        _require_digest(self.subject_digest, f"exception_subject:{self.requirement_id}")
        _require_digest(self.package_digest, f"exception_package:{self.requirement_id}")
        _require_digest(self.profile_digest, f"exception_profile:{self.requirement_id}")
        if not self.compensating_control_digests:
            raise ValueError("REFUSED:EXCEPTION_WITHOUT_COMPENSATING_CONTROL")
        for digest in self.compensating_control_digests:
            _require_digest(digest, f"compensating_control:{self.requirement_id}")

    def canonical(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "authority_decision": self.authority_decision,
            "authority_evidence_digest": self.authority_evidence_digest,
            "approver_identity_digest": self.approver_identity_digest,
            "authority_verifier_iri": self.authority_verifier_iri,
            "subject_digest": self.subject_digest,
            "package_digest": self.package_digest,
            "profile_digest": self.profile_digest,
            "issued_at_ns": self.issued_at_ns,
            "expires_at_ns": self.expires_at_ns,
            "compensating_control_digests": list(
                sorted(self.compensating_control_digests)
            ),
        }


@dataclass(frozen=True, slots=True)
class EnterpriseArchitectureSubmission:
    subject_digest: str
    profile_digest: str
    package_digest: str
    transition_plan_digest: str
    readiness_witness_digest: str
    submitted_at_ns: int
    evaluations: tuple[RequirementEvidence, ...]
    exceptions: tuple[ExceptionEvidence, ...] = ()

    def __post_init__(self) -> None:
        if self.submitted_at_ns < 0:
            raise ValueError("REFUSED:INVALID_ENTERPRISE_ARCHITECTURE_SUBMISSION_TIME")
        _require_digest(self.subject_digest, "ea_submission_subject")
        _require_digest(self.profile_digest, "ea_submission_profile")
        _require_digest(self.package_digest, "ea_submission_package")
        _require_digest(self.transition_plan_digest, "ea_submission_transition")
        _require_digest(self.readiness_witness_digest, "ea_submission_readiness")
        evaluation_ids = [item.requirement_id for item in self.evaluations]
        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("REFUSED:DUPLICATE_REQUIREMENT_EVIDENCE")
        exception_ids = [item.requirement_id for item in self.exceptions]
        if len(exception_ids) != len(set(exception_ids)):
            raise ValueError("REFUSED:DUPLICATE_EXCEPTION_EVIDENCE")
        for item in (*self.evaluations, *self.exceptions):
            if item.subject_digest != self.subject_digest:
                raise ValueError(
                    f"REFUSED:EA_EVIDENCE_SUBJECT_MISMATCH:{item.requirement_id}"
                )
            if item.package_digest != self.package_digest:
                raise ValueError(
                    f"REFUSED:EA_EVIDENCE_PACKAGE_MISMATCH:{item.requirement_id}"
                )
            if item.profile_digest != self.profile_digest:
                raise ValueError(
                    f"REFUSED:EA_EVIDENCE_PROFILE_MISMATCH:{item.requirement_id}"
                )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "subject_digest": self.subject_digest,
                "profile_digest": self.profile_digest,
                "package_digest": self.package_digest,
                "transition_plan_digest": self.transition_plan_digest,
                "readiness_witness_digest": self.readiness_witness_digest,
                "submitted_at_ns": self.submitted_at_ns,
                "evaluations": [
                    item.canonical()
                    for item in sorted(
                        self.evaluations, key=lambda evidence: evidence.requirement_id
                    )
                ],
                "exceptions": [
                    item.canonical()
                    for item in sorted(
                        self.exceptions, key=lambda evidence: evidence.requirement_id
                    )
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class EnterpriseArchitectureWitness:
    subject_digest: str
    submission_digest: str
    profile_digest: str
    package_digest: str
    transition_plan_digest: str
    readiness_witness_digest: str
    verified_at_ns: int
    technical_standing: str
    conformance_status: str
    missing_mandatory: tuple[str, ...]
    failed_mandatory: tuple[str, ...]
    unknown_mandatory: tuple[str, ...]
    exceptioned_requirements: tuple[str, ...]
    invalid_exception_requirements: tuple[str, ...]
    advisory_gaps: tuple[str, ...]
    evidence_coverage_ratio: float
    mandatory_clean_conformance_ratio: float
    exception_debt: int
    transition_order: tuple[str, ...]
    witness_digest: str

    @property
    def conformant(self) -> bool:
        return self.technical_standing == "ALIVE"

    def canonical_without_digest(self) -> dict[str, object]:
        return {
            "subject_digest": self.subject_digest,
            "submission_digest": self.submission_digest,
            "profile_digest": self.profile_digest,
            "package_digest": self.package_digest,
            "transition_plan_digest": self.transition_plan_digest,
            "readiness_witness_digest": self.readiness_witness_digest,
            "verified_at_ns": self.verified_at_ns,
            "technical_standing": self.technical_standing,
            "conformance_status": self.conformance_status,
            "missing_mandatory": list(self.missing_mandatory),
            "failed_mandatory": list(self.failed_mandatory),
            "unknown_mandatory": list(self.unknown_mandatory),
            "exceptioned_requirements": list(self.exceptioned_requirements),
            "invalid_exception_requirements": list(self.invalid_exception_requirements),
            "advisory_gaps": list(self.advisory_gaps),
            "evidence_coverage_ratio": self.evidence_coverage_ratio,
            "mandatory_clean_conformance_ratio": (
                self.mandatory_clean_conformance_ratio
            ),
            "exception_debt": self.exception_debt,
            "transition_order": list(self.transition_order),
        }

    def canonical(self) -> dict[str, object]:
        payload = self.canonical_without_digest()
        payload["witness_digest"] = self.witness_digest
        return payload


class EnterpriseArchitectureVerifier:
    """Read-only Fortune-5 enterprise-architecture conformance verifier."""

    def __init__(self, profile: EnterpriseArchitectureProfile) -> None:
        self.profile = profile
        self._requirements = {
            requirement.requirement_id: requirement
            for requirement in profile.requirements
        }

    def verify(
        self,
        submission: EnterpriseArchitectureSubmission,
        *,
        package: EnterpriseArchitecturePackage,
        transition_plan: TransitionPlan,
        readiness_witness: ReadinessWitness,
        verified_at_ns: int,
    ) -> EnterpriseArchitectureWitness:
        if submission.profile_digest != self.profile.digest:
            raise ValueError("REFUSED:EA_PROFILE_IDENTITY_MISMATCH")
        if package.digest != submission.package_digest:
            raise ValueError("REFUSED:EA_PACKAGE_IDENTITY_MISMATCH")
        if transition_plan.digest != submission.transition_plan_digest:
            raise ValueError("REFUSED:EA_TRANSITION_IDENTITY_MISMATCH")
        if package.subject_digest != submission.subject_digest:
            raise ValueError("REFUSED:EA_PACKAGE_SUBJECT_MISMATCH")
        if transition_plan.subject_digest != submission.subject_digest:
            raise ValueError("REFUSED:EA_TRANSITION_SUBJECT_MISMATCH")
        if readiness_witness.witness_digest != submission.readiness_witness_digest:
            raise ValueError("REFUSED:EA_READINESS_WITNESS_IDENTITY_MISMATCH")
        if readiness_witness.subject_digest != submission.subject_digest:
            raise ValueError("REFUSED:EA_READINESS_SUBJECT_MISMATCH")
        if not readiness_witness.ready:
            raise ValueError("REFUSED:EA_REQUIRES_ALIVE_TECHNICAL_READINESS")
        if verified_at_ns < submission.submitted_at_ns:
            raise ValueError("REFUSED:EA_VERIFICATION_PRECEDES_SUBMISSION")

        evaluations = {
            item.requirement_id: item.decision for item in submission.evaluations
        }
        unknown_ids = tuple(
            sorted(
                requirement_id
                for requirement_id in evaluations
                if requirement_id not in self._requirements
            )
        )
        if unknown_ids:
            raise ValueError(
                "REFUSED:UNKNOWN_ARCHITECTURE_REQUIREMENT:" + ",".join(unknown_ids)
            )
        exception_by_requirement = {
            item.requirement_id: item for item in submission.exceptions
        }
        orphan_exception_ids = tuple(
            sorted(
                requirement_id
                for requirement_id in exception_by_requirement
                if evaluations.get(requirement_id) != "FAIL"
            )
        )
        if orphan_exception_ids:
            raise ValueError(
                "REFUSED:EXCEPTION_WITHOUT_FAILED_REQUIREMENT:"
                + ",".join(orphan_exception_ids)
            )
        unknown_exception_ids = tuple(
            sorted(
                requirement_id
                for requirement_id in exception_by_requirement
                if requirement_id not in self._requirements
            )
        )
        if unknown_exception_ids:
            raise ValueError(
                "REFUSED:UNKNOWN_EXCEPTION_REQUIREMENT:"
                + ",".join(unknown_exception_ids)
            )

        mandatory = tuple(
            requirement
            for requirement in self.profile.requirements
            if requirement.level == MANDATORY
        )
        advisory = tuple(
            requirement
            for requirement in self.profile.requirements
            if requirement.level == ADVISORY
        )

        missing = tuple(
            requirement.requirement_id
            for requirement in mandatory
            if requirement.requirement_id not in evaluations
        )
        unknown = tuple(
            requirement.requirement_id
            for requirement in mandatory
            if evaluations.get(requirement.requirement_id) == "UNKNOWN"
        )

        failed: list[str] = []
        exceptioned: list[str] = []
        invalid_exceptions: list[str] = []
        for requirement in mandatory:
            requirement_id = requirement.requirement_id
            if evaluations.get(requirement_id) != "FAIL":
                continue
            exception = exception_by_requirement.get(requirement_id)
            if exception is None:
                failed.append(requirement_id)
                continue
            if (
                exception.authority_decision == "APPROVED"
                and exception.issued_at_ns <= verified_at_ns < exception.expires_at_ns
            ):
                exceptioned.append(requirement_id)
            else:
                failed.append(requirement_id)
                invalid_exceptions.append(requirement_id)

        advisory_gaps = tuple(
            requirement.requirement_id
            for requirement in advisory
            if evaluations.get(requirement.requirement_id) != "PASS"
        )
        supplied_ids = set(evaluations) & set(self._requirements)
        coverage = len(supplied_ids) / len(self._requirements)
        clean_passes = sum(
            evaluations.get(requirement.requirement_id) == "PASS"
            for requirement in mandatory
        )
        clean_ratio = clean_passes / len(mandatory)

        unresolved = bool(missing or unknown or failed)
        if not unresolved:
            standing = "ALIVE"
            status = "CONFORMANT_WITH_EXCEPTIONS" if exceptioned else "CONFORMANT"
        elif evaluations:
            standing = "PARTIAL_ALIVE"
            status = "NONCONFORMANT"
        else:
            standing = "UNKNOWN"
            status = "UNKNOWN"

        base = {
            "subject_digest": submission.subject_digest,
            "submission_digest": submission.digest,
            "profile_digest": self.profile.digest,
            "package_digest": package.digest,
            "transition_plan_digest": transition_plan.digest,
            "readiness_witness_digest": readiness_witness.witness_digest,
            "verified_at_ns": verified_at_ns,
            "technical_standing": standing,
            "conformance_status": status,
            "missing_mandatory": list(missing),
            "failed_mandatory": failed,
            "unknown_mandatory": list(unknown),
            "exceptioned_requirements": exceptioned,
            "invalid_exception_requirements": invalid_exceptions,
            "advisory_gaps": list(advisory_gaps),
            "evidence_coverage_ratio": coverage,
            "mandatory_clean_conformance_ratio": clean_ratio,
            "exception_debt": len(exceptioned),
            "transition_order": list(transition_plan.topological_order),
        }
        return EnterpriseArchitectureWitness(
            subject_digest=submission.subject_digest,
            submission_digest=submission.digest,
            profile_digest=self.profile.digest,
            package_digest=package.digest,
            transition_plan_digest=transition_plan.digest,
            readiness_witness_digest=readiness_witness.witness_digest,
            verified_at_ns=verified_at_ns,
            technical_standing=standing,
            conformance_status=status,
            missing_mandatory=missing,
            failed_mandatory=tuple(failed),
            unknown_mandatory=unknown,
            exceptioned_requirements=tuple(exceptioned),
            invalid_exception_requirements=tuple(invalid_exceptions),
            advisory_gaps=advisory_gaps,
            evidence_coverage_ratio=coverage,
            mandatory_clean_conformance_ratio=clean_ratio,
            exception_debt=len(exceptioned),
            transition_order=transition_plan.topological_order,
            witness_digest=_digest(base),
        )

    def replay(
        self,
        submission: EnterpriseArchitectureSubmission,
        witness: EnterpriseArchitectureWitness,
        *,
        package: EnterpriseArchitecturePackage,
        transition_plan: TransitionPlan,
        readiness_witness: ReadinessWitness,
    ) -> EnterpriseArchitectureWitness:
        if witness.submission_digest != submission.digest:
            raise ValueError("REFUSED:EA_REPLAY_SUBMISSION_MISMATCH")
        replayed = self.verify(
            submission,
            package=package,
            transition_plan=transition_plan,
            readiness_witness=readiness_witness,
            verified_at_ns=witness.verified_at_ns,
        )
        if replayed != witness:
            raise ValueError("REFUSED:EA_REPLAY_DIVERGENCE")
        return replayed


def architecture_artifact_digest(value: object) -> str:
    """Digest an observed architecture artifact without assigning conformance."""
    return _digest(value)
