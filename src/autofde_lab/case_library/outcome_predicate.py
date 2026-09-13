# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Success predicate for the case library's retain step.

A fault-diagnosis outcome is only eligible for case-library retention (and,
downstream, taxonomy promotion and future detector self-drafting) if a
**structural re-check** confirms the original violation is gone, and, when an
**external oracle** is available, that oracle agrees. Disagreement between the
two is retained as its own artifact -- ``DISPUTED`` -- never coerced into a
plain boolean. This is the same discipline
``.claude/rules/absence-is-not-evidence.md`` requires generally: an unknown or
contested signal must survive as its own typed value, not be squashed into
whichever boolean is convenient for the caller.

``evaluate_outcome`` is the pure decision function; :class:`StructuralRecheck`
and :class:`OracleVerdict` are the two typed inputs it consumes.

Placement note: this lives in ``case_library/`` (not ``powl/``) because its
sole real consumer is the case library's retain step
(``.claude/rules/standing-law.md``-scoped: this module's own standing is
``ALIVE`` for the decision function and the local ``Anomaly`` placeholder,
and ``UNKNOWN`` for its eventual wiring into a generalized structural
scanner, which does not exist in this worktree yet).

The generalized structural scanner's real ``Anomaly`` type is being built by
a parallel workstream and is not importable here. :class:`Anomaly` below is a
minimal, self-contained placeholder matching the field shape agreed for that
type (``kind``, ``object_name``, ``namespace``, ``field``, ``expected``) --
this module does not block on the real type landing, and the placeholder is
named as such so it is not mistaken for the eventual canonical definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Literal, Protocol


@dataclass(frozen=True)
class Anomaly:
    """Placeholder ``Anomaly`` shape, pending the real structural scanner.

    Mirrors the field shape agreed with the (not-yet-built) generalized
    structural scanner: which object kind, which specific object, which
    namespace, which field diverged, and what value was expected (``None``
    when the check is presence/absence rather than a specific expected
    value). Not a port of the eventual real type -- unify against it, not
    against this module, once it lands.
    """

    kind: str
    object_name: str
    namespace: str
    field: str
    expected: str | None = None


class StructuralRecheck(Protocol):
    """Callable protocol: does a fresh re-observation still show the fault?

    Implementations take the original :class:`Anomaly` (identifying exactly
    which structural violation is being re-checked) and a real
    re-observation function -- ``observe() -> str | None``, returning the
    field's *current* value (or ``None`` if the field/object is now absent)
    -- and return ``True`` if the violation is confirmed **gone** (structural
    re-check passed), ``False`` if it is still present.

    This is a protocol, not a concrete implementation: the real
    re-observation function talks to a live cluster/object store, which is
    exactly the kind of collaborator ``.claude/rules/testing-chicago-style.md``
    requires tests to exercise for real rather than fake -- callers own
    providing a real ``observe`` callable (e.g. a real ``kubectl get`` read),
    and this module's own tests exercise the pure decision function
    (:func:`evaluate_outcome`) directly rather than faking that
    infrastructure.
    """

    def __call__(
        self,
        anomaly: Anomaly,
        observe: Callable[[], str | None],
    ) -> bool: ...


def default_structural_recheck(anomaly: Anomaly, observe: Callable[[], str | None]) -> bool:
    """Reference :class:`StructuralRecheck`: fault is gone iff the current
    observed value no longer equals the anomaly's ``expected`` mismatch.

    Concretely: the anomaly recorded a field that diverged from what was
    expected. The structural re-check passes (returns ``True``, meaning the
    fault is confirmed gone) when a fresh ``observe()`` call now returns the
    ``expected`` value -- or, when ``expected`` is ``None`` (a
    presence/absence check rather than a specific-value check), when the
    field is now absent (``observe()`` returns ``None``).
    """
    current = observe()
    if anomaly.expected is None:
        return current is None
    return current == anomaly.expected


@dataclass(frozen=True)
class OracleVerdict:
    """An external oracle's verdict on whether a fix succeeded, if any.

    :param present: whether an external oracle was consulted at all. Some
        fault classes have no independent oracle (no test suite, no health
        endpoint distinct from the structural check itself) -- ``present``
        being ``False`` records that honestly rather than defaulting
        ``passed`` to ``True``.
    :param passed: the oracle's verdict, or ``None`` when ``present=False``.
        Never ``None`` when ``present=True`` -- a present oracle must report
        a real boolean verdict.
    """

    present: bool
    passed: bool | None = None

    def __post_init__(self) -> None:
        if self.present and self.passed is None:
            raise ValueError("OracleVerdict.passed must be bool when present=True")
        if not self.present and self.passed is not None:
            raise ValueError("OracleVerdict.passed must be None when present=False")


class OutcomeVerdict(str, Enum):
    """The three real, distinct outcomes retention can reach.

    ``CONFIRMED`` and ``UNCONFIRMED`` are not the only non-agreement cases:
    ``DISPUTED`` is a third, explicitly distinct situation (structural
    re-check *passed*, but a present oracle disagreed) from ``UNCONFIRMED``
    (the structural re-check itself failed, oracle involvement irrelevant).
    Conflating the two would discard exactly the information that
    distinguishes "the fix visibly didn't take" from "the fix took
    structurally but an independent signal disagrees."
    """

    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
    UNCONFIRMED = "UNCONFIRMED"


ConfirmedVia = Literal["structural_only", "structural_and_oracle", "n/a"]


def evaluate_outcome(
    structural_passed: bool,
    oracle: OracleVerdict,
) -> tuple[OutcomeVerdict, ConfirmedVia]:
    """Pure decision function: real, exhaustive, three-way outcome.

    Exactly:

    - ``CONFIRMED``   = ``structural_passed`` AND (``not oracle.present`` OR ``oracle.passed``)
    - ``DISPUTED``    = ``structural_passed`` AND ``oracle.present`` AND ``oracle.passed is False``
    - ``UNCONFIRMED`` = ``not structural_passed``

    The second element of the returned tuple names *how* a ``CONFIRMED``
    verdict was reached (``"structural_only"`` when no oracle was consulted,
    ``"structural_and_oracle"`` when both agreed), or ``"n/a"`` for
    ``DISPUTED``/``UNCONFIRMED``, where no confirmation was reached.
    """
    if not structural_passed:
        return OutcomeVerdict.UNCONFIRMED, "n/a"

    if not oracle.present:
        return OutcomeVerdict.CONFIRMED, "structural_only"

    if oracle.passed:
        return OutcomeVerdict.CONFIRMED, "structural_and_oracle"

    return OutcomeVerdict.DISPUTED, "n/a"


__all__ = [
    "Anomaly",
    "StructuralRecheck",
    "default_structural_recheck",
    "OracleVerdict",
    "OutcomeVerdict",
    "ConfirmedVia",
    "evaluate_outcome",
]
