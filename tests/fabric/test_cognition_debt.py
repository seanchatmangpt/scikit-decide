import pytest

from autofde_lab.fabric.cognition_debt import (
    CognitionEpisode,
    detect_repeated_cognition_debt,
)
from autofde_lab.fabric.selection import DecisionRegime


def ep(regime, tokens, *, verified=True, successful=True, signature="sig"):
    return CognitionEpisode(
        signature_key=signature,
        regime=regime,
        frontier_tokens=tokens,
        verified=verified,
        successful=successful,
    )


def test_repeated_verified_hot_inference_becomes_candidate_debt():
    findings = detect_repeated_cognition_debt(
        [ep(DecisionRegime.HOT, 100), ep(DecisionRegime.HOT, 80)]
    )
    assert len(findings) == 1
    assert findings[0].repeated_episodes == 2
    assert findings[0].frontier_tokens == 180
    assert findings[0].finding == "CANDIDATE:REPEATED_COGNITION_DEBT"


def test_cold_exploration_is_not_cognition_debt():
    assert not detect_repeated_cognition_debt(
        [ep(DecisionRegime.COLD, 100), ep(DecisionRegime.COLD, 100)]
    )


def test_zero_token_hot_path_is_desired_not_debt():
    assert not detect_repeated_cognition_debt(
        [ep(DecisionRegime.HOT, 0), ep(DecisionRegime.HOT, 0)]
    )


def test_unverified_or_failed_hot_runs_do_not_create_compilation_authority():
    assert not detect_repeated_cognition_debt(
        [
            ep(DecisionRegime.HOT, 100, verified=False),
            ep(DecisionRegime.HOT, 100, successful=False),
        ]
    )


def test_signatures_are_never_merged_for_convenience():
    assert not detect_repeated_cognition_debt(
        [
            ep(DecisionRegime.HOT, 100, signature="a"),
            ep(DecisionRegime.HOT, 100, signature="b"),
        ]
    )


def test_threshold_cannot_be_weakened_to_single_observation():
    with pytest.raises(ValueError):
        detect_repeated_cognition_debt([], min_repetitions=1)
