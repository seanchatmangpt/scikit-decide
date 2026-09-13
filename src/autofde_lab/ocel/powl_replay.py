# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Structural POWL replay, projected into a real OCEL 2.0 trace.

Drives a :class:`~autofde_lab.powl.algebra.PowlNode` tree through
:mod:`autofde_lab.powl.executor`'s **existing** ``enabled()``/``fire()``
functions -- this module reimplements no traversal logic of its own -- and
records each real structural fire as a real OCEL event via
:func:`autofde_lab.ocel.mcp_session.append_tool_call_event`.

Boundary this module must never cross
--------------------------------------
``powl/executor.py`` is a *reference traversal*: it fires nothing in the
world, and an :class:`~autofde_lab.powl.algebra.Atom`'s ``action`` payload is
"never invoked, never brokered, never admitted" (its own module docstring,
quoted exactly). This module inherits that guarantee by construction --
it calls only ``enabled()``/``fire()`` -- and additionally never imports,
directly or transitively:

- ``autofde_lab.ofmf`` (any submodule, including ``ofmf_keystone``)
- ``SpiffExecutor`` / ``SpiffWorkflowAdapter``
- the ``SpiffWorkflow`` package itself

``tests/ocel/test_powl_replay_boundary.py`` checks this mechanically, via a
``sys.modules`` inspection after import -- not as a documentation promise.

Representation choice
----------------------
This module drives ``powl/algebra.py``'s :class:`PowlNode` tree directly
(the shape ``powl/executor.py`` already consumes), not ``fabric/powl.py``'s
Turtle-projector :class:`PowlModel`. As of this session's own finding there
is no converter between the two POWL representations, and writing one is
real, unscoped semantic work (resolving ``PowlModel``'s node-id graph back
into ``algebra.py``'s index-addressed children/edges arena convention).
Building this replay directly against a hand-constructed (or
``project_plan_to_powl``-inspired) ``PowlNode`` tree is the narrower, honest
scope for this item -- a caller that already has a parsed ``PowlModel`` can
still reach this module by building the equivalent ``PowlNode`` tree, which
is what :func:`plan_lines_to_powl_node` below does for the common case (a
flat, real plan action sequence).
"""

from __future__ import annotations

import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable, Sequence

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder
from autofde_lab.powl.algebra import Atom, PartialOrder, PowlNode
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    Marking,
    NodePath,
    enabled,
    fire,
    is_final,
)

__all__ = [
    "plan_lines_to_powl_node",
    "replay_structural_fires",
    "ActionBindingTimeout",
]

#: An action binding: given a fired Atom's real attributes (``label``,
#: ``action``, ``bindings``) as a plain dict, returns a real, JSON-attachable
#: result. Receives only the Atom's data, never the ``Atom`` object or the
#: ``PowlNode`` tree itself, so a binding cannot reach back into the
#: structural replay this module drives -- it may only compute a value from
#: what fired.
ActionBinding = Callable[[dict[str, Any]], Any]


class ActionBindingTimeout(TimeoutError):
    """A bound callable did not return within ``binding_timeout_s``.

    Raised by *this* replay driver, never by ``powl/executor.py`` -- the
    executor's own termination remains purely structural (visit-count
    bounded, no wall clock; see its module docstring). This timeout bounds
    only the caller-supplied side-effecting callable this module invokes on
    top of an already-completed structural fire; it has no bearing on, and
    does not change, how ``enabled()``/``fire()`` terminate.
    """


def _atom_labels(node: PowlNode) -> list[str]:
    """Every :class:`Atom` label reachable from ``node``, one entry per Atom
    (duplicates preserved) -- used only to detect label collisions and
    caller typos in ``action_bindings``, never to drive traversal."""
    if isinstance(node, Atom):
        return [node.label]
    children = getattr(node, "children", ())
    labels: list[str] = []
    for child in children:
        labels.extend(_atom_labels(child))
    return labels


def plan_lines_to_powl_node(plan_lines: Sequence[str]) -> PowlNode:
    """A real, totally-ordered :class:`PowlNode` tree for a real flat plan.

    ``plan_lines`` is e.g. the output of ``fabric/powl.py``'s
    ``decision_result_to_plan_lines`` (VAL-style action strings such as
    ``"(unstack a b)"``), or any other real, ordered sequence of step labels.
    Each line becomes one :class:`Atom` leaf; a :class:`PartialOrder` with a
    full chain of :class:`~autofde_lab.powl.algebra.OrderEdge`\\ s enforces
    strict sequencing, matching the flat plan's own total order.

    Requires at least two lines: :class:`PartialOrder` itself requires
    ``n >= 2`` children (its own construction-time invariant), so a
    single-step plan cannot be represented without a composite wrapper this
    function declines to invent silently.
    """
    if len(plan_lines) < 2:
        raise ValueError(
            f"plan_lines_to_powl_node requires >= 2 steps, got {len(plan_lines)}"
        )
    from autofde_lab.powl.algebra import OrderEdge

    children = tuple(Atom(label=line) for line in plan_lines)
    order = frozenset(
        OrderEdge(i, i + 1) for i in range(len(children) - 1)  # type: ignore[arg-type]
    )
    return PartialOrder(children=children, order=order)


def replay_structural_fires(
    model: PowlNode,
    *,
    session_id: str | None = None,
    action_bindings: dict[str, ActionBinding] | None = None,
    binding_timeout_s: float | None = None,
) -> OcelLog:
    """Replay ``model`` to completion via ``powl/executor.py``'s
    ``enabled()``/``fire()`` only, recording one real ``"powl_structural_fire"``
    OCEL event per structural fire.

    At each step this function picks the lexicographically-smallest enabled
    path -- a caller-side policy choice made *here*, in the replay driver,
    never inside the executor itself (``enabled()``'s own law: it returns a
    set, never an ordered choice). Returns the validated
    :class:`~autofde_lab.ocel.log.OcelLog`.

    ``action_bindings`` -- optional, additive, backward-compatible
    -----------------------------------------------------------------
    When ``None`` (the default) or when a fired :class:`Atom`'s ``label`` has
    no matching key, behavior is byte-for-byte unchanged from before this
    parameter existed: pure structural advancement, one
    ``"powl_structural_fire"`` event per fire, nothing else invoked.

    When provided and a fired ``Atom``'s ``label`` matches a key, the bound
    callable is invoked with that atom's real attributes
    (``{"label": ..., "action": ..., "bindings": ...}``) *after* the
    structural fire has already advanced the marking -- so a binding can
    never influence which path was enabled or chosen; it only observes what
    already, structurally, fired. Note this module's own boundary doctrine is
    unaffected: ``powl/executor.py`` itself still never invokes ``action``;
    this module still calls only ``enabled()``/``fire()`` for traversal. The
    binding is invoked by *this* replay driver, as an explicit, opt-in,
    caller-supplied side effect layered on top of the same structural trace,
    not a change to the executor's own neutrality.

    A successful binding's real return value is recorded as an additional
    ``outcome`` attribute (``action_result``) on that same fire's OCEL event
    -- the existing event shape (``standing``, ``detail``, ``steps_taken``)
    is extended, never replaced.

    A binding that raises is recorded honestly as a real
    ``"powl_action_binding_error"`` OCEL event (never silently swallowed),
    and replay then **halts**: the original exception is re-raised after
    recording, so the caller observes the failure and no further structural
    fires are attempted past an action whose real invocation failed. This
    mirrors ``mcp_instrumentation.instrumented``'s own precedent (record,
    then re-raise unchanged) and this repo's absence-is-not-evidence law: a
    replay that pressed on past an unobserved-to-have-succeeded action would
    manufacture a completed trace the world never actually produced. The
    same halt-and-record shape covers :class:`ActionBindingTimeout` -- see
    ``binding_timeout_s`` below.

    ``binding_timeout_s`` -- bounding a caller-supplied callable
    --------------------------------------------------------------
    ``powl/executor.py``'s own termination is deliberately *structural, not
    wall-clock* (its module docstring: "every fire either completes a node
    or increments a bounded counter") -- that design covers the
    ``enabled()``/``fire()`` traversal this module still drives unchanged.
    It does **not** cover ``action_bindings``: a bound callable is arbitrary
    caller-supplied code (a real HTTP call, a real subprocess, anything),
    invoked directly by *this* driver, with no structural counter bounding
    it. Left unbounded, one slow or hung binding blocks this replay forever
    -- a real gap the structural design was never meant to close, since the
    callable did not exist when that design was written.

    Default (``binding_timeout_s=None``) preserves the exact prior
    behavior: the callable is invoked directly, no timeout, byte-for-byte
    identical to before this parameter existed. Passing a positive float
    runs the callable on a worker thread and bounds the *wait* on it; if it
    does not return in time, an :class:`ActionBindingTimeout` is recorded as
    a ``"powl_action_binding_error"`` OCEL event (same shape as a raising
    binding, with the timeout as the recorded error) and then raised --
    replay halts, matching the raising-binding case exactly. Python cannot
    forcibly kill a running thread, so a genuinely hung callable's thread
    keeps running in the background after the timeout fires; what this
    guards is the replay never blocking past the bound, not the leaked
    thread's own termination.
    """
    session_id = session_id or f"powl-replay-{uuid.uuid4().hex[:8]}"
    recorder = OcelSessionRecorder(session_id, server_name="powl-structural-replay")

    if action_bindings:
        all_labels = _atom_labels(model)
        label_counts = Counter(all_labels)
        present = set(all_labels)

        unmatched = sorted(set(action_bindings) - present)
        if unmatched:
            raise ValueError(
                "action_bindings has key(s) with no matching Atom label in "
                f"model: {unmatched!r} -- refusing rather than silently "
                "doing nothing (likely a typo in a label)"
            )

        collided = sorted(
            label
            for label in action_bindings
            if label_counts.get(label, 0) > 1
        )
        if collided:
            raise ValueError(
                "action_bindings key(s) match more than one Atom in model "
                f"by label: {collided!r} -- a label-keyed binding cannot "
                "structurally distinguish which real pipeline step fired, "
                "so this is refused rather than silently dispatching the "
                "same callable to both (construct distinct labels for "
                "distinct steps, or bind by structural path instead)"
            )

    marking: Marking = INITIAL_MARKING
    step = 0
    while not is_final(model, marking):
        live = enabled(model, marking)
        if not live:
            # Structurally stalled with nothing enabled and not final --
            # nothing left this replay can lawfully do; stop rather than loop.
            break
        chosen: NodePath = sorted(live)[0]
        node = _node_at(model, chosen)
        label = node.label if isinstance(node, Atom) else f"path:{chosen}"

        marking = fire(model, marking, chosen)
        step += 1

        node_object_id = f"{session_id}-node-{'.'.join(map(str, chosen))}"
        outcome: dict[str, Any] = {
            "standing": "FIRED",
            "detail": label,
            "steps_taken": step,
        }

        binding = action_bindings.get(label) if action_bindings else None
        if binding is not None and isinstance(node, Atom):
            atom_attrs = {
                "label": node.label,
                "action": node.action,
                "bindings": dict(node.bindings),
            }
            try:
                if binding_timeout_s is None:
                    action_result = binding(atom_attrs)
                else:
                    # Not a `with` block deliberately: `ThreadPoolExecutor
                    # .__exit__` calls `shutdown(wait=True)`, which would
                    # block on the very hung thread this timeout exists to
                    # bound past. `shutdown(wait=False, ...)` on the
                    # timeout path lets this replay return without waiting
                    # for a thread that may never finish (see
                    # `ActionBindingTimeout`'s docstring).
                    pool = ThreadPoolExecutor(max_workers=1)
                    future = pool.submit(binding, atom_attrs)
                    try:
                        action_result = future.result(timeout=binding_timeout_s)
                    except FutureTimeoutError:
                        pool.shutdown(wait=False, cancel_futures=True)
                        raise ActionBindingTimeout(
                            f"binding for label {label!r} did not return "
                            f"within {binding_timeout_s}s"
                        ) from None
                    else:
                        pool.shutdown(wait=False)
            except Exception as exc:  # noqa: BLE001 -- recorded honestly, then re-raised
                recorder.record(
                    activity="powl_action_binding_error",
                    objects=[(node_object_id, "PowlNode")],
                    outcome={
                        "standing": "ERROR",
                        "detail": label,
                        "steps_taken": step,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                # The recorder's log never reaches this function's own
                # return value on this path (the exception propagates
                # instead), so without this the caller has no way to reach
                # the just-recorded error event's real detail. Attach the
                # partial (not-yet-validated) log so a caller can still
                # inspect what was recorded before the halt.
                exc.ocel_partial_log = recorder.log  # type: ignore[attr-defined]
                raise
            outcome["action_result"] = action_result

        recorder.record(
            activity="powl_structural_fire",
            objects=[(node_object_id, "PowlNode")],
            outcome=outcome,
        )

    return recorder.close()


def _node_at(model: PowlNode, path: NodePath) -> PowlNode:
    from autofde_lab.powl.executor import node_at

    return node_at(model, path)
