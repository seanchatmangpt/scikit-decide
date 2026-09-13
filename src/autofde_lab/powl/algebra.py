# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The POWL 2.0 node algebra.

Exactly six node kinds exist: :class:`Start`, :class:`End`, :class:`Atom`,
:class:`Silent`, :class:`PartialOrder` and :class:`ChoiceGraph`. POWL 1.0's
``Xor`` and ``Loop`` are prohibited — iteration in POWL 2.0 is expressed by a
*cyclic choice graph*, not by a loop operator.

Arena/index convention
----------------------
A composite node owns its children in a tuple. Its edges reference those
children by **0-based index into that same tuple** — never by a global
identifier. This mirrors the arena style used in
``~/wasm4pm-compat/src/powl.rs``. An index outside ``range(len(children))``
is a :data:`~autofde_lab.powl.refusals.PowlRefusal.DANGLING_REFERENCE`.

Two edge types, deliberately not interchangeable
------------------------------------------------
:class:`OrderEdge` (precedence inside a partial order) and
:class:`ChoiceGraphEdge` (a directed transition inside a choice graph) are two
*distinct* frozen dataclasses, not aliases and not bare tuples.
``~/wasm4pm-compat/src/powl.rs:584`` (``OrderEdge``) and
``~/wasm4pm-compat/src/powl.rs:629`` (``ChoiceGraphEdge``) enforce the same
separation in Rust with compile-fail fixtures; Python has no compile-fail
fixture, so this module enforces it at construction time with
:data:`~autofde_lab.powl.refusals.PowlRefusal.EDGE_TYPE_MISMATCH`.

Storage law
-----------
A partial order is irreflexive and transitive. **Canonical storage is the
transitive reduction**: ``PartialOrder.order`` always holds the reduction,
whatever was passed in. The transitive **closure** is computed exactly once at
construction and exposed as :attr:`PartialOrder.closure`; an executor reads
only the closure, while digests and serialization use only the reduction.

Nothing in this module actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, NewType, TypeAlias, Union

from autofde_lab.fabric.canonical import canonical_json
from autofde_lab.powl.frequency import ONCE, Frequency
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = [
    "NodeId",
    "MAX_POWL_DEPTH",
    "Consequence",
    "Guard",
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
]

NodeId = NewType("NodeId", int)

#: Maximum nesting depth of a POWL 2.0 tree (atoms are depth 1).
MAX_POWL_DEPTH = 8

#: The four activity-consequence classes from ``ontology/process.ttl``'s
#: ``afl:ConsequenceClass`` vocabulary (PURE/READ/DO/VERIFY), manufactured
#: additively (unwired) as ``constitution.process.StandingValue`` — this
#: `Literal` is the real, executable type the algebra/validator/executor use;
#: DSPy reasons and constructs candidate ``Atom``s but a ``DO``-consequence
#: atom's bound callable must still route through the existing
#: ``GatedCapabilityBinding``/``CapabilityGate`` machinery, never bypassed by
#: this vocabulary.
Consequence: TypeAlias = Literal["PURE", "READ", "DO", "VERIFY"]


# ── edges ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, order=True)
class OrderEdge:
    """Precedence ``src -> dst`` inside a :class:`PartialOrder`.

    Structural precedence only: ``src`` must complete before ``dst`` may
    start. Distinct from :class:`ChoiceGraphEdge` — see the module docstring.
    """

    src: NodeId
    dst: NodeId


@dataclass(frozen=True, slots=True)
class Guard:
    """A named, evaluable predicate on a :class:`ChoiceGraphEdge`.

    ``predicate_name`` names a predicate an external, deterministic
    ``guard_evaluator`` (see :mod:`autofde_lab.powl.executor`) resolves
    against the current epistemic state at execution time — this dataclass
    only names the predicate, per ``ontology/process.ttl``'s ``afl:Guard``
    comment ("the ontology names the predicate, it does not define its
    truth"). ``predicate_args`` is arbitrary canonical-JSON-able data,
    mirroring :class:`Atom`'s own ``bindings`` field — and, like
    ``Atom.bindings``, excluded from equality/hashing (a plain ``dict`` is
    unhashable) in favor of ``key``, a canonical-JSON identity string
    computed at construction.
    """

    predicate_name: str
    predicate_args: Mapping[str, Any] = field(default_factory=dict, compare=False)
    key: str = field(init=False, compare=True, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "key",
            canonical_json({"predicate_name": self.predicate_name, "predicate_args": dict(self.predicate_args)}),
        )


@dataclass(frozen=True, slots=True)
class ChoiceGraphEdge:
    """A directed transition ``src -> dst`` inside a :class:`ChoiceGraph`.

    Distinct from :class:`OrderEdge` — see the module docstring. ``guard``,
    when present, is the real predicate an executor must evaluate true
    before taking this transition; ``None`` marks an unconditional/"else"
    edge — a real, legal shape (a guarded branch alongside an unconditional
    "else" branch between the same two nodes), which real call sites
    (`powl/membership.py`, `powl/witness.py`) already rely on ``sorted()``
    over a ``frozenset[ChoiceGraphEdge]`` for. This dataclass therefore
    defines ``__lt__`` by hand (rather than requesting the stdlib
    ``order=True``, which would compare ``guard`` fields directly and raise
    ``TypeError`` on a ``None``-vs-``Guard`` tie) so those existing call
    sites keep getting a real, deterministic total order even when two edges
    share ``src``/``dst`` and differ only by guard.
    """

    src: NodeId
    dst: NodeId
    guard: "Guard | None" = None

    def __lt__(self, other: "ChoiceGraphEdge") -> bool:
        if not isinstance(other, ChoiceGraphEdge):
            return NotImplemented
        self_guard_key = self.guard.key if self.guard is not None else ""
        other_guard_key = other.guard.key if other.guard is not None else ""
        return (self.src, self.dst, self_guard_key) < (other.src, other.dst, other_guard_key)


# ── edge algebra ────────────────────────────────────────────────────────────


def _reachability(edges: frozenset[OrderEdge], n: int) -> list[list[bool]]:
    reach = [[False] * n for _ in range(n)]
    for e in edges:
        reach[e.src][e.dst] = True
    for k in range(n):
        rk = reach[k]
        for i in range(n):
            if reach[i][k]:
                ri = reach[i]
                for j in range(n):
                    if rk[j]:
                        ri[j] = True
    return reach


def _check_edges(edges: frozenset[OrderEdge], n: int) -> None:
    for e in edges:
        if not isinstance(e, OrderEdge):
            raise PowlError(
                PowlRefusal.EDGE_TYPE_MISMATCH,
                f"expected OrderEdge, got {type(e).__name__}",
            )
        if not (0 <= e.src < n and 0 <= e.dst < n):
            raise PowlError(
                PowlRefusal.DANGLING_REFERENCE,
                f"edge {e.src}->{e.dst} outside range(0, {n})",
            )


def transitive_closure(edges: frozenset[OrderEdge], n: int) -> frozenset[OrderEdge]:
    """Transitive closure of ``edges`` over ``n`` indexed children.

    Raises ``CYCLIC_PARTIAL_ORDER`` if the relation is not irreflexive after
    closure (i.e. the input contained a cycle or a self-loop).
    """
    edges = frozenset(edges)
    _check_edges(edges, n)
    reach = _reachability(edges, n)
    for i in range(n):
        if reach[i][i]:
            raise PowlError(
                PowlRefusal.CYCLIC_PARTIAL_ORDER, f"node index {i} reaches itself"
            )
    return frozenset(
        OrderEdge(NodeId(i), NodeId(j))
        for i in range(n)
        for j in range(n)
        if reach[i][j]
    )


def transitive_reduction(edges: frozenset[OrderEdge], n: int) -> frozenset[OrderEdge]:
    """Transitive reduction of ``edges`` over ``n`` indexed children.

    The input may be any relation with the same closure (the reduction, the
    closure, or anything between); the result is identical. Raises
    ``CYCLIC_PARTIAL_ORDER`` on a cyclic input.
    """
    closure = transitive_closure(edges, n)
    reach = [[False] * n for _ in range(n)]
    for e in closure:
        reach[e.src][e.dst] = True
    out: set[OrderEdge] = set()
    for e in closure:
        i, j = e.src, e.dst
        if not any(k != i and k != j and reach[i][k] and reach[k][j] for k in range(n)):
            out.add(e)
    return frozenset(out)


# ── leaf nodes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Start:
    """The unique start marker ``|>``."""


@dataclass(frozen=True, slots=True)
class End:
    """The unique end marker ``[]``."""


@dataclass(frozen=True, slots=True)
class Silent:
    """A silent (tau) step: observable structure, no activity."""


@dataclass(frozen=True, slots=True)
class Atom:
    """A labelled activity.

    ``action`` is an opaque payload identifying what a downstream *broker*
    would be asked to authorize; this package never invokes it. ``bindings``
    is arbitrary canonical-JSON-able parameter data.

    ``consequence`` names the activity's real effect class, per
    ``ontology/process.ttl``'s ``afl:ConsequenceClass`` vocabulary
    (PURE/READ/DO/VERIFY). Defaults to ``"PURE"`` (matching this session's
    own DSPy-reasons/GymAct-actuates law: an unlabelled step is assumed to
    have no environmental effect until explicitly marked otherwise). This
    field is descriptive, not enforcing — nothing in this module invokes
    ``action``, so a ``"DO"``-consequence atom's real gating still happens
    entirely at the executor/broker layer
    (``GatedCapabilityBinding``/``CapabilityGate``), exactly as it already
    does for every other atom today; this field only makes that consequence
    class visible to a validator/executor that wants to check it.

    ``action`` and ``bindings`` are folded into :attr:`key` for value equality
    and hashing, so an ``Atom`` stays hashable even with a ``dict`` binding.
    ``consequence`` also participates in ``key`` (two atoms with the same
    label/action/bindings but a different consequence are genuinely
    different steps).
    """

    label: str
    action: Any = field(default=None, compare=False)
    bindings: Mapping[str, Any] = field(default_factory=dict, compare=False)
    consequence: "Consequence" = "PURE"
    key: str = field(init=False, compare=True, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "key",
            canonical_json(
                {
                    "label": self.label,
                    "action": _action_identity(self.action),
                    "bindings": dict(self.bindings),
                    "consequence": self.consequence,
                }
            ),
        )


def _action_identity(action: Any) -> str:
    """Stable textual identity for an opaque action payload."""
    if action is None:
        return ""
    for attr in ("__qualname__", "__name__"):
        name = getattr(action, attr, None)
        if isinstance(name, str):
            return f"{getattr(action, '__module__', '')}.{name}"
    if isinstance(action, (str, int, float, bool)):
        return f"{type(action).__name__}:{action}"
    return f"{type(action).__module__}.{type(action).__qualname__}"


# ── composite nodes ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PartialOrder:
    """A partial order over ``children``, indexed 0-based into ``children``.

    ``order`` is normalized to the **transitive reduction** at construction, so
    ``PartialOrder(c, transitive_closure(E, n))`` and
    ``PartialOrder(c, transitive_reduction(E, n))`` are equal objects.
    :attr:`closure` is computed once at construction and cached.
    """

    children: tuple["PowlNode", ...]
    order: frozenset[OrderEdge] = frozenset()
    frequency: Frequency = ONCE
    _closure: frozenset[OrderEdge] = field(
        init=False, compare=False, repr=False, hash=False, default=frozenset()
    )
    _depth: int = field(init=False, compare=False, repr=False, hash=False, default=1)

    def __post_init__(self) -> None:
        n = len(self.children)
        if n < 2:
            raise PowlError(
                PowlRefusal.INVALID_PARTIAL_ORDER_ARITY,
                f"PartialOrder requires n >= 2 children, got {n}",
            )
        edges = frozenset(self.order)
        _check_edges(edges, n)
        closure = transitive_closure(edges, n)  # raises CYCLIC_PARTIAL_ORDER
        object.__setattr__(self, "order", transitive_reduction(closure, n))
        object.__setattr__(self, "_closure", closure)
        object.__setattr__(self, "_depth", _composite_depth(self.children))

    @property
    def closure(self) -> frozenset[OrderEdge]:
        """The transitive closure, computed once at construction."""
        return self._closure

    @property
    def depth(self) -> int:
        return self._depth


@dataclass(frozen=True, slots=True)
class ChoiceGraph:
    """A (possibly cyclic) choice graph over ``children``, indexed 0-based.

    Cycles are how POWL 2.0 expresses iteration and are **always accepted**.
    ``start`` must have no incoming edge and ``end`` no outgoing edge;
    reachability / co-reachability of every node is checked by the validator,
    not here.
    """

    children: tuple["PowlNode", ...]
    edges: frozenset[ChoiceGraphEdge] = frozenset()
    start: int = 0
    end: int = 1
    frequency: Frequency = ONCE
    _depth: int = field(init=False, compare=False, repr=False, hash=False, default=1)

    def __post_init__(self) -> None:
        n = len(self.children)
        if n < 2:
            raise PowlError(
                PowlRefusal.INVALID_CHOICE_ARITY,
                f"ChoiceGraph requires n >= 2 children, got {n} (required_min=2)",
            )
        edges = frozenset(self.edges)
        for e in edges:
            if not isinstance(e, ChoiceGraphEdge):
                raise PowlError(
                    PowlRefusal.EDGE_TYPE_MISMATCH,
                    f"expected ChoiceGraphEdge, got {type(e).__name__}",
                )
            if not (0 <= e.src < n and 0 <= e.dst < n):
                raise PowlError(
                    PowlRefusal.DANGLING_REFERENCE,
                    f"edge {e.src}->{e.dst} outside range(0, {n})",
                )
        for name, idx in (("start", self.start), ("end", self.end)):
            if not (0 <= idx < n):
                raise PowlError(
                    PowlRefusal.DANGLING_REFERENCE,
                    f"{name}={idx} outside range(0, {n})",
                )
        if self.start == self.end:
            raise PowlError(
                PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH,
                f"start and end coincide at index {self.start}",
            )
        for e in edges:
            if e.dst == self.start:
                raise PowlError(
                    PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH,
                    f"start index {self.start} has an incoming edge from {e.src}",
                )
            if e.src == self.end:
                raise PowlError(
                    PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH,
                    f"end index {self.end} has an outgoing edge to {e.dst}",
                )
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "_depth", _composite_depth(self.children))

    @property
    def depth(self) -> int:
        return self._depth


PowlNode: TypeAlias = Union[Start, End, Atom, Silent, PartialOrder, ChoiceGraph]


# ── depth ───────────────────────────────────────────────────────────────────


def node_depth(node: PowlNode) -> int:
    """Nesting depth of ``node``; leaves are depth 1."""
    if isinstance(node, (PartialOrder, ChoiceGraph)):
        return node.depth
    return 1


def _composite_depth(children: tuple[PowlNode, ...]) -> int:
    depth = 1 + max((node_depth(c) for c in children), default=0)
    if depth > MAX_POWL_DEPTH:
        raise PowlError(
            PowlRefusal.DEPTH_EXCEEDED,
            f"depth {depth} exceeds MAX_POWL_DEPTH={MAX_POWL_DEPTH}",
        )
    return depth
