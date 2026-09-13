# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Content-addressed identity for POWL 2.0 nodes.

Digests are Merkle-style and built over
:func:`autofde_lab.fabric.canonical.canonical_json` + ``sha256``. Two invariants
are load-bearing:

1. Only the transitive **reduction** enters a digest; the closure is a derived
   execution aid and never contributes.
2. Every set is serialized in a sorted canonical order, so Python's
   ``frozenset`` iteration order can never leak into a digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autofde_lab.fabric.canonical import canonical_json
from autofde_lab.fabric.canonical import sha256 as _sha256
from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
    _action_identity,
)
from autofde_lab.powl.frequency import Frequency
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = ["activity_sha256", "node_id", "node_structure", "OccurrenceKey"]


def activity_sha256(atom: Atom) -> str:
    """Content hash of an :class:`~autofde_lab.powl.algebra.Atom`.

    Covers ``{label, action identity, bindings}``.
    """
    if not isinstance(atom, Atom):
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"activity_sha256 expects Atom, got {type(atom).__name__}",
        )
    return _sha256(
        {
            "label": atom.label,
            "action": _action_identity(atom.action),
            "bindings": dict(atom.bindings),
        }
    )


def _freq(f: Frequency) -> dict[str, Any]:
    return {"min": f.min, "max": f.max}


def node_structure(node: PowlNode) -> dict[str, Any]:
    """Canonical, order-independent structural description of ``node``."""
    if isinstance(node, Start):
        return {"kind": "Start"}
    if isinstance(node, End):
        return {"kind": "End"}
    if isinstance(node, Silent):
        return {"kind": "Silent"}
    if isinstance(node, Atom):
        return {"kind": "Atom", "activity": activity_sha256(node)}
    if isinstance(node, PartialOrder):
        return {
            "kind": "PartialOrder",
            "children": [node_id(c) for c in node.children],
            # reduction only, sorted — never the closure, never set order
            "order": sorted([e.src, e.dst] for e in node.order),
            "frequency": _freq(node.frequency),
        }
    if isinstance(node, ChoiceGraph):
        return {
            "kind": "ChoiceGraph",
            "children": [node_id(c) for c in node.children],
            "edges": sorted([e.src, e.dst] for e in node.edges),
            "start": node.start,
            "end": node.end,
            "frequency": _freq(node.frequency),
        }
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def node_id(node: PowlNode) -> str:
    """Recursive Merkle identity of ``node``."""
    return _sha256(canonical_json(node_structure(node)))


@dataclass(frozen=True, slots=True)
class OccurrenceKey:
    """Identity of one occurrence of an activity within a traversal context."""

    activity_sha256: str
    occurrence_index: int
    context_sha256: str
