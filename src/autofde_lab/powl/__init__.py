# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""POWL 2.0 type foundation.

Structure only: this package describes the shape of a *candidate* plan. It
never actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

from autofde_lab.powl.algebra import (
    MAX_POWL_DEPTH,
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
    node_depth,
    transitive_closure,
    transitive_reduction,
)
from autofde_lab.powl.bounds import DEFAULT_BOUND, ExecutionBound
from autofde_lab.powl.frequency import (
    ONCE,
    ONE_OR_MORE,
    OPTIONAL,
    ZERO_OR_MORE,
    Frequency,
)
from autofde_lab.powl.identity import (
    OccurrenceKey,
    activity_sha256,
    node_id,
    node_structure,
)
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = [
    "PowlRefusal",
    "PowlError",
    "Frequency",
    "ONCE",
    "OPTIONAL",
    "ONE_OR_MORE",
    "ZERO_OR_MORE",
    "ExecutionBound",
    "DEFAULT_BOUND",
    "NodeId",
    "MAX_POWL_DEPTH",
    "OrderEdge",
    "ChoiceGraphEdge",
    "Start",
    "End",
    "Atom",
    "Silent",
    "PartialOrder",
    "ChoiceGraph",
    "PowlNode",
    "transitive_closure",
    "transitive_reduction",
    "node_depth",
    "activity_sha256",
    "node_id",
    "node_structure",
    "OccurrenceKey",
]
