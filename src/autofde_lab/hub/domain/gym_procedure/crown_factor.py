# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Crown factors that cannot be satisfied from absence, by construction.

Every factor of the Level 4 acceptance equation was a bare ``bool`` (or, worse,
a collection read with ``.get(key, [])``). That representation cannot
distinguish four genuinely different situations:

* the factor was observed and holds,
* the factor was observed and does NOT hold,
* the factor was never observed,
* the factor was refused / unsupported / blocked.

Collapsing those into one boolean is what let the REPLAY factor score as
satisfied in three consecutive frozen-crown attempts without ever running: an
exception produced no mismatch key, a missing key read as an empty collection,
and an empty collection read as "clean". Every one of those is *absence*, and
absence was scored as success.

This module makes that impossible to express. A :class:`CrownFactor` has no
truthy shortcut: :meth:`CrownFactor.is_satisfied` is True **only** for
``OBSERVED_TRUE``, and every other state -- including the ones that look like
"nothing went wrong" -- is not satisfied. Constructing a factor requires
naming its evidence source, so a factor with no evidence cannot be built at
all without saying so.

See ``.claude/rules/absence-is-not-evidence.md`` for the governing law. The
short form: a factor that cannot fail is a factor that is not being checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class FactorState(str, Enum):
    """Six states, not two. `UNKNOWN` is neither success nor failure."""

    OBSERVED_TRUE = "OBSERVED_TRUE"
    OBSERVED_FALSE = "OBSERVED_FALSE"
    UNKNOWN = "UNKNOWN"  # never observed -- NOT a failure, and NOT a pass
    REFUSED = "REFUSED"  # a typed refusal is a real answer
    UNSUPPORTED = "UNSUPPORTED"  # capability/dependency genuinely absent
    BLOCKED = "BLOCKED"  # named external prerequisite prevented observation


#: States that are *not* `OBSERVED_TRUE` but are also not evidence of failure.
#: Kept explicit so a caller that wants "did anything actually get checked?"
#: does not have to re-derive the set and get it subtly wrong.
NON_EVIDENCE_STATES = frozenset(
    {FactorState.UNKNOWN, FactorState.UNSUPPORTED, FactorState.BLOCKED}
)


@dataclass(frozen=True)
class CrownFactor(Generic[T]):
    """One acceptance-equation factor, with its evidence origin attached.

    ``source`` is mandatory and non-empty: a factor that cannot name where its
    value came from is not evidence, and the constructor refuses it rather
    than letting an unattributed value into the conjunction.
    """

    name: str
    state: FactorState
    source: str  # evidence ref: a file path, a receipt id, a command, a digest
    observed: Optional[T] = None
    evidence_ref: Optional[str] = None  # the artifact answering "why is this true?"
    refusal: Optional[str] = None  # typed refusal reason, when state is REFUSED
    unknown_reason: Optional[str] = None  # why it was never observed

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("CROWN_FACTOR_REQUIRES_NAME")
        if not self.source:
            raise ValueError(
                f"CROWN_FACTOR_REQUIRES_EVIDENCE_SOURCE: {self.name!r} has no evidence "
                f"origin; an unattributed value is not evidence"
            )
        if self.state is FactorState.REFUSED and not self.refusal:
            raise ValueError(f"REFUSED_FACTOR_REQUIRES_REASON: {self.name!r}")
        if self.state is FactorState.OBSERVED_TRUE and not self.evidence_ref:
            # "Why is replay_valid true?" must answer with an artifact, not a
            # boolean. A satisfied factor with no evidence_ref is exactly the
            # self-certification this type exists to prevent.
            raise ValueError(
                f"OBSERVED_TRUE_FACTOR_REQUIRES_EVIDENCE_REF: {self.name!r} claims to hold "
                f"but names no artifact establishing it"
            )
        if self.state in NON_EVIDENCE_STATES and not self.unknown_reason:
            raise ValueError(
                f"NON_EVIDENCE_FACTOR_REQUIRES_REASON: {self.name!r} is "
                f"{self.state.value} and must say why it was not observed"
            )

    @property
    def holds(self) -> bool:
        """True ONLY for OBSERVED_TRUE.

        Deliberately no ``__bool__``: ``if factor:`` must never compile to a
        pass. UNKNOWN, REFUSED, UNSUPPORTED, BLOCKED and OBSERVED_FALSE all
        return False -- five distinct ways of not being established, none of
        which may contribute to ALIVE.
        """
        return self.state is FactorState.OBSERVED_TRUE

    def is_satisfied(self) -> bool:
        """Deprecated alias for :attr:`holds`. Kept so existing call sites do
        not silently change meaning mid-refactor."""
        return self.holds

    def is_evidence(self) -> bool:
        """Whether anything was actually checked (true or false), as opposed to
        the factor simply never having been established."""
        return self.state in (FactorState.OBSERVED_TRUE, FactorState.OBSERVED_FALSE, FactorState.REFUSED)

    def describe(self) -> str:
        detail = self.refusal or self.unknown_reason or ""
        suffix = f" ({detail})" if detail else ""
        return f"{self.name}={self.state.value}{suffix} [src={self.source}]"

    # -- constructors, so a caller states which case it is ------------------

    # One named constructor per state. Deliberately NOT one generic
    # constructor taking booleans: every impossible state removed from the
    # type surface is one fewer way to recreate the same bug under a new name.

    @classmethod
    def observed_true(cls, name: str, source: str, evidence_ref: str, value: Any = True) -> "CrownFactor":
        return cls(name=name, state=FactorState.OBSERVED_TRUE, source=source,
                   evidence_ref=evidence_ref, observed=value)

    @classmethod
    def observed_false(cls, name: str, source: str, evidence_ref: str, value: Any = False) -> "CrownFactor":
        return cls(name=name, state=FactorState.OBSERVED_FALSE, source=source,
                   evidence_ref=evidence_ref, observed=value)

    @classmethod
    def unknown(cls, name: str, source: str, reason: str) -> "CrownFactor":
        return cls(name=name, state=FactorState.UNKNOWN, source=source, unknown_reason=reason)

    @classmethod
    def refused(cls, name: str, source: str, refusal: str) -> "CrownFactor":
        return cls(name=name, state=FactorState.REFUSED, source=source, refusal=refusal)

    @classmethod
    def blocked(cls, name: str, source: str, reason: str) -> "CrownFactor":
        return cls(name=name, state=FactorState.BLOCKED, source=source, unknown_reason=reason)

    @classmethod
    def unsupported(cls, name: str, source: str, reason: str) -> "CrownFactor":
        return cls(name=name, state=FactorState.UNSUPPORTED, source=source, unknown_reason=reason)

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "source": self.source,
            "observed": self.observed,
            "evidence_ref": self.evidence_ref,
            "refusal": self.refusal,
            "unknown_reason": self.unknown_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "CrownFactor":
        """Rebuild from a serialized row. Deliberately indexes ``state``,
        ``name`` and ``source`` with ``[]`` and not ``.get(..., default)``: a
        serialized factor missing its state is a corrupt record, not a
        satisfied one."""
        return cls(
            name=payload["name"],
            state=FactorState(payload["state"]),
            source=payload["source"],
            observed=payload["observed"] if "observed" in payload else None,
            evidence_ref=payload["evidence_ref"] if "evidence_ref" in payload else None,
            refusal=payload["refusal"] if "refusal" in payload else None,
            unknown_reason=payload["unknown_reason"] if "unknown_reason" in payload else None,
        )


@dataclass(frozen=True)
class FactorConjunction:
    """The acceptance equation as an explicit, inspectable conjunction.

    Requires every REQUIRED factor to be present *and* `OBSERVED_TRUE`. A
    missing factor is a hard failure naming itself, not a silently satisfied
    one -- which is precisely the defect this type exists to make
    unrepresentable.
    """

    required: tuple[str, ...]
    factors: dict[str, CrownFactor]

    def missing(self) -> list[str]:
        return [n for n in self.required if n not in self.factors]

    def unsatisfied(self) -> list[str]:
        out = list(self.missing())
        out += [n for n in self.required if n in self.factors and not self.factors[n].holds]
        return out

    def never_checked(self) -> list[str]:
        """Required factors that were never actually established either way --
        the ones a boolean scoreboard would have silently counted as passing."""
        return [n for n in self.required if n not in self.factors] + [
            n for n in self.required if n in self.factors and not self.factors[n].is_evidence()
        ]

    def is_alive(self) -> bool:
        """Every required factor present AND holding. No `.get(..., default)`
        anywhere on this path: a factor absent from the record is absent, and
        absence never contributes to ALIVE."""
        return all(n in self.factors and self.factors[n].holds for n in self.required)

    def verdict(self) -> str:
        """`ALIVE` / `UNKNOWN` / `NOT_ALIVE`, per standing-law vocabulary.

        The distinction that mattered for crown run 1: a trial whose factors
        were never checked is `UNKNOWN`, not a 0-scoring failure. Eight trials
        genuinely reached their goal there; what was absent was replay
        evidence, so the honest verdict was `UNKNOWN`, never `NOT_ALIVE`.
        """
        if self.is_alive():
            return "ALIVE"
        if self.never_checked():
            return "UNKNOWN"
        return "NOT_ALIVE"

    def report(self) -> list[str]:
        lines = [f.describe() for f in (self.factors[n] for n in self.required if n in self.factors)]
        lines += [f"{n}=ABSENT (no factor recorded)" for n in self.missing()]
        return lines


#: The Level 4 acceptance equation, as of the corrected conjunction.
LEVEL4_REQUIRED_FACTORS: tuple[str, ...] = (
    "real_goal_attained",
    "independently_verified",
    "ocel_valid",
    "ocel_referential_integrity",
    "replay_ran",
    "replay_valid",
    "zero_replay_mismatches",
)


def factors_from_row(row: dict) -> dict[str, CrownFactor]:
    """Rebuild the acceptance factors from a serialized scoreboard row.

    Two eras of row exist and they must not be scored identically:

    * Rows written **after** the typed acceptance equation landed carry a
      ``crown_factors`` list; those are authoritative and are rebuilt verbatim.
    * Rows written **before** it (crown attempts 1-3, and 4-5) carry only loose
      booleans. Those are reconstructed field by field, and any field the row
      does not contain becomes ``UNKNOWN`` -- never ``OBSERVED_FALSE`` and
      never a pass. Attempts 1-3 have no ``replay_ran``/``replay_valid`` field
      at all, which is exactly why they must re-score ``UNKNOWN``: replay was
      not checked in those runs, so neither a green nor a red verdict is
      honest about them.

    ``zero_replay_mismatches`` is deliberately gated on the row containing
    ``replay_ran``. An empty mismatch tuple from a run where replay never
    executed is absence, not cleanliness -- the original defect.
    """
    if "crown_factors" in row and isinstance(row["crown_factors"], list):
        rebuilt = {}
        for payload in row["crown_factors"]:
            factor = CrownFactor.from_dict(payload)
            rebuilt[factor.name] = factor
        return rebuilt

    src = f"crown_row:seed={row['seed'] if 'seed' in row else 'UNSEEDED'}"
    base_ref = row["evidence_dir"] if "evidence_dir" in row else None
    factors: dict[str, CrownFactor] = {}

    def _ref(key: str) -> str:
        # The evidence reference for a reconstructed factor names the exact
        # recorded field it came from, qualified by the trial's evidence
        # directory when the row carries one. It is weaker than the live
        # report's digest-bearing reference, and says so -- but it is still a
        # real origin, not a claim with nothing behind it. What it can never
        # be is manufactured from a MISSING field: those become UNKNOWN above.
        return f"{base_ref}#row.{key}" if base_ref else f"{src}#row.{key}"

    def _from_bool(factor_name: str, key: str, reason: str) -> None:
        if key not in row:
            factors[factor_name] = CrownFactor.unknown(factor_name, src, reason)
            return
        ctor = CrownFactor.observed_true if row[key] is True else CrownFactor.observed_false
        factors[factor_name] = ctor(factor_name, src, _ref(key), row[key])

    _from_bool("real_goal_attained", "real_goal_attained", "LEGACY_ROW_LACKS_real_goal_attained")
    _from_bool("independently_verified", "independently_verified", "LEGACY_ROW_LACKS_independently_verified")
    _from_bool("ocel_valid", "ocel_valid", "LEGACY_ROW_LACKS_ocel_valid")

    name = "ocel_referential_integrity"
    if "ocel_ref_violations" not in row:
        factors[name] = CrownFactor.unknown(name, src, "LEGACY_ROW_LACKS_ocel_ref_violations")
    else:
        clean = not row["ocel_ref_violations"]
        ctor = CrownFactor.observed_true if clean else CrownFactor.observed_false
        factors[name] = ctor(name, src, _ref("ocel_ref_violations"), list(row["ocel_ref_violations"]))

    _from_bool("replay_ran", "replay_ran", "REPLAY_NOT_CHECKED_IN_THIS_ATTEMPT")
    _from_bool("replay_valid", "replay_valid", "REPLAY_NOT_CHECKED_IN_THIS_ATTEMPT")

    name = "zero_replay_mismatches"
    if "replay_ran" not in row or "replay_mismatches" not in row:
        factors[name] = CrownFactor.unknown(
            name, src, "MISMATCH_TUPLE_WITHOUT_A_REPLAY_THAT_RAN_IS_ABSENCE_NOT_CLEANLINESS"
        )
    elif row["replay_ran"] is not True:
        factors[name] = CrownFactor.unknown(
            name, src, "REPLAY_DID_NOT_RUN_SO_MISMATCH_TUPLE_CARRIES_NO_EVIDENCE"
        )
    else:
        clean = not row["replay_mismatches"]
        ctor = CrownFactor.observed_true if clean else CrownFactor.observed_false
        factors[name] = ctor(name, src, _ref("replay_mismatches"), list(row["replay_mismatches"]))

    return factors


def conjunction_from_row(row: dict) -> FactorConjunction:
    """The single scoring path shared by `TrialReport` and the scoreboard, so
    the report and the runner cannot drift apart."""
    return FactorConjunction(LEVEL4_REQUIRED_FACTORS, factors_from_row(row))
