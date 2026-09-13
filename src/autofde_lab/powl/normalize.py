# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Canonical form and structural digest for POWL 2.0 models.

What this module actually achieves
----------------------------------
:func:`canonical_form` rewrites a model into a single representative of its
structural equivalence class, and :func:`model_digest` takes a Merkle digest
over that *structure* — never over a serialization string, never over a
``repr``, never over set iteration order. Two models that differ only in how
their edge relation was written down (closure vs. reduction vs. anything
between), or in the tuple order of the children of an unconstrained partial
order, digest identically.

Honest scope — a named blocker, not an achieved property
--------------------------------------------------------
This makes **our** model digest-stable. It does **not** establish

    ``model_digest(autofde_lab) == digest(mfw) == digest(bcinr)``

for the same conceptual plan. Cross-repository digest agreement needs a single
shared normalizer — the same canonical child-ordering rule, the same edge
storage law, the same frequency encoding, the same hash input framing — and no
repository in the portfolio has one. Recorded as:

    ``BLOCKED:NO_SHARED_CROSS_REPO_NORMALIZER``

Anyone tempted to read a matching digest across repositories as agreement
should first check that the other side normalizes children the way
:func:`canonical_form` does; at the time of writing, none does, and a
coincidental match would be evidence of nothing.

What "canonical" means precisely here
-------------------------------------
* Every :class:`~autofde_lab.powl.algebra.PartialOrder` stores the transitive
  **reduction** — already guaranteed by its constructor, re-applied here so a
  model rebuilt via ``object.__setattr__`` is repaired rather than trusted.
* A partial order's children are sorted by their own recursive
  :func:`~autofde_lab.powl.identity.node_id`, and the edge relation is remapped
  through that permutation. Index is pure addressing in this algebra, so the
  remap is an isomorphism and preserves the order relation exactly. Ties (two
  structurally identical children) are broken by original position, so the rule
  is deterministic but is a canonical form only *up to* that tie-break.
* A :class:`~autofde_lab.powl.algebra.ChoiceGraph`'s children are **not**
  reordered. Its ``start`` and ``end`` are index-valued parts of the model's
  meaning, and the boundary law constrains which index may hold them, so the
  structure does not permit a free reordering. Only its children are
  canonicalized in place.
* Frequencies are carried through unchanged; they are already value objects.

Nothing here actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
    transitive_reduction,
)
from autofde_lab.powl.identity import node_id
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = ["canonical_form", "model_digest", "CROSS_REPO_DIGEST_BLOCKER"]

#: Named blocker for cross-repository digest agreement. See the module
#: docstring: this package's normalizer is local, and no shared normalizer
#: exists in the portfolio.
CROSS_REPO_DIGEST_BLOCKER = "BLOCKED:NO_SHARED_CROSS_REPO_NORMALIZER"


def canonical_form(node: PowlNode) -> PowlNode:
    """Return the canonical representative of ``node``'s structure.

    Idempotent: ``canonical_form(canonical_form(x)) == canonical_form(x)``.
    """
    if isinstance(node, (Start, End, Silent, Atom)):
        return node

    if isinstance(node, PartialOrder):
        kids = tuple(canonical_form(c) for c in node.children)
        n = len(kids)
        ids = [node_id(k) for k in kids]
        # deterministic: by structural identity, ties by original position
        perm = sorted(range(n), key=lambda i: (ids[i], i))
        new_index = {old: new for new, old in enumerate(perm)}
        reduced = transitive_reduction(frozenset(node.order), n)
        edges = frozenset(
            OrderEdge(NodeId(new_index[e.src]), NodeId(new_index[e.dst]))
            for e in reduced
        )
        return PartialOrder(tuple(kids[i] for i in perm), edges, node.frequency)

    if isinstance(node, ChoiceGraph):
        # children are addressed by start/end and by edges under the boundary
        # law; the structure does not permit a free reordering.
        kids = tuple(canonical_form(c) for c in node.children)
        return ChoiceGraph(kids, node.edges, node.start, node.end, node.frequency)

    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def model_digest(node: PowlNode) -> str:
    """64-hex Merkle digest over the canonical **structure** of ``node``.

    Never digests a serialization string. Stable across differently-ordered but
    structurally equal inputs. See the module docstring for what this digest
    does *not* establish across repositories.
    """
    return node_id(canonical_form(node))
