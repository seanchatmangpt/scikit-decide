# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Subprocess bridge to ``bcinr-powl``'s real, paper-grounded
``WfNet::check_soundness()`` formal soundness checker (exhaustive BFS
token-game replay over the reachability graph; van der Aalst soundness
clauses per Kourani, Park & van der Aalst, "Hierarchical Decomposition of
Separable Workflow-Nets", arXiv:2602.15739, Definitions 3.1/3.3/3.4).

autofde-lab has no in-repo equivalent of this checker and must not
reimplement it -- this module bridges to the real Rust binary
(``soundness_cli``, built from ``~/bcinr/crates/bcinr-powl``) via
subprocess, the same out-of-process pattern already used for the MFW
planner oracle in :mod:`autofde_lab.wasm._mfw`
(``SubprocessMfwTransport``).

A :class:`~autofde_lab.powl.algebra.PowlNode` tree is not literally a
workflow net -- :func:`powl_to_wf_net_request` performs a real, documented
translation from the POWL 2.0 node algebra (``algebra.py``) into the
WF-net wire shape this bridge sends to the Rust CLI. See that function's
docstring for the exact translation rules and the design choices it had to
make that the shared wire schema does not spell out.

Nothing in this module actuates, admits, brokers, or issues receipts --
``check_soundness`` reports a structural/behavioural fact about a net, it
does not authorize running it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
)

__all__ = [
    "SoundnessBridgeError",
    "SoundnessResult",
    "WfNetRequest",
    "powl_to_wf_net_request",
    "check_soundness",
]


class SoundnessBridgeError(RuntimeError):
    """A named, typed failure of the soundness bridge.

    ``code`` follows the same shape as ``MfwInteropError`` in
    ``autofde_lab.wasm._mfw``:

    - ``TRANSPORT_UNAVAILABLE`` -- the real ``soundness_cli`` binary could
      not be located and no override path was given. Maps to
      ``BLOCKED:BCINR_SOUNDNESS_CLI_BINARY_NOT_FOUND`` in this repo's
      standing vocabulary.
    - ``TRANSPORT_FAILED`` -- the subprocess ran but failed (bad exit code,
      OS error, timeout).
    - ``TRANSPORT_PROTOCOL_INVALID`` -- the subprocess exited 0 but its
      stdout did not parse as the agreed response schema.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class SoundnessResult:
    """Mirrors the Rust CLI's response schema exactly, field for field."""

    no_dead_transitions: bool | None
    option_to_complete: bool | None
    proper_completion: bool | None
    is_safe: bool | None
    truncated: bool
    reachable_marking_count: int
    sound: bool | None

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "SoundnessResult":
        required = (
            "no_dead_transitions",
            "option_to_complete",
            "proper_completion",
            "is_safe",
            "truncated",
            "reachable_marking_count",
            "sound",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise SoundnessBridgeError(
                "TRANSPORT_PROTOCOL_INVALID",
                f"response missing required field(s): {missing}",
            )
        return cls(
            no_dead_transitions=payload["no_dead_transitions"],
            option_to_complete=payload["option_to_complete"],
            proper_completion=payload["proper_completion"],
            is_safe=payload["is_safe"],
            truncated=bool(payload["truncated"]),
            reachable_marking_count=int(payload["reachable_marking_count"]),
            sound=payload["sound"],
        )


@dataclass(frozen=True, slots=True)
class WfNetRequest:
    """The exact wire request shape the Rust CLI expects.

    Field names and the ``kind`` string literals (``"place_to_transition"``,
    ``"transition_to_place"``) match the shared schema byte for byte -- both
    sides of this bridge were built independently against the same contract
    and must not drift from it.
    """

    places: tuple[str, ...]
    transitions: tuple[tuple[str, str | None], ...]
    flow: tuple[tuple[str, str, str], ...]
    source: str
    sink: str

    def to_json(self) -> dict[str, Any]:
        return {
            "places": list(self.places),
            "transitions": [
                {"id": tid, "name": name} for tid, name in self.transitions
            ],
            "flow": [
                {"from": src, "to": dst, "kind": kind}
                for src, dst, kind in self.flow
            ],
            "source": self.source,
            "sink": self.sink,
        }


# ── PowlNode -> WfNet translation ───────────────────────────────────────────
#
# A PowlNode tree is a process algebra term, not a Petri net; the WF-net it
# denotes must be built compositionally. The translation used here follows
# the standard "process tree -> block-structured WF-net" construction
# (each subterm gets its own entry place and exit place, and composition
# operators wire those interface places together) rather than inventing an
# ad hoc scheme:
#
# - Every subterm compiles to a fragment with exactly one entry place and
#   one exit place (the WF-net "single-entry single-exit" block discipline).
# - Start()/End() are structural boundary markers in POWL, not activities;
#   they translate to a fragment with a tau transition between a fresh
#   entry place and a fresh exit place -- there is no activity to name.
# - Silent() is likewise a tau transition: a real transition with
#   ``name=None`` between its own entry and exit place, so it consumes zero
#   activity label but is still a token-game step (matches the Rust CLI's
#   own contract: "absent name field == null (tau)").
# - Atom(label) is one transition named ``label`` between a single fresh
#   input place and a single fresh output place.
# - PartialOrder(children, order): each child compiles to its own fragment.
#   Children with no predecessor in ``order`` have their entry place fed
#   directly from the PartialOrder's own entry place (parallel start);
#   children with no successor feed the PartialOrder's own exit place
#   (parallel join). An OrderEdge(src, dst) wires child src's exit place to
#   child dst's entry place. A WF-net arc can only connect a place to a
#   transition (never place-to-place), so every one of these structural
#   links is itself realized as its own fresh silent (tau) transition
#   between the two places, rather than a direct place-to-place arc.
# - ChoiceGraph(children, edges, start, end): each child again compiles to
#   its own fragment. The graph's own entry place feeds the ``start``
#   child's entry place (via a silent transition, as above); the ``end``
#   child's exit place feeds the graph's own exit place. A
#   ChoiceGraphEdge(src, dst) wires child src's exit place to child dst's
#   entry place, again via a silent transition. This is the one place a
#   genuine, repo-external design choice was required: a *cyclic* choice
#   graph (POWL 2.0's iteration construct) compiles to a WF-net whose
#   reachability graph is unbounded in the number of loop iterations but
#   whose *marking* count stays finite (loop re-entry revisits the same
#   places), so ``check_soundness()``'s BFS still terminates -- it is
#   exploring markings, not execution traces.


@dataclass(frozen=True, slots=True)
class _Fragment:
    """A compiled sub-net with exactly one entry and one exit place."""

    places: list[str]
    transitions: list[tuple[str, str | None]]
    flow: list[tuple[str, str, str]]
    entry: str
    exit: str


class _Counter:
    def __init__(self) -> None:
        self._n = 0

    def next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"


_PLACE_TO_TRANSITION = "place_to_transition"
_TRANSITION_TO_PLACE = "transition_to_place"
_SILENT_LINK = "__silent_link__"


def _compile(node: PowlNode, counter: _Counter) -> _Fragment:
    if isinstance(node, (Start, End, Silent)):
        entry = counter.next("p")
        exit_ = counter.next("p")
        tau = counter.next("t")
        return _Fragment(
            places=[entry, exit_],
            transitions=[(tau, None)],
            flow=[
                (entry, tau, _PLACE_TO_TRANSITION),
                (tau, exit_, _TRANSITION_TO_PLACE),
            ],
            entry=entry,
            exit=exit_,
        )
    if isinstance(node, Atom):
        entry = counter.next("p")
        exit_ = counter.next("p")
        tid = counter.next("t")
        return _Fragment(
            places=[entry, exit_],
            transitions=[(tid, node.label)],
            flow=[
                (entry, tid, _PLACE_TO_TRANSITION),
                (tid, exit_, _TRANSITION_TO_PLACE),
            ],
            entry=entry,
            exit=exit_,
        )
    if isinstance(node, PartialOrder):
        return _compile_partial_order(node, counter)
    if isinstance(node, ChoiceGraph):
        return _compile_choice_graph(node, counter)
    raise TypeError(f"unrecognized PowlNode variant: {type(node).__name__}")


def _compile_partial_order(node: PartialOrder, counter: _Counter) -> _Fragment:
    n = len(node.children)
    child_fragments = [_compile(c, counter) for c in node.children]

    has_pred = [False] * n
    has_succ = [False] * n
    for edge in node.order:
        has_succ[edge.src] = True
        has_pred[edge.dst] = True

    entry = counter.next("p")
    exit_ = counter.next("p")

    places: list[str] = [entry, exit_]
    transitions: list[tuple[str, str | None]] = []
    flow: list[tuple[str, str, str]] = []
    for frag in child_fragments:
        places.extend(frag.places)
        transitions.extend(frag.transitions)
        flow.extend(frag.flow)

    for i, frag in enumerate(child_fragments):
        if not has_pred[i]:
            flow.append((entry, frag.entry, _SILENT_LINK))
        if not has_succ[i]:
            flow.append((frag.exit, exit_, _SILENT_LINK))

    for edge in node.order:
        src_frag = child_fragments[edge.src]
        dst_frag = child_fragments[edge.dst]
        flow.append((src_frag.exit, dst_frag.entry, _SILENT_LINK))

    return _finish_composite(entry, exit_, places, transitions, flow, counter)


def _compile_choice_graph(node: ChoiceGraph, counter: _Counter) -> _Fragment:
    child_fragments = [_compile(c, counter) for c in node.children]

    entry = counter.next("p")
    exit_ = counter.next("p")

    places: list[str] = [entry, exit_]
    transitions: list[tuple[str, str | None]] = []
    flow: list[tuple[str, str, str]] = []
    for frag in child_fragments:
        places.extend(frag.places)
        transitions.extend(frag.transitions)
        flow.extend(frag.flow)

    flow.append((entry, child_fragments[node.start].entry, _SILENT_LINK))
    flow.append((child_fragments[node.end].exit, exit_, _SILENT_LINK))

    for edge in node.edges:
        src_frag = child_fragments[edge.src]
        dst_frag = child_fragments[edge.dst]
        flow.append((src_frag.exit, dst_frag.entry, _SILENT_LINK))

    return _finish_composite(entry, exit_, places, transitions, flow, counter)


def _finish_composite(
    entry: str,
    exit_: str,
    places: list[str],
    transitions: list[tuple[str, str | None]],
    flow: list[tuple[str, str, str]],
    counter: _Counter,
) -> _Fragment:
    """Realize each ``_SILENT_LINK`` placeholder as a real tau transition.

    A place cannot flow directly into another place in a WF-net (arcs only
    ever connect a place to a transition or a transition to a place), so
    every structural link recorded above compiles to its own fresh silent
    transition.
    """
    real_flow: list[tuple[str, str, str]] = []
    for src, dst, kind in flow:
        if kind == _SILENT_LINK:
            tau = counter.next("t")
            transitions.append((tau, None))
            real_flow.append((src, tau, _PLACE_TO_TRANSITION))
            real_flow.append((tau, dst, _TRANSITION_TO_PLACE))
        else:
            real_flow.append((src, dst, kind))
    return _Fragment(
        places=places,
        transitions=transitions,
        flow=real_flow,
        entry=entry,
        exit=exit_,
    )


def powl_to_wf_net_request(root: PowlNode) -> WfNetRequest:
    """Compile a :class:`PowlNode` tree into the WF-net request wire shape.

    See the module-level translation notes above ``_Fragment`` for the
    exact rules. The returned request always has a unique source (the
    compiled root fragment's entry place) and a unique sink (its exit
    place), matching ``bcinr_powl::wf_net::WfNet``'s own well-formedness
    requirement.
    """
    counter = _Counter()
    fragment = _compile(root, counter)
    return WfNetRequest(
        places=tuple(fragment.places),
        transitions=tuple(fragment.transitions),
        flow=tuple(fragment.flow),
        source=fragment.entry,
        sink=fragment.exit,
    )


# ── subprocess bridge ────────────────────────────────────────────────────────


def _default_executable() -> str:
    found = shutil.which("soundness_cli")
    if found:
        return found
    candidates = (
        Path.home() / "bcinr" / "target" / "debug" / "soundness_cli",
        Path.home() / "bcinr" / "target" / "release" / "soundness_cli",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def check_soundness(
    request: WfNetRequest | PowlNode,
    *,
    executable: str | None = None,
    timeout: float = 10.0,
) -> SoundnessResult:
    """Invoke the real ``soundness_cli`` Rust binary and return its verdict.

    ``request`` may be a pre-built :class:`WfNetRequest`, or a
    :class:`PowlNode` tree (converted internally via
    :func:`powl_to_wf_net_request`).

    Raises :class:`SoundnessBridgeError` when the binary cannot be found
    (``TRANSPORT_UNAVAILABLE``), fails to run (``TRANSPORT_FAILED``), or
    returns output that does not parse as the agreed response schema
    (``TRANSPORT_PROTOCOL_INVALID``). Never fabricates a result.
    """
    wf_request = (
        request
        if isinstance(request, WfNetRequest)
        else powl_to_wf_net_request(request)
    )

    exe = executable or _default_executable()
    if not exe:
        raise SoundnessBridgeError(
            "TRANSPORT_UNAVAILABLE",
            "the real bcinr-powl soundness_cli binary could not be found "
            "(checked PATH and ~/bcinr/target/{debug,release}/soundness_cli)",
        )
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    payload = json.dumps(wf_request.to_json()).encode("utf-8")
    try:
        completed = subprocess.run(
            [exe],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SoundnessBridgeError(
            "TRANSPORT_FAILED",
            "soundness_cli process failed",
        ) from exc
    if completed.returncode != 0:
        raise SoundnessBridgeError(
            "TRANSPORT_FAILED",
            completed.stderr.decode("utf-8", "replace").strip()
            or f"soundness_cli exited {completed.returncode}",
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SoundnessBridgeError(
            "TRANSPORT_PROTOCOL_INVALID",
            "soundness_cli returned invalid JSON",
        ) from exc
    if not isinstance(value, dict):
        raise SoundnessBridgeError(
            "TRANSPORT_PROTOCOL_INVALID",
            "soundness_cli result must be a JSON object",
        )
    return SoundnessResult.from_json(value)
