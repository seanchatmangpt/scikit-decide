# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The acceptance equation is TYPED -- hostile fixtures for that claim.

`.claude/rules/absence-is-not-evidence.md` is repo doctrine. This file is the
part that makes it mechanical: after these tests, encoding absence as success
requires violating the type contract, not merely forgetting a convention.

Every test here is a hostile fixture. Each one constructs the shape of a real
defect that actually occurred in this repo and asserts the type refuses it.
No mocks: `CrownFactor`/`FactorConjunction` are real objects with real
behaviour, and the assertions are on real returned state.
"""

from __future__ import annotations

import pytest

from autofde_lab.hub.domain.gym_procedure.crown_factor import (
    LEVEL4_REQUIRED_FACTORS,
    CrownFactor,
    FactorConjunction,
    FactorState,
)

EV = "receipts.sqlite3#head=abc123"


def _all_true() -> dict[str, CrownFactor]:
    return {
        n: CrownFactor.observed_true(n, source="crown_run.json", evidence_ref=EV)
        for n in LEVEL4_REQUIRED_FACTORS
    }


# ---------------------------------------------------------------------------
# Only OBSERVED_TRUE may contribute to ALIVE
# ---------------------------------------------------------------------------


def test_only_observed_true_holds():
    assert CrownFactor.observed_true("f", "src", EV).holds is True
    assert CrownFactor.observed_false("f", "src", EV).holds is False
    assert CrownFactor.unknown("f", "src", "never ran").holds is False
    assert CrownFactor.refused("f", "src", "LIVE_AUTHORITY_REQUIRED").holds is False
    assert CrownFactor.unsupported("f", "src", "extra absent").holds is False
    assert CrownFactor.blocked("f", "src", "no venv").holds is False


def test_factor_has_no_truthy_shortcut():
    """`if factor:` must not compile to a pass.

    A dataclass without `__bool__` is truthy by default, so a caller writing
    `if factor:` would treat an UNKNOWN factor as satisfied. Assert the
    property is the only route to a verdict.
    """
    unknown = CrownFactor.unknown("replay_valid", "crown_run.json", "replay never ran")
    assert unknown.holds is False
    assert "__bool__" not in type(unknown).__dict__, (
        "CrownFactor must not define __bool__: a custom truthiness would make "
        "`if factor:` a plausible-looking verdict, which is the whole defect"
    )
    # The dangerous idiom, made explicit: truthiness disagrees with the verdict.
    assert bool(unknown) is True and unknown.holds is False


# ---------------------------------------------------------------------------
# Construction refuses unattributed or unexplained factors
# ---------------------------------------------------------------------------


def test_missing_source_refuses_construction():
    with pytest.raises(ValueError, match="CROWN_FACTOR_REQUIRES_EVIDENCE_SOURCE"):
        CrownFactor(name="replay_valid", state=FactorState.OBSERVED_TRUE, source="")


def test_observed_true_without_evidence_ref_refuses_construction():
    """"Why is replay_valid true?" must answer with an artifact, not a bool."""
    with pytest.raises(ValueError, match="OBSERVED_TRUE_FACTOR_REQUIRES_EVIDENCE_REF"):
        CrownFactor(name="replay_valid", state=FactorState.OBSERVED_TRUE, source="ledger")


def test_non_evidence_states_must_say_why():
    for state in (FactorState.UNKNOWN, FactorState.UNSUPPORTED, FactorState.BLOCKED):
        with pytest.raises(ValueError, match="NON_EVIDENCE_FACTOR_REQUIRES_REASON"):
            CrownFactor(name="replay_valid", state=state, source="ledger")


def test_refused_must_carry_a_typed_reason():
    with pytest.raises(ValueError, match="REFUSED_FACTOR_REQUIRES_REASON"):
        CrownFactor(name="replay_valid", state=FactorState.REFUSED, source="ledger")


# ---------------------------------------------------------------------------
# THE hostile fixture: omission is not satisfaction
# ---------------------------------------------------------------------------


def test_factor_omitted_from_record_is_not_satisfied():
    """The exact defect that produced three FALSE_GREEN crown attempts.

    Crown run 1 recorded no replay fields at all. Under a boolean scoreboard
    reading `not row.get("replay_mismatches")`, a missing key was
    indistinguishable from a clean one, and 8 trials scored ALIVE on a factor
    that had never been checked. Here, omission fails and names itself.
    """
    factors = _all_true()
    for absent in ("replay_ran", "replay_valid", "zero_replay_mismatches"):
        del factors[absent]

    conj = FactorConjunction(required=LEVEL4_REQUIRED_FACTORS, factors=factors)
    assert conj.is_alive() is False
    assert set(conj.missing()) == {"replay_ran", "replay_valid", "zero_replay_mismatches"}
    # And the omission is legible in the report rather than silently absent.
    assert any("ABSENT" in line for line in conj.report())


def test_omission_verdict_is_unknown_not_failure():
    """A factor never checked makes the trial UNKNOWN, never NOT_ALIVE.

    This distinction is load-bearing and was got right in the crown-run-1
    correction: 8 trials genuinely reached their real-world goal. What was
    absent was replay evidence. Reporting them as failures would have been as
    wrong as reporting them as passes.
    """
    factors = _all_true()
    del factors["replay_ran"]
    del factors["replay_valid"]
    conj = FactorConjunction(required=LEVEL4_REQUIRED_FACTORS, factors=factors)
    assert conj.verdict() == "UNKNOWN"
    assert conj.never_checked()


def test_observed_failure_verdict_is_not_alive_not_unknown():
    """A checked-and-failed factor is a real negative, distinct from absence."""
    factors = _all_true()
    factors["replay_valid"] = CrownFactor.observed_false(
        "replay_valid", source="replay_ledger", evidence_ref=EV
    )
    conj = FactorConjunction(required=LEVEL4_REQUIRED_FACTORS, factors=factors)
    assert conj.verdict() == "NOT_ALIVE"
    assert conj.never_checked() == []


def test_full_conjunction_alive_only_when_every_factor_observed_true():
    conj = FactorConjunction(required=LEVEL4_REQUIRED_FACTORS, factors=_all_true())
    assert conj.is_alive() is True
    assert conj.verdict() == "ALIVE"
    assert conj.unsatisfied() == []

    # One factor demoted to UNKNOWN collapses the whole conjunction.
    for name in LEVEL4_REQUIRED_FACTORS:
        degraded = _all_true()
        degraded[name] = CrownFactor.unknown(name, "crown_run.json", "not observed")
        c = FactorConjunction(required=LEVEL4_REQUIRED_FACTORS, factors=degraded)
        assert c.is_alive() is False, f"{name} UNKNOWN must break the conjunction"


def test_every_holding_factor_can_answer_why():
    """An ALIVE conjunction must be able to point at an artifact per factor."""
    conj = FactorConjunction(required=LEVEL4_REQUIRED_FACTORS, factors=_all_true())
    assert conj.is_alive()
    for name in LEVEL4_REQUIRED_FACTORS:
        factor = conj.factors[name]
        assert factor.evidence_ref, f"{name} holds but names no evidence artifact"
        assert factor.source
