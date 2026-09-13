# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, LLM-free bridge: every real `guard_executor.execute()` call also
emits a real OCEL 2.0 log using this repo's own, existing OCEL machinery.

Closes the "planned POWL -> execution OCEL" half of the process-mining loop.
The other half -- process-mining/analysis over the resulting log -- is
explicitly out of scope here; this module only does the mechanical logging
step, no LLM call anywhere.

This module wraps :func:`autofde_lab.powl.guard_executor.execute`; it does
not modify it, and it changes nothing about what that function actually
does -- same guard evaluation, same atom invocation, same mandatory
``validate_model`` admission inside ``execute()`` (see that module's own
docstring). OCEL emission is purely additional, side-channel observation.

Reused, not reinvented, OCEL machinery
---------------------------------------
:class:`~autofde_lab.ocel.log.OcelLog` (``src/autofde_lab/ocel/log.py:140``)
is this repo's one real OCEL 2.0 working-log type -- the same immutable,
append-only, ``validate()``-checked log every other OCEL producer in this
repo uses (see ``src/autofde_lab/ocel/mcp_instrumentation.py``'s
``OcelSessionRecorder``, which wraps the identical log for MCP tool calls).
This module reuses that exact class rather than inventing a second,
competing OCEL representation, per this repo's no-dual-bookkeeping law.

Naming convention followed
---------------------------
``OcelSessionRecorder`` (``ocel/mcp_instrumentation.py:64-107``) declares one
top-level session/container object (there: ``"MCPSession"``) that every
event of that call also links to, and calls
``OcelLog.append_event(event_id, activity, objects, ...)`` per real
occurrence -- the exact pattern this module follows for the POWL execution
case: one ``"PowlExecution"`` container object per :func:`execute_with_ocel`
call (mirroring ``"MCPSession"``), one ``"PowlActivity"`` object per real
``Atom`` label encountered (mirroring how ``OcelSessionRecorder.record``'s
``objects_fn`` link to typed domain/solver objects such as ``"Domain"`` /
``"Solver"`` in ``fabric/mcp.py`` call sites), and one OCEL event per real
atom visited during the walk, each linking the execution object and the
activity object.

Failure is real and visible
----------------------------
If OCEL emission itself fails (e.g. the accumulated log fails
``OcelLog.validate()``), that raises -- it is never silently swallowed, and
it is never confused with the executor's own real
:class:`~autofde_lab.powl.guard_executor.ExecutionTrace` result: the trace
returned by :func:`execute_with_ocel` is always exactly the same object the
real ``atom_invoker``/``guard_evaluator`` walk produced, independent of
whatever OCEL side-observation succeeded or failed.
"""

from __future__ import annotations

import itertools
import uuid

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.powl.algebra import Atom, PowlNode
from autofde_lab.powl.guard_executor import (
    AtomInvoker,
    ExecutionContext,
    ExecutionStep,
    ExecutionTrace,
    GuardEvaluator,
)
from autofde_lab.powl.guard_executor import execute as _execute

__all__ = ["OcelExecutionRecorder", "execute_with_ocel"]

#: Object type for the one container object declared per execution call,
#: matching "MCPSession" in ocel/mcp_instrumentation.py:75-81's naming
#: convention (a singular, PascalCase, domain-specific container noun).
_EXECUTION_OBJECT_TYPE = "PowlExecution"

#: Object type for one real Atom label visited, matching the same
#: convention -- see module docstring.
_ACTIVITY_OBJECT_TYPE = "PowlActivity"

#: OCEL activity/event-type name for a real Atom visitation.
_ATOM_ACTIVITY = "AtomInvoked"


class OcelExecutionRecorder:
    """Accumulates one :func:`execute_with_ocel` call's real Atom visitations
    into a valid :class:`~autofde_lab.ocel.log.OcelLog`.

    Not thread-safe (single-writer accumulator over an immutable log, exactly
    like :class:`~autofde_lab.ocel.mcp_instrumentation.OcelSessionRecorder`,
    whose docstring names the same constraint) -- construct one recorder per
    :func:`execute_with_ocel` call, never share one across concurrent walks.

    A plain (not frozen) class, deliberately: unlike the immutable
    :class:`~autofde_lab.powl.algebra` node types, this is a real
    single-writer *accumulator* over an immutable :class:`OcelLog` -- the
    same shape :class:`~autofde_lab.ocel.mcp_instrumentation.OcelSessionRecorder`
    already uses, which is likewise a plain, mutable-holder class.
    """

    def __init__(self, execution_id: str | None = None) -> None:
        self.execution_id = execution_id or f"powl-exec-{uuid.uuid4().hex}"
        self._declared_activity_ids: set[str] = set()
        self._event_counter = itertools.count()
        self._log = OcelLog.new().with_objects(OcelObject(self.execution_id, _EXECUTION_OBJECT_TYPE))

    @property
    def log(self) -> OcelLog:
        """The log accumulated so far. Not yet re-validated -- see
        :meth:`close`."""
        return self._log

    def _ensure_activity_object(self, activity_id: str, label: str) -> None:
        if activity_id in self._declared_activity_ids:
            return
        self._declared_activity_ids.add(activity_id)
        self._log = self._log.with_objects(
            OcelObject(
                activity_id,
                _ACTIVITY_OBJECT_TYPE,
                (OcelAttribute("label", OcelAttributeValue.string(label)),),
            )
        )

    def record_atom(self, step: ExecutionStep, *, timestamp_ns: int) -> None:
        """Append one real OCEL event for one real ``Atom`` visitation.

        ``step.label`` and ``step.consequence`` are the real values recorded
        on ``step`` by :func:`autofde_lab.powl.guard_executor.execute`'s own
        walk -- never re-derived or guessed here.
        """
        if step.kind != "Atom":
            raise ValueError(f"record_atom requires an Atom step, got kind={step.kind!r}")
        label = step.label if step.label is not None else "<unlabeled>"
        activity_id = f"activity-{label}"
        self._ensure_activity_object(activity_id, label)

        event_id = f"evt-{_ATOM_ACTIVITY}-{next(self._event_counter)}-{uuid.uuid4().hex[:8]}"
        self._log = self._log.append_event(
            event_id,
            _ATOM_ACTIVITY,
            [self.execution_id, activity_id],
            timestamp_ns=timestamp_ns,
            attributes={
                "label": OcelAttributeValue.string(label),
                "consequence": OcelAttributeValue.string(step.consequence or ""),
            },
        )

    def close(self) -> OcelLog:
        """Validate (OCPQ Definition 2's structural laws, per
        :meth:`~autofde_lab.ocel.log.OcelLog.validate`) and return the
        accumulated log. Raises :class:`~autofde_lab.ocel.refusals.OcelError`
        on any violation -- never silently swallowed."""
        self._log = self._log.validate()
        return self._log


def execute_with_ocel(
    node: PowlNode,
    *,
    guard_evaluator: GuardEvaluator,
    atom_invoker: AtomInvoker,
    max_choice_transitions: int = 64,
    max_workers: int = 1,
    context: "ExecutionContext | None" = None,
    recorder: OcelExecutionRecorder,
) -> ExecutionTrace:
    """Wrap :func:`autofde_lab.powl.guard_executor.execute` so every real
    ``Atom`` visited during the walk also gets a real OCEL 2.0 event
    appended to ``recorder``.

    Structurally identical execution
    ---------------------------------
    This calls the real, unmodified ``execute()`` exactly once, with the
    exact same arguments a direct caller would pass -- same guard
    evaluation, same atom invocation, same mandatory ``validate_model``
    admission inside ``execute()``. The returned
    :class:`~autofde_lab.powl.guard_executor.ExecutionTrace` is exactly
    ``execute()``'s own return value, untouched. OCEL events are derived
    *after* the real walk completes, by replaying the trace's own
    already-recorded steps (never a second, parallel decision mechanism,
    and never able to alter what was actually invoked) -- this is why
    concurrent execution (``max_workers > 1``) is safe here: OCEL emission
    happens by replaying the final, already-synchronized ``trace.steps``,
    never by a live hook fired from inside concurrent worker threads.

    ``max_workers``/``context`` are forwarded to ``execute()`` unchanged
    (added so real concurrent callers, e.g.
    `reasoning.planner_federation_ensemble.federate_concurrently`, can gain
    real OCEL observation without losing their real concurrency -- a van
    der Aalst-style audit this session found several real, concurrent,
    `validate_model`-admitted POWL executions producing zero OCEL trace
    specifically because this function couldn't previously accept them).

    ``recorder`` must be a real, fresh-or-reused
    :class:`OcelExecutionRecorder`; its log is left in a real, appended (not
    yet re-validated) state after this call -- call
    :meth:`OcelExecutionRecorder.close` to validate.

    OCEL emission failure is real
    ------------------------------
    If appending or validating an event on ``recorder`` raises, that
    exception propagates to the caller unchanged -- it is never caught or
    downgraded to a log line, and it is raised only *after* the real
    execution has already completed, so a caller can distinguish "execution
    failed" from "execution succeeded but its OCEL observation failed."
    """
    trace = _execute(
        node,
        guard_evaluator=guard_evaluator,
        atom_invoker=atom_invoker,
        max_choice_transitions=max_choice_transitions,
        max_workers=max_workers,
        context=context,
    )

    timestamp_ns = 0
    for step in trace.steps:
        if step.kind != "Atom":
            continue
        recorder.record_atom(step, timestamp_ns=timestamp_ns)
        timestamp_ns += 1

    return trace
