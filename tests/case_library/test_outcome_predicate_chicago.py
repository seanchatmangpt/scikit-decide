# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for :mod:`autofde_lab.case_library.outcome_predicate`.

Every real combination of ``(structural_passed, oracle.present, oracle.passed)``
is enumerated and named explicitly, not looped anonymously, so each decision
is independently visible: 2 (structural) x 2 (oracle present) x 2 (oracle
passed, only relevant/constructible when present) = 6 constructible cases
(``OracleVerdict`` itself refuses to construct ``present=False`` with a
non-``None`` ``passed``, so that combination is not a 7th case -- it is not a
case at all, and is tested separately as a construction-time refusal).

No mocks: :func:`evaluate_outcome` is a pure function and :class:`Anomaly` /
:class:`OracleVerdict` are plain dataclasses, so every collaborator here is
the real production object -- there is nothing to fake.
"""

from __future__ import annotations

import pytest

from autofde_lab.case_library.outcome_predicate import (
    Anomaly,
    OracleVerdict,
    OutcomeVerdict,
    default_structural_recheck,
    evaluate_outcome,
)


# ---------------------------------------------------------------------------
# The six real, constructible (structural_passed, oracle) combinations.
# ---------------------------------------------------------------------------


def test_structural_passed_oracle_absent_is_confirmed_structural_only() -> None:
    oracle = OracleVerdict(present=False, passed=None)

    verdict, confirmed_via = evaluate_outcome(structural_passed=True, oracle=oracle)

    assert verdict is OutcomeVerdict.CONFIRMED
    assert confirmed_via == "structural_only"


def test_structural_passed_oracle_present_and_passed_is_confirmed_structural_and_oracle() -> None:
    oracle = OracleVerdict(present=True, passed=True)

    verdict, confirmed_via = evaluate_outcome(structural_passed=True, oracle=oracle)

    assert verdict is OutcomeVerdict.CONFIRMED
    assert confirmed_via == "structural_and_oracle"


def test_structural_passed_oracle_present_and_failed_is_disputed() -> None:
    oracle = OracleVerdict(present=True, passed=False)

    verdict, confirmed_via = evaluate_outcome(structural_passed=True, oracle=oracle)

    assert verdict is OutcomeVerdict.DISPUTED
    assert confirmed_via == "n/a"


def test_structural_failed_oracle_absent_is_unconfirmed() -> None:
    oracle = OracleVerdict(present=False, passed=None)

    verdict, confirmed_via = evaluate_outcome(structural_passed=False, oracle=oracle)

    assert verdict is OutcomeVerdict.UNCONFIRMED
    assert confirmed_via == "n/a"


def test_structural_failed_oracle_present_and_passed_is_unconfirmed() -> None:
    # Structural failure dominates regardless of what the oracle says --
    # UNCONFIRMED is defined solely by `not structural_passed`.
    oracle = OracleVerdict(present=True, passed=True)

    verdict, confirmed_via = evaluate_outcome(structural_passed=False, oracle=oracle)

    assert verdict is OutcomeVerdict.UNCONFIRMED
    assert confirmed_via == "n/a"


def test_structural_failed_oracle_present_and_failed_is_unconfirmed() -> None:
    oracle = OracleVerdict(present=True, passed=False)

    verdict, confirmed_via = evaluate_outcome(structural_passed=False, oracle=oracle)

    assert verdict is OutcomeVerdict.UNCONFIRMED
    assert confirmed_via == "n/a"


# ---------------------------------------------------------------------------
# The 7th slot in the raw 2x2x2 grid is not a constructible case.
# ---------------------------------------------------------------------------


def test_oracle_absent_with_non_none_passed_is_refused_at_construction() -> None:
    with pytest.raises(ValueError):
        OracleVerdict(present=False, passed=True)


def test_oracle_present_with_none_passed_is_refused_at_construction() -> None:
    with pytest.raises(ValueError):
        OracleVerdict(present=True, passed=None)


# ---------------------------------------------------------------------------
# default_structural_recheck against a real Anomaly + a real observe() callable.
# ---------------------------------------------------------------------------


def test_default_structural_recheck_passes_when_observed_value_now_matches_expected() -> None:
    anomaly = Anomaly(
        kind="Deployment",
        object_name="checkout",
        namespace="prod",
        field="spec.replicas",
        expected="3",
    )

    def observe() -> str | None:
        return "3"  # a real (in-test) fresh re-observation, now matching

    assert default_structural_recheck(anomaly, observe) is True


def test_default_structural_recheck_fails_when_observed_value_still_diverges() -> None:
    anomaly = Anomaly(
        kind="Deployment",
        object_name="checkout",
        namespace="prod",
        field="spec.replicas",
        expected="3",
    )

    def observe() -> str | None:
        return "0"  # still wrong

    assert default_structural_recheck(anomaly, observe) is False


def test_default_structural_recheck_passes_for_absence_check_when_field_now_gone() -> None:
    anomaly = Anomaly(
        kind="CronJob",
        object_name="nightly-backup",
        namespace="prod",
        field="spec.suspend",
        expected=None,  # presence/absence check
    )

    def observe() -> str | None:
        return None  # field is now absent, as required

    assert default_structural_recheck(anomaly, observe) is True


def test_default_structural_recheck_fails_for_absence_check_when_field_still_present() -> None:
    anomaly = Anomaly(
        kind="CronJob",
        object_name="nightly-backup",
        namespace="prod",
        field="spec.suspend",
        expected=None,
    )

    def observe() -> str | None:
        return "true"  # still present -- fault not gone

    assert default_structural_recheck(anomaly, observe) is False
