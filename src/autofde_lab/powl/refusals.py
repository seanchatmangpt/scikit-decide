# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""First-class refusal vocabulary for the POWL 2.0 algebra.

Every rejection raised by :mod:`autofde_lab.powl` names a *specific* structural
law. A refusal is a verdict about shape, never a bare string and never a
generic ``InvalidInput``.

Provenance: the first eight members mirror the ``PowlRefusal`` enum in
``~/wasm4pm-compat/src/powl.rs:1116`` (dual MIT/Apache-2.0). Only the type
shape (variant names) is transcribed; no code is copied.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover -- type-checking only, avoids a real circular import
    from autofde_lab.powl.guard_executor import ExecutionTrace

__all__ = ["PowlRefusal", "PowlError"]


class PowlRefusal(StrEnum):
    """Named structural laws a POWL 2.0 shape can violate."""

    # --- mirrored from ~/wasm4pm-compat/src/powl.rs:1116 ---
    CYCLIC_PARTIAL_ORDER = "CYCLIC_PARTIAL_ORDER"
    INVALID_CHOICE = "INVALID_CHOICE"
    INVALID_CHOICE_ARITY = "INVALID_CHOICE_ARITY"
    IRREDUCIBLE_PROJECTION = "IRREDUCIBLE_PROJECTION"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    CHOICE_GRAPH_DISCONNECTED = "CHOICE_GRAPH_DISCONNECTED"

    # --- required by this package ---
    MULTI_BOUNDARY_CHOICE_GRAPH = "MULTI_BOUNDARY_CHOICE_GRAPH"
    DEPTH_EXCEEDED = "DEPTH_EXCEEDED"
    DANGLING_REFERENCE = "DANGLING_REFERENCE"
    NOT_TRANSITIVELY_REDUCED = "NOT_TRANSITIVELY_REDUCED"
    EDGE_TYPE_MISMATCH = "EDGE_TYPE_MISMATCH"
    INVALID_PARTIAL_ORDER_ARITY = "INVALID_PARTIAL_ORDER_ARITY"
    INVALID_FREQUENCY = "INVALID_FREQUENCY"
    PROHIBITED_NODE_KIND = "PROHIBITED_NODE_KIND"
    BOUND_EXHAUSTED = "BOUND_EXHAUSTED"
    AMBIGUOUS_CHOICE_GUARD = "AMBIGUOUS_CHOICE_GUARD"
    NO_GUARD_MATCHED = "NO_GUARD_MATCHED"
    TRANSITION_BUDGET_EXHAUSTED = "TRANSITION_BUDGET_EXHAUSTED"
    ATOM_INVOCATION_FAILED = "ATOM_INVOCATION_FAILED"
    CHECKPOINT_NODE_MISMATCH = "CHECKPOINT_NODE_MISMATCH"


class PowlError(ValueError):
    """Raised for every POWL 2.0 structural rejection.

    Carries the named law (:attr:`refusal`) plus human-readable evidence
    (:attr:`detail`).
    """

    def __init__(self, refusal: PowlRefusal, detail: str = "", *, partial_trace: "ExecutionTrace | None" = None) -> None:
        self.refusal: PowlRefusal = refusal
        self.detail: str = detail
        #: For ATOM_INVOCATION_FAILED only: the real
        #: `~autofde_lab.powl.guard_executor.ExecutionTrace` accumulated up to
        #: (and including) the failing step, so a caller can inspect exactly
        #: what ran before the failure. Typed only under `TYPE_CHECKING` (not
        #: imported at runtime) to avoid a real circular import from this
        #: low-level refusals module into `guard_executor`; the real value is
        #: always an `ExecutionTrace` when set.
        self.partial_trace = partial_trace
        super().__init__(f"POWL refused: {refusal.value}" + (f" ({detail})" if detail else ""))
