# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Construct a real PORTFOLIO of alternative mitigation *processes* --
each a real, admitted `autofde_lab.powl.algebra.PartialOrder` of `Atom`s --
instead of `sre_troubleshooting_pipeline.SreTroubleshootingPipeline
.select_mitigation`'s single best free-text `mitigation_intent` collapsed
inside a `dspy.BestOfN`.

Pareto selection over the returned portfolio (by cost, risk, step count,
consequence-class mix, ...) is deliberately a CALLER's job, never this
module's -- this module's only responsibility is constructing and admitting
real candidates, never ranking or collapsing them to one.

This module is additive: it does not modify
`sre_troubleshooting_pipeline.py`, `sre_troubleshooting_signatures.py`, or
`gymact_dspy_react.py`.

The step-line format, honestly documented
-------------------------------------------
`ConstructSreMitigationProcess.process_steps` is real, structured text: one
step per line, each line exactly `"<CONSEQUENCE>: <description>"` where
`<CONSEQUENCE>` is one of `READ`, `DO`, `VERIFY` (uppercase). `_parse_steps`
is a pure, deterministic parser with no LLM involvement -- it either
produces a real, honest `PartialOrder` of `Atom`s in file order (each atom
depends on all previous atoms, so the parsed process is a real total
chain, the natural reading of "one step per line describing a sequence"),
or it raises `MitigationProcessParseError`, a real, typed error. A
malformed line is NEVER silently dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import dspy

from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder, PowlNode
from autofde_lab.powl.refusals import PowlError
from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.sre_mitigation_portfolio_signatures import ConstructSreMitigationProcess

__all__ = [
    "MitigationPortfolioCandidate",
    "MitigationProcessParseError",
    "construct_mitigation_portfolio",
    "parse_process_steps",
]


@dataclass(frozen=True, slots=True)
class MitigationPortfolioCandidate:
    """One real, admitted portfolio candidate, carrying the real DSPy
    prediction's safety-relevant fields alongside the parsed process --
    `construct_mitigation_portfolio` previously discarded
    `safe_to_actuate`/`expected_consequence`/`rollback_plan` and returned
    only the bare `PowlNode`. A caller that would actually actuate a
    candidate against a live environment (see
    `gymact_mitigation_actuation.py`) needs `safe_to_actuate` to decide
    whether actuating it is admissible at all -- dropping it here would
    force that caller to either re-derive it (a second, competing
    computation of the same real signal) or actuate blind."""

    node: PowlNode
    safe_to_actuate: bool
    expected_consequence: str
    rollback_plan: str

logger = logging.getLogger(__name__)

_VALID_CONSEQUENCES: frozenset[str] = frozenset({"READ", "DO", "VERIFY"})


class MitigationProcessParseError(ValueError):
    """Raised when `process_steps` text does not conform to the documented
    `"<CONSEQUENCE>: <description>"` format. Never raised silently -- every
    malformed line surfaces as a real exception, never a dropped step."""


def parse_process_steps(process_steps: str) -> PartialOrder:
    """Parse `process_steps` text (one real step per line, each line
    `"<CONSEQUENCE>: <description>"`) into a real `PartialOrder` of `Atom`s,
    ordered as a total chain matching the given line order (line *i*
    depends on every line before it -- the natural reading of a sequential
    process description).

    Raises `MitigationProcessParseError` if `process_steps` has fewer than
    two non-blank lines, or if any non-blank line does not match the
    documented format, or names a consequence outside READ/DO/VERIFY.
    Never silently drops or skips a malformed line.
    """
    lines = [line.strip() for line in process_steps.splitlines()]
    non_blank = [line for line in lines if line]

    if len(non_blank) < 2:
        raise MitigationProcessParseError(
            f"process_steps must contain at least 2 non-blank step lines, got {len(non_blank)}: "
            f"{process_steps!r}"
        )

    atoms: list[Atom] = []
    for line in non_blank:
        if ":" not in line:
            raise MitigationProcessParseError(
                f"malformed step line (missing '<CONSEQUENCE>: ' prefix): {line!r}"
            )
        tag, _, description = line.partition(":")
        tag = tag.strip()
        description = description.strip()
        if tag not in _VALID_CONSEQUENCES:
            raise MitigationProcessParseError(
                f"malformed step line: consequence tag {tag!r} is not one of "
                f"{sorted(_VALID_CONSEQUENCES)}: {line!r}"
            )
        if not description:
            raise MitigationProcessParseError(f"malformed step line (empty description): {line!r}")
        atoms.append(Atom(label=description, consequence=tag))  # type: ignore[arg-type]

    n = len(atoms)
    # A real total chain: step i must precede every step j > i. Storage is
    # normalized to the transitive reduction by PartialOrder's constructor,
    # so passing the full O(n^2) chain relation here is safe and simple.
    order = frozenset(
        OrderEdge(i, j)  # type: ignore[arg-type]
        for i in range(n)
        for j in range(n)
        if i < j
    )
    return PartialOrder(children=tuple(atoms), order=order)


def construct_mitigation_portfolio(
    *,
    root_cause: str,
    relevant_resource_spec: str,
    capability_catalog: str,
    portfolio_size: int = 3,
    program: dspy.Module | None = None,
) -> list[MitigationPortfolioCandidate]:
    """Construct a real portfolio of up to `portfolio_size` independently
    admitted mitigation-process candidates.

    Makes exactly `portfolio_size` independent real calls into `program`
    (a real `dspy.Predict(ConstructSreMitigationProcess)` by default, or an
    injected real `dspy.Module` for testability -- never a mock/stub
    substituting the interaction itself). Every LM/program call is real;
    no candidate is fabricated or duplicated to pad the portfolio.

    Each call's `process_steps` is parsed via `parse_process_steps` and the
    resulting `PartialOrder` is checked with
    `autofde_lab.powl.validate.validate_model`. A candidate that fails to
    parse or fails admission is logged and skipped -- never crashes the
    whole portfolio, and never appears unvalidated in the returned list.
    A partial (even empty) portfolio is an honest, legitimate result when
    every candidate this round happened to be malformed or inadmissible.

    Returns `MitigationPortfolioCandidate`s (not bare `PowlNode`s) --
    each carries the real prediction's `safe_to_actuate`/
    `expected_consequence`/`rollback_plan` alongside the parsed process, so
    a caller deciding whether to actuate a candidate never has to re-derive
    or discard that real safety signal.
    """
    if portfolio_size < 1:
        raise ValueError(f"portfolio_size must be >= 1, got {portfolio_size}")

    predictor: dspy.Module = program if program is not None else dspy.Predict(ConstructSreMitigationProcess)

    portfolio: list[MitigationPortfolioCandidate] = []
    for i in range(portfolio_size):
        prediction = predictor(
            root_cause=root_cause,
            relevant_resource_spec=relevant_resource_spec,
            capability_catalog=capability_catalog,
        )
        process_steps = getattr(prediction, "process_steps", "")

        try:
            node = parse_process_steps(process_steps)
        except MitigationProcessParseError as exc:
            logger.warning("portfolio candidate %d skipped: parse failure: %s", i, exc)
            continue

        try:
            validate_model(node)
        except PowlError as exc:
            logger.warning("portfolio candidate %d skipped: admission failure: %s", i, exc)
            continue

        portfolio.append(
            MitigationPortfolioCandidate(
                node=node,
                safe_to_actuate=bool(getattr(prediction, "safe_to_actuate", False)),
                expected_consequence=str(getattr(prediction, "expected_consequence", "")),
                rollback_plan=str(getattr(prediction, "rollback_plan", "")),
            )
        )

    return portfolio
