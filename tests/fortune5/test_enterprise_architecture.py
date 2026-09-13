from __future__ import annotations

import pytest

from autofde_lab.fortune5.enterprise_architecture import (
    REQUIRED_ARCHITECTURE_VIEWS,
    REQUIRED_REFERENCE_ARTIFACTS,
    EnterpriseArchitecturePackage,
    EnterpriseArchitectureSubmission,
    EnterpriseArchitectureVerifier,
    ExceptionEvidence,
    RequirementEvidence,
    TransitionPlan,
    architecture_artifact_digest,
    build_enterprise_profile,
)
from autofde_lab.fortune5.readiness import (
    REQUIRED_GATES,
    F5ReadinessVerifier,
    build_submission,
    evidence_digest,
)

SCENARIO = "1" * 64
OBSERVATION = "2" * 64


def digest(label: str) -> str:
    return architecture_artifact_digest({"label": label})


def readiness_witness(*, observation: str = OBSERVATION):
    evidence = {
        gate: ("PASS", evidence_digest({"gate": gate, "observation": observation}))
        for gate in REQUIRED_GATES
    }
    submission = build_submission(
        benchmark_id="F5Bench-10K",
        benchmark_version="1",
        scenario_digest=SCENARIO,
        admitted_observation_digest=observation,
        started_at_ns=100,
        submitted_at_ns=130,
        evidence_by_gate=evidence,
    )
    witness = F5ReadinessVerifier().verify(submission, verified_at_ns=150)
    assert witness.ready
    return witness


def profile():
    return build_enterprise_profile(
        profile_id="F5-EA",
        profile_version="1",
        reference_artifact_digests={
            name: digest(f"reference:{name}") for name in REQUIRED_REFERENCE_ARTIFACTS
        },
    )


def package(subject: str) -> EnterpriseArchitecturePackage:
    return EnterpriseArchitecturePackage(
        subject_digest=subject,
        artifacts=tuple(
            (name, digest(f"package:{name}")) for name in REQUIRED_ARCHITECTURE_VIEWS
        ),
    )


def transition(subject: str) -> TransitionPlan:
    return TransitionPlan(
        subject_digest=subject,
        waves=("foundation", "platform", "workloads", "optimization"),
        dependencies=(
            ("foundation", "platform"),
            ("platform", "workloads"),
            ("workloads", "optimization"),
        ),
    )


def evaluations(
    *,
    subject: str,
    profile_digest: str,
    package_digest: str,
    overrides: dict[str, str] | None = None,
    omit: set[str] | None = None,
) -> tuple[RequirementEvidence, ...]:
    overrides = overrides or {}
    omit = omit or set()
    result = []
    for requirement in profile().requirements:
        if requirement.requirement_id in omit:
            continue
        decision = overrides.get(requirement.requirement_id, "PASS")
        result.append(
            RequirementEvidence(
                requirement_id=requirement.requirement_id,
                decision=decision,
                evidence_digest=digest(
                    f"evidence:{requirement.requirement_id}:{decision}"
                ),
                subject_digest=subject,
                package_digest=package_digest,
                profile_digest=profile_digest,
            )
        )
    return tuple(result)


def submission(
    *,
    witness,
    architecture_profile,
    architecture_package,
    transition_plan,
    overrides: dict[str, str] | None = None,
    omit: set[str] | None = None,
    exceptions: tuple[ExceptionEvidence, ...] = (),
) -> EnterpriseArchitectureSubmission:
    return EnterpriseArchitectureSubmission(
        subject_digest=witness.subject_digest,
        profile_digest=architecture_profile.digest,
        package_digest=architecture_package.digest,
        transition_plan_digest=transition_plan.digest,
        readiness_witness_digest=witness.witness_digest,
        submitted_at_ns=170,
        evaluations=evaluations(
            subject=witness.subject_digest,
            profile_digest=architecture_profile.digest,
            package_digest=architecture_package.digest,
            overrides=overrides,
            omit=omit,
        ),
        exceptions=exceptions,
    )


def test_full_architecture_package_is_conformant_and_replayable() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
    )
    verifier = EnterpriseArchitectureVerifier(architecture_profile)
    result = verifier.verify(
        candidate,
        package=architecture_package,
        transition_plan=transition_plan,
        readiness_witness=readiness,
        verified_at_ns=200,
    )
    assert result.conformant
    assert result.technical_standing == "ALIVE"
    assert result.conformance_status == "CONFORMANT"
    assert result.evidence_coverage_ratio == 1.0
    assert result.mandatory_clean_conformance_ratio == 1.0
    assert result.transition_order == (
        "foundation",
        "platform",
        "workloads",
        "optimization",
    )
    assert (
        verifier.replay(
            candidate,
            result,
            package=architecture_package,
            transition_plan=transition_plan,
            readiness_witness=readiness,
        )
        == result
    )


def test_mandatory_failure_cannot_be_compensated_by_other_passes() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
        overrides={"SEC-ZT-001": "FAIL"},
    )
    result = EnterpriseArchitectureVerifier(architecture_profile).verify(
        candidate,
        package=architecture_package,
        transition_plan=transition_plan,
        readiness_witness=readiness,
        verified_at_ns=200,
    )
    assert not result.conformant
    assert result.technical_standing == "PARTIAL_ALIVE"
    assert result.failed_mandatory == ("SEC-ZT-001",)


def test_missing_mandatory_evidence_is_not_admitted_as_conformance() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
        omit={"DATA-GOV-001"},
    )
    result = EnterpriseArchitectureVerifier(architecture_profile).verify(
        candidate,
        package=architecture_package,
        transition_plan=transition_plan,
        readiness_witness=readiness,
        verified_at_ns=200,
    )
    assert result.missing_mandatory == ("DATA-GOV-001",)
    assert result.technical_standing == "PARTIAL_ALIVE"
    assert result.evidence_coverage_ratio == 11 / 12


def test_advisory_gap_is_visible_but_nonblocking() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
        overrides={"SUSTAIN-001": "FAIL"},
    )
    result = EnterpriseArchitectureVerifier(architecture_profile).verify(
        candidate,
        package=architecture_package,
        transition_plan=transition_plan,
        readiness_witness=readiness,
        verified_at_ns=200,
    )
    assert result.conformant
    assert result.advisory_gaps == ("SUSTAIN-001",)


def test_external_exception_evidence_is_explicit_debt_not_hidden_pass() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    exception = ExceptionEvidence(
        requirement_id="VENDOR-EXIT-001",
        authority_decision="APPROVED",
        authority_evidence_digest=digest("architecture-review-board:decision"),
        approver_identity_digest=digest("architecture-review-board:identity"),
        authority_verifier_iri="urn:example:external-architecture-authority",
        subject_digest=readiness.subject_digest,
        package_digest=architecture_package.digest,
        profile_digest=architecture_profile.digest,
        issued_at_ns=180,
        expires_at_ns=300,
        compensating_control_digests=(digest("vendor-exit:compensating-control"),),
    )
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
        overrides={"VENDOR-EXIT-001": "FAIL"},
        exceptions=(exception,),
    )
    result = EnterpriseArchitectureVerifier(architecture_profile).verify(
        candidate,
        package=architecture_package,
        transition_plan=transition_plan,
        readiness_witness=readiness,
        verified_at_ns=200,
    )
    assert result.conformant
    assert result.conformance_status == "CONFORMANT_WITH_EXCEPTIONS"
    assert result.exceptioned_requirements == ("VENDOR-EXIT-001",)
    assert result.exception_debt == 1
    assert result.mandatory_clean_conformance_ratio == 10 / 11


def test_expired_exception_cannot_mask_mandatory_failure() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    exception = ExceptionEvidence(
        requirement_id="VENDOR-EXIT-001",
        authority_decision="APPROVED",
        authority_evidence_digest=digest("architecture-review-board:expired"),
        approver_identity_digest=digest("architecture-review-board:identity"),
        authority_verifier_iri="urn:example:external-architecture-authority",
        subject_digest=readiness.subject_digest,
        package_digest=architecture_package.digest,
        profile_digest=architecture_profile.digest,
        issued_at_ns=160,
        expires_at_ns=190,
        compensating_control_digests=(digest("vendor-exit:control"),),
    )
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
        overrides={"VENDOR-EXIT-001": "FAIL"},
        exceptions=(exception,),
    )
    result = EnterpriseArchitectureVerifier(architecture_profile).verify(
        candidate,
        package=architecture_package,
        transition_plan=transition_plan,
        readiness_witness=readiness,
        verified_at_ns=200,
    )
    assert not result.conformant
    assert result.invalid_exception_requirements == ("VENDOR-EXIT-001",)
    assert result.failed_mandatory == ("VENDOR-EXIT-001",)


def test_transition_plan_refuses_cycles() -> None:
    readiness = readiness_witness()
    with pytest.raises(ValueError, match="CYCLIC_TRANSITION_PLAN"):
        TransitionPlan(
            subject_digest=readiness.subject_digest,
            waves=("foundation", "platform", "workloads"),
            dependencies=(
                ("foundation", "platform"),
                ("platform", "workloads"),
                ("workloads", "foundation"),
            ),
        )


def test_architecture_package_refuses_missing_required_view() -> None:
    readiness = readiness_witness()
    with pytest.raises(ValueError, match="ARCHITECTURE_PACKAGE_INCOMPLETE"):
        EnterpriseArchitecturePackage(
            subject_digest=readiness.subject_digest,
            artifacts=tuple(
                (name, digest(name))
                for name in REQUIRED_ARCHITECTURE_VIEWS
                if name != "security_architecture"
            ),
        )


def test_subject_smuggling_is_refused() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    item = RequirementEvidence(
        requirement_id="CAP-OWN-001",
        decision="PASS",
        evidence_digest=digest("capability"),
        subject_digest="f" * 64,
        package_digest=architecture_package.digest,
        profile_digest=architecture_profile.digest,
    )
    with pytest.raises(ValueError, match="EA_EVIDENCE_SUBJECT_MISMATCH"):
        EnterpriseArchitectureSubmission(
            subject_digest=readiness.subject_digest,
            profile_digest=architecture_profile.digest,
            package_digest=architecture_package.digest,
            transition_plan_digest=transition_plan.digest,
            readiness_witness_digest=readiness.witness_digest,
            submitted_at_ns=170,
            evaluations=(item,),
        )


def test_profile_drift_invalidates_submission_identity() -> None:
    readiness = readiness_witness()
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
    )
    references = dict(architecture_profile.reference_artifacts)
    references["standards_catalog"] = digest("reference:standards-catalog:v2")
    changed_profile = build_enterprise_profile(
        profile_id="F5-EA",
        profile_version="2",
        reference_artifact_digests=references,
    )
    with pytest.raises(ValueError, match="EA_PROFILE_IDENTITY_MISMATCH"):
        EnterpriseArchitectureVerifier(changed_profile).verify(
            candidate,
            package=architecture_package,
            transition_plan=transition_plan,
            readiness_witness=readiness,
            verified_at_ns=200,
        )


def test_non_alive_readiness_cannot_be_promoted_to_ea_conformance() -> None:
    evidence = {
        gate: ("PASS", evidence_digest({"gate": gate})) for gate in REQUIRED_GATES
    }
    evidence["production"] = ("FAIL", evidence_digest({"production": "failed"}))
    readiness_submission = build_submission(
        benchmark_id="F5Bench-10K",
        benchmark_version="1",
        scenario_digest=SCENARIO,
        admitted_observation_digest=OBSERVATION,
        started_at_ns=100,
        submitted_at_ns=130,
        evidence_by_gate=evidence,
    )
    readiness = F5ReadinessVerifier().verify(
        readiness_submission,
        verified_at_ns=150,
    )
    architecture_profile = profile()
    architecture_package = package(readiness.subject_digest)
    transition_plan = transition(readiness.subject_digest)
    candidate = submission(
        witness=readiness,
        architecture_profile=architecture_profile,
        architecture_package=architecture_package,
        transition_plan=transition_plan,
    )
    with pytest.raises(ValueError, match="EA_REQUIRES_ALIVE_TECHNICAL_READINESS"):
        EnterpriseArchitectureVerifier(architecture_profile).verify(
            candidate,
            package=architecture_package,
            transition_plan=transition_plan,
            readiness_witness=readiness,
            verified_at_ns=200,
        )
