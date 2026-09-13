# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Named refusals for the AutoFDE phase graph and its GitHub projection.

Every rejection names a *specific* law, mirroring the discipline of
:mod:`autofde_lab.powl.refusals`. A refusal is never a bare string and never a
generic ``ValueError`` message.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["AutoFdeRefusal", "AutoFdeError"]


class AutoFdeRefusal(StrEnum):
    """Named laws an AutoFDE graph or its projection can violate."""

    # --- source graph shape ---
    UNKNOWN_PHASE = "UNKNOWN_PHASE"
    UNKNOWN_WORK_ITEM = "UNKNOWN_WORK_ITEM"
    DUPLICATE_NODE_ID = "DUPLICATE_NODE_ID"
    CYCLIC_WORK_GRAPH = "CYCLIC_WORK_GRAPH"
    PHASE_ORDER_VIOLATION = "PHASE_ORDER_VIOLATION"
    EMPTY_GRAPH = "EMPTY_GRAPH"

    # --- projection / reconstruction ---
    MISSING_PRECEDENCE_METADATA = "MISSING_PRECEDENCE_METADATA"
    MALFORMED_METADATA_BLOCK = "MALFORMED_METADATA_BLOCK"
    ORPHAN_ISSUE = "ORPHAN_ISSUE"
    ORPHAN_MILESTONE = "ORPHAN_MILESTONE"
    MILESTONE_BINDING_MISMATCH = "MILESTONE_BINDING_MISMATCH"
    LABEL_MISMATCH = "LABEL_MISMATCH"
    NON_INJECTIVE_PROJECTION = "NON_INJECTIVE_PROJECTION"
    DROPPED_WORK_ITEM = "DROPPED_WORK_ITEM"
    ROUND_TRIP_MISMATCH = "ROUND_TRIP_MISMATCH"
    NONDETERMINISTIC_RENDER = "NONDETERMINISTIC_RENDER"
    UNSAFE_HEREDOC_BODY = "UNSAFE_HEREDOC_BODY"


class AutoFdeError(ValueError):
    """Raised for every AutoFDE structural rejection."""

    def __init__(self, refusal: AutoFdeRefusal, detail: str = "") -> None:
        self.refusal: AutoFdeRefusal = refusal
        self.detail: str = detail
        super().__init__(
            f"AutoFDE refused: {refusal.value}" + (f" ({detail})" if detail else "")
        )
