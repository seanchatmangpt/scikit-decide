# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Standing-law exceptions: raise the status, not a generic gap.

A generic `NotImplementedError` asserts that something is missing and says
nothing about *why*, *what would fix it*, or *whether it is even fixable
here*. Those three questions are the entire content of a status claim, and
`.claude/rules/standing-law.md` already has the vocabulary for them. This
module makes that vocabulary raisable.

    NotImplementedError                           # says nothing
    Unsupported("azure-monitor-query extra is not installed")
    Blocked("NO_APPROVED_TEST_SUBSCRIPTION")
    NotRun("apply_smoke.tftest.hcl has no live run block")

The bad half above is written without its `raise` keyword on purpose:
`test_standing_module_raises_no_generic_gap` greps this file's raw source
for the statement, and that check is kept deliberately crude. When it fired
on this docstring, the choice was to make the check smarter or to change the
module. The module changed. A check that gets an exception carved for it the
first time it is inconvenient stops being a check.

Each subclass carries exactly one standing from the law, and each refuses
to be constructed without a reason -- because the law says *name the exact
blocker, not "blocked"*, and an exception that lets you write `Blocked("")`
does not enforce that.

This is not a refusal vocabulary. Those already exist per package --
`PowlRefusal`, `OcelRefusal`, `AgentRefusalCode`, the `AZ-0NN-*` codes --
and they classify *why a lawful operation declined*. This classifies *what
standing the code has right now*, which is a different question and the one
`NotImplementedError` was being used to dodge.
"""

from __future__ import annotations

from typing import ClassVar, Sequence

__all__ = [
    "StandingError",
    "Blocked",
    "Unsupported",
    "Unknown",
    "NotRun",
    "BuildBroken",
    "PartialAlive",
    "NotFound",
]


class StandingError(Exception):
    """Base for every standing-law exception.

    Never raised directly -- a bare `StandingError` would be the same
    contentless assertion as `NotImplementedError`, one rename removed.
    """

    standing: ClassVar[str] = ""

    def __init__(self, reason: str, *, evidence: str = "") -> None:
        if not type(self).standing:
            raise TypeError(
                "StandingError is abstract: raise a subclass that names a "
                "standing, or the exception asserts nothing"
            )
        if not reason or not reason.strip():
            raise ValueError(
                f"{type(self).__name__} requires a reason. "
                "standing-law: name the exact blocker, not 'blocked'"
            )
        self.reason = reason.strip()
        self.evidence = evidence.strip()
        detail = f"{type(self).standing}:{self.reason}"
        if self.evidence:
            detail = f"{detail} -- {self.evidence}"
        super().__init__(detail)

    def __str__(self) -> str:
        return self.args[0]


class Blocked(StandingError):
    """A named external prerequisite prevents lawful progress.

    The reason names the prerequisite, not the feeling. `Blocked("blocked")`
    and `Blocked("cannot proceed")` are both worse than no exception at all,
    because they look like evidence.
    """

    standing = "BLOCKED"


class Unsupported(StandingError):
    """A required capability or dependency is absent.

    Distinct from `Blocked`: this is an environment gate, not incomplete
    work. A missing optional extra is `Unsupported`; an unbuilt feature is
    not.
    """

    standing = "UNSUPPORTED"


class Unknown(StandingError):
    """Observation is insufficient to classify standing.

    Distinct from `Unsupported`: the capability may well exist and work --
    nothing looked. Never a synonym for "probably fine".
    """

    standing = "UNKNOWN"


class NotRun(StandingError):
    """The path exists, is committed, and has never been executed.

    The status a file earns by being authored rather than exercised. It is
    not a failure and it is not progress; conflating it with either is the
    error this names.
    """

    standing = "NOT_RUN"


class BuildBroken(StandingError):
    """The relevant build or test suite fails."""

    standing = "BUILD_BROKEN"


class PartialAlive(StandingError):
    """A bounded working checkpoint exists; the larger claim does not follow.

    Raised where code can serve the narrow case and must refuse the wide one,
    so the boundary is enforced rather than documented.
    """

    standing = "PARTIAL_ALIVE"


class NotFound(Unsupported):
    """An absence claim, carrying the boundary that produced it.

    A bare "absent" is unfalsifiable: it does not say where anyone looked.
    This refuses to be constructed without at least one searched surface and
    one method, so the claim can be checked and, when wrong, corrected.
    """

    standing = "NOT_FOUND"

    def __init__(
        self,
        what: str,
        *,
        searched: Sequence[str],
        methods: Sequence[str],
        revision: str = "",
    ) -> None:
        surfaces = tuple(s for s in searched if s and s.strip())
        ways = tuple(m for m in methods if m and m.strip())
        if not surfaces:
            raise ValueError(
                "NotFound requires at least one searched surface: an absence "
                "claim without its search boundary cannot be checked"
            )
        if not ways:
            raise ValueError(
                "NotFound requires at least one method: 'we looked' is not a "
                "method"
            )
        self.searched = surfaces
        self.methods = ways
        self.revision = revision.strip()
        detail = f"searched={list(surfaces)} methods={list(ways)}"
        if self.revision:
            detail = f"{detail} revision={self.revision}"
        super().__init__(what, evidence=detail)


# ---------------------------------------------------------------------------
# Unlawful standing transitions
# ---------------------------------------------------------------------------
#
# The lawful chain is:
#
#     candidate -> implemented -> executed -> independently verified
#               -> admitted -> ALIVE
#
# A violation is not a coding-style defect. It is a specific transition that
# was skipped, with an artifact promoted into standing it had not earned.
# Each class below names one such skip. Syntactic clues (`NotImplementedError`,
# `MagicMock`, `mock_provider`, `noqa`) can *suggest* one of these, but they
# are not the concept -- the concept is the missing transition.


class TransitionViolation(StandingError):
    """An artifact was promoted past a transition that never occurred."""

    standing = "REFUSED"

    #: The standing the claim is entitled to once the violation is applied.
    lawful_standing: ClassVar[str] = "UNKNOWN"

    def __init__(self, claimed: str, *, detail: str) -> None:
        super().__init__(
            f"{type(self).__name__}: claimed {claimed}, "
            f"lawful standing is {type(self).lawful_standing}",
            evidence=detail,
        )
        self.claimed = claimed
        self.lawful = type(self).lawful_standing


class AuthoredNotExecuted(TransitionViolation):
    """The artifact exists; no execution witness does. `NOT_RUN`, never `PARTIAL_ALIVE`."""

    lawful_standing = "NOT_RUN"


class DeclaredMappingOnly(TransitionViolation):
    """Vocabulary exists; no executable derivation computes it."""

    lawful_standing = "ABSENT"


class MockEvidencePromoted(TransitionViolation):
    """A mocked test was cited as evidence for a real external boundary.

    The mock is not the problem. Citing it past what it can falsify is. A
    mocked provider establishes `CONFIGURATION_VALIDATED` -- variable
    validation, preconditions, graph shape, naming laws, refusal branches --
    and cannot establish that the cloud accepts the schema, that RBAC
    suffices, that a query is valid, or anything about quota or timing.
    """

    lawful_standing = "CONFIGURATION_VALIDATED"


class PredictedStandingCited(TransitionViolation):
    """A forecast was quoted as an observation.

    Expected and observed standing must not share a data structure, and no
    conversion may exist without a witness.
    """

    lawful_standing = "UNKNOWN"


class SelfCertifiedPostcondition(TransitionViolation):
    """The performer declared its own consequence successful.

    `fabric/fde.py` already has the stronger primitive -- `Verifier.independent_of`
    and `REFUSED_SELF_CERTIFICATION`. This names the same fault at claim level.
    """

    lawful_standing = "UNKNOWN"


class AdvisoryAuthorityUsedAsBearer(TransitionViolation):
    """An advisory allow was treated as bearer authority.

    `permits()` is advisory by construction. A refusal is binding; an allow
    means only *no modeled prohibition was found*. It never means authority
    to actuate exists.
    """

    lawful_standing = "UNKNOWN"


class DeclaredDeployedMismatch(TransitionViolation):
    """The declared architecture and the deployed one describe different systems.

    Live instance: the evidence sink is declared as Confidential Ledger
    (`AZ-009-NO_CONFIDENTIAL_LEDGER`) and deployed as a storage account.
    """

    lawful_standing = "ABSENT"


class InertIntegrationSurface(TransitionViolation):
    """The surface is declared but has no executable path from input to effect.

    Live instance: the Logic App is `enabled = false` with no trigger wired,
    so no candidate action can reach it even given a subscription.
    """

    lawful_standing = "ABSENT"


class UndeclaredEvidenceDependency(TransitionViolation):
    """A proof passed only because of an ambient, undeclared provider.

    Live instance: the POWL projection needs BLAKE3 via the `blake3` package
    or a `b3sum` binary. Neither is in any manifest; local runs went green on
    Homebrew's `b3sum` being on PATH.
    """

    lawful_standing = "UNKNOWN"


class FalseGreen(TransitionViolation):
    """A report announced success over a run that did not succeed.

    Non-zero return code, zero collected items, or an absent expected
    witness. This invalidates the whole standing report from that run, not
    just the one row.
    """

    lawful_standing = "BUILD_BROKEN"


class SiblingPromotedToCoreDependency(TransitionViolation):
    """An optional sibling adapter became a prerequisite of the core."""

    lawful_standing = "UNSUPPORTED"


TRANSITION_VIOLATIONS: tuple[type[TransitionViolation], ...] = (
    AuthoredNotExecuted,
    DeclaredMappingOnly,
    MockEvidencePromoted,
    PredictedStandingCited,
    SelfCertifiedPostcondition,
    AdvisoryAuthorityUsedAsBearer,
    DeclaredDeployedMismatch,
    InertIntegrationSurface,
    UndeclaredEvidenceDependency,
    FalseGreen,
    SiblingPromotedToCoreDependency,
)

__all__ += [
    "TransitionViolation",
    "TRANSITION_VIOLATIONS",
    *[c.__name__ for c in TRANSITION_VIOLATIONS],
]
