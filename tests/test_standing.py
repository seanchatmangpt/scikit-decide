# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Standing-law exceptions carry a status; a generic gap carries nothing.

Compressed per the ERRC discipline: each test loops its whole table and
asserts the accumulated failure list is empty, so one red item names every
offender rather than reporting the first and stopping.
"""

from __future__ import annotations

import pytest

from autofde_lab.standing import (
    Blocked,
    BuildBroken,
    NotFound,
    NotRun,
    PartialAlive,
    StandingError,
    Unknown,
    Unsupported,
)

# (class, the standing token it must emit)
STANDINGS = [
    (Blocked, "BLOCKED"),
    (Unsupported, "UNSUPPORTED"),
    (Unknown, "UNKNOWN"),
    (NotRun, "NOT_RUN"),
    (BuildBroken, "BUILD_BROKEN"),
    (PartialAlive, "PARTIAL_ALIVE"),
]


def test_every_subclass_emits_its_own_standing_token():
    assert len(STANDINGS) == 6, "anti-vacuity: the table must not shrink silently"
    bad = []
    for cls, token in STANDINGS:
        exc = cls("a named reason")
        if cls.standing != token:
            bad.append(f"{cls.__name__}.standing == {cls.standing!r}, want {token!r}")
        if not str(exc).startswith(f"{token}:"):
            bad.append(f"{cls.__name__} renders {str(exc)!r}, want prefix {token!r}")
        if not isinstance(exc, StandingError):
            bad.append(f"{cls.__name__} is not a StandingError")
    assert not bad, bad


def test_a_reasonless_standing_claim_is_refused():
    """standing-law: name the exact blocker, not 'blocked'."""
    bad = []
    for cls, _ in STANDINGS:
        for empty in ("", "   ", "\n\t"):
            try:
                cls(empty)
            except ValueError:
                continue
            bad.append(f"{cls.__name__} accepted reason={empty!r}")
    assert not bad, bad


def test_the_abstract_base_cannot_be_raised():
    """A bare StandingError would be NotImplementedError, one rename removed."""
    with pytest.raises(TypeError):
        StandingError("anything")


def test_evidence_is_appended_when_given_and_absent_when_not():
    assert str(Blocked("X")) == "BLOCKED:X"
    assert str(Blocked("X", evidence="ran cmd")) == "BLOCKED:X -- ran cmd"


def test_an_absence_claim_must_carry_its_search_boundary():
    """A bare 'absent' is unfalsifiable: it never says where anyone looked."""
    found = NotFound(
        "azurerm_sentinel_*",
        searched=["~/**/*.tf"],
        methods=["grep"],
        revision="a319ad1",
    )
    rendered = str(found)
    bad = [
        part
        for part in ("NOT_FOUND:", "azurerm_sentinel_*", "searched=", "methods=", "a319ad1")
        if part not in rendered
    ]
    assert not bad, f"missing from rendering: {bad} -- got {rendered!r}"
    assert isinstance(found, Unsupported), "an absence is an environment gate"

    refused = []
    for label, kwargs in [
        ("no surfaces", {"searched": [], "methods": ["grep"]}),
        ("blank surfaces", {"searched": ["", "  "], "methods": ["grep"]}),
        ("no methods", {"searched": ["a"], "methods": []}),
        ("blank methods", {"searched": ["a"], "methods": ["  "]}),
    ]:
        try:
            NotFound("x", **kwargs)
        except ValueError:
            continue
        refused.append(label)
    assert not refused, f"NotFound accepted an uncheckable claim: {refused}"


def test_standing_module_raises_no_generic_gap():
    """The replacement for NotImplementedError must not itself use one."""
    import pathlib

    import autofde_lab.standing as mod

    src = pathlib.Path(mod.__file__).read_text()
    assert "class Blocked" in src, "anti-vacuity: read the wrong file"
    offenders = [
        f"line {i}"
        for i, line in enumerate(src.splitlines(), start=1)
        if "raise NotImplementedError" in line
    ]
    assert not offenders, offenders
