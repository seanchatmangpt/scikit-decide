# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic sampling of linearizations, and honest coverage reporting.

Sampling is seeded from a ``sha256`` of a caller-supplied seed *string*; no
clock, no process entropy, no unseeded RNG. The same seed yields the same
sequence of samples, so a witness run is reproducible from its report.

Counting is the hard part, and the honesty rule follows from it: counting the
linear extensions of a partial order is **#P-complete** (Brightwell & Winkler,
1991). :func:`count_linearizations` therefore returns an exact count only for
small child counts and ``None`` otherwise —
:meth:`WitnessReport.coverage_statement` must then report an *unknown* total
and never a percentage, because a fraction whose denominator is unknown is
exactly the false precision this module exists to prevent.

Nothing here actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Iterator

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
)
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = [
    "sample_linearizations",
    "count_linearizations",
    "WitnessReport",
    "rng_for_seed",
]

#: Cap on steps in a random choice-graph walk; cyclic choice graphs are legal.
_MAX_WALK_STEPS = 256


def rng_for_seed(seed: str) -> random.Random:
    """A ``random.Random`` derived deterministically from ``seed``."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, "big"))


# ── sampling ────────────────────────────────────────────────────────────────


def _random_topological_order(node: PartialOrder, rng: random.Random) -> list[int]:
    n = len(node.children)
    preds = [0] * n
    succs: list[list[int]] = [[] for _ in range(n)]
    for e in sorted(node.order):
        preds[e.dst] += 1
        succs[e.src].append(e.dst)
    ready = sorted(i for i in range(n) if preds[i] == 0)
    out: list[int] = []
    while ready:
        k = rng.randrange(len(ready))
        i = ready.pop(k)
        out.append(i)
        for j in sorted(succs[i]):
            preds[j] -= 1
            if preds[j] == 0:
                ready.append(j)
        ready.sort()
    return out


def _one_linearization(node: PowlNode, rng: random.Random) -> tuple[str, ...]:
    if isinstance(node, Atom):
        return (node.label,)
    if isinstance(node, (Start, End, Silent)):
        return ()
    if isinstance(node, PartialOrder):
        out: list[str] = []
        for i in _random_topological_order(node, rng):
            out.extend(_one_linearization(node.children[i], rng))
        return tuple(out)
    if isinstance(node, ChoiceGraph):
        succs: dict[int, list[int]] = {}
        for e in sorted(node.edges):
            succs.setdefault(e.src, []).append(e.dst)
        out = []
        cur = node.start
        for _ in range(_MAX_WALK_STEPS):
            out.extend(_one_linearization(node.children[cur], rng))
            if cur == node.end:
                return tuple(out)
            options = succs.get(cur)
            if not options:
                raise PowlError(
                    PowlRefusal.CHOICE_GRAPH_DISCONNECTED,
                    f"child index {cur} has no outgoing edge and is not the end",
                )
            cur = options[rng.randrange(len(options))]
        raise PowlError(
            PowlRefusal.CHOICE_GRAPH_DISCONNECTED,
            f"no end reached within {_MAX_WALK_STEPS} steps",
        )
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def sample_linearizations(
    node: PowlNode, *, samples: int, seed: str
) -> Iterator[tuple[str, ...]]:
    """Yield ``samples`` linearizations of ``node``, deterministically seeded.

    Samples are drawn with replacement; duplicates are expected and are not
    filtered, because filtering would silently change the meaning of the
    sample count in a report.
    """
    if samples < 0:
        raise ValueError(f"samples must be >= 0, got {samples}")
    rng = rng_for_seed(seed)
    for _ in range(samples):
        yield _one_linearization(node, rng)


# ── counting ────────────────────────────────────────────────────────────────


def count_linearizations(node: PowlNode, *, exact_limit: int = 10) -> int | None:
    """Exact number of linearizations of ``node``, or ``None`` if not computed.

    Counting the linear extensions of a partial order is **#P-complete**
    (Brightwell & Winkler, 1991), so this returns a number only when it is
    cheap and unambiguous:

    * a leaf → ``1``;
    * a :class:`~autofde_lab.powl.algebra.PartialOrder` with
      ``len(children) <= exact_limit`` **and** only leaf children → the exact
      count, by a subset dynamic program over the closed order;
    * anything else (more children than ``exact_limit``, a composite child
      whose internal steps could interleave with its siblings', or a
      :class:`~autofde_lab.powl.algebra.ChoiceGraph`, which may be cyclic and
      hence have infinitely many walks) → ``None``.

    ``None`` means "not counted", never "zero".
    """
    if isinstance(node, (Atom, Start, End, Silent)):
        return 1
    if isinstance(node, ChoiceGraph):
        return None
    if not isinstance(node, PartialOrder):
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"{type(node).__name__} is not a POWL 2.0 node kind",
        )
    n = len(node.children)
    if n > exact_limit:
        return None
    if any(isinstance(c, (PartialOrder, ChoiceGraph)) for c in node.children):
        return None

    required = [0] * n  # bitmask of predecessors in the closed order
    for e in node.closure:
        required[e.dst] |= 1 << e.src

    counts = [0] * (1 << n)
    counts[0] = 1
    for mask in range(1 << n):
        if counts[mask] == 0:
            continue
        for j in range(n):
            if mask & (1 << j):
                continue
            if required[j] & ~mask:
                continue
            counts[mask | (1 << j)] += counts[mask]
    return counts[(1 << n) - 1]


# ── reporting ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WitnessReport:
    """The outcome of a sampling run, stated without false precision."""

    samples: tuple[tuple[str, ...], ...]
    seed: str
    counterexamples: tuple[tuple[str, ...], ...] = ()
    total_linearizations: int | None = None

    def coverage_statement(self) -> str:
        """A coverage sentence that never expresses an unknown as a fraction.

        When :attr:`total_linearizations` is ``None`` the total is reported as
        ``UNKNOWN`` and no percentage appears anywhere in the string.
        """
        n = len(self.samples)
        if self.total_linearizations is None:
            head = f"sampled {n} of an UNKNOWN total (counting is #P-complete)"
        else:
            head = f"sampled {n} of {self.total_linearizations} total linearizations"
        if self.counterexamples:
            tail = f"{len(self.counterexamples)} counterexample(s) found"
        else:
            tail = "no counterexample found"
        return f"{head}; {tail}"
