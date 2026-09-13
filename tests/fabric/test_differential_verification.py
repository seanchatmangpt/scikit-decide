import pytest

from autofde_lab.fabric.differential_verification import (
    DifferentialStanding,
    VerificationResult,
    corroborate,
)


def result(verifier, *, passed=True, subject="s", post="p"):
    return VerificationResult(verifier, subject, post, passed, f"evidence:{verifier}")


def test_two_independent_agreeing_verifiers_corroborate():
    verdict = corroborate([result("a"), result("b")])
    assert verdict.standing is DifferentialStanding.CORROBORATED


def test_same_verifier_twice_is_not_independence():
    verdict = corroborate([result("a"), result("a")])
    assert verdict.standing is DifferentialStanding.REFUSED_INSUFFICIENT_INDEPENDENCE


def test_subject_identity_must_match():
    verdict = corroborate([result("a", subject="x"), result("b", subject="y")])
    assert verdict.standing is DifferentialStanding.REFUSED_SUBJECT_MISMATCH


def test_postcondition_identity_must_match():
    verdict = corroborate([result("a", post="x"), result("b", post="y")])
    assert verdict.standing is DifferentialStanding.REFUSED_POSTCONDITION_MISMATCH


def test_one_rejection_refuses_corroboration():
    verdict = corroborate([result("a"), result("b", passed=False)])
    assert verdict.standing is DifferentialStanding.REFUSED_DISAGREEMENT


def test_independence_threshold_cannot_be_weakened_below_two():
    with pytest.raises(ValueError):
        corroborate([result("a")], minimum_independent_verifiers=1)
