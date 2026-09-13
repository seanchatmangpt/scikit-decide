from pathlib import Path

from autofde_lab.fabric.crown import RequirementStatus, crown_report


def test_every_crown_evidence_path_exists_at_exact_checkout():
    for requirement in crown_report().requirements:
        for evidence in requirement.evidence:
            assert Path(evidence).exists(), (
                f"{requirement.requirement_id} cites missing evidence path {evidence!r}"
            )


def test_every_satisfied_requirement_has_executable_test_evidence():
    for requirement in crown_report().by_status(RequirementStatus.SATISFIED):
        assert any(path.startswith("tests/") for path in requirement.evidence), (
            f"{requirement.requirement_id} is SATISFIED without test evidence"
        )


def test_blocked_requirements_name_the_unobserved_dependency():
    for requirement in crown_report().by_status(RequirementStatus.BLOCKED):
        assert requirement.external_dependency
        assert requirement.external_dependency.strip()
