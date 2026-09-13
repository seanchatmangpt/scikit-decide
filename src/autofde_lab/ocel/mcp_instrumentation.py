# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Automatic object-centric event logging for MCP tool calls.

Instruments a set of tool functions -- one call site, at server construction
-- so every real call becomes a real OCEL 2.0 event, without touching the
tool bodies themselves or the ``fastmcp`` library. Built on top of
:mod:`autofde_lab.ocel.mcp_session` (:func:`append_tool_call_event`), which
already carries the OCPQ Definition 2 discipline this repo's OCEL module
follows (Kusters & van der Aalst, 2025, "OCPQ: Object-Centric Process
Querying & Constraints", arXiv:2506.11541 -- see
:mod:`autofde_lab.ocel.log`'s module docstring and :meth:`OcelLog.validate`
for the exact laws every event in this module's output obeys).

Two design choices, stated because each rejects a plausible alternative:

1. **A decorator, not a metaclass.** :class:`~fastmcp.FastMCP` tools are
   plain functions passed through one choke point -- ``server.tool`` -- not
   instances of many subclasses whose *construction* needs intercepting.
   Wrapping the function at registration time is the minimal correct hook;
   a metaclass would solve a problem this codebase's shape does not have.

2. **A point-event model, not a lifecycle (start/complete) model.** OCEL 2.0
   -- unlike XES's optional lifecycle extension -- has no notion of a
   ``start``/``complete`` transition pair for one occurrence; an event is a
   single timestamped fact. Recording *only* the completion (with an
   ``elapsed_s`` attribute carrying the duration) is therefore the
   spec-faithful projection of "this tool call happened," not a simplification
   of a richer model this format does not have. A tool that never returns
   (killed by an outer timeout) correctly produces no event at all -- absence
   of evidence, not fabricated evidence of an unobserved completion.

``OcelSessionRecorder`` exists because :class:`~autofde_lab.ocel.log.OcelLog`
is immutable (:meth:`OcelLog.append_event` returns a *new* log) -- a mutable
holder is the seam between that functional data structure and instrumented
functions that must accumulate state across independent calls. It also owns
object declaration: OCEL requires every event's linked objects to already
exist in the log (:meth:`OcelLog.validate`'s ``DANGLING_EVENT_OBJECT_LINK``
law) and forbids declaring the same object id twice
(``DUPLICATE_ENTITY_ID``) -- so this class declares each object exactly once,
the first time it is referenced, rather than requiring the caller to
pre-enumerate every domain/solver name up front.
"""

from __future__ import annotations

import functools
import itertools
import time
import uuid
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeVar

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject

F = TypeVar("F", bound=Callable[..., Any])

__all__ = ["OcelSessionRecorder", "instrumented"]


class OcelSessionRecorder:
    """Accumulates one session's MCP tool calls into a valid OCEL 2.0 log.

    Not thread-safe (a single-writer accumulator over an immutable log, by
    design -- see module docstring); a concurrent server should hold one
    recorder per session, never share one across sessions.
    """

    def __init__(self, session_id: str, *, server_name: str = "scikit-decide-fabric") -> None:
        self._session_id = session_id
        self._declared_object_ids: set[str] = {session_id}
        self._event_counter = itertools.count()
        self._log = OcelLog.new().with_objects(
            OcelObject(
                session_id,
                "MCPSession",
                (OcelAttribute("server", OcelAttributeValue.string(server_name)),),
            )
        )

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def log(self) -> OcelLog:
        """The log as of the last recorded call. Not yet validated -- call
        :meth:`close` before trusting or persisting it."""
        return self._log

    def ensure_object(self, object_id: str, object_type: str) -> None:
        """Declare an object if this session has not already declared it.

        Idempotent by ``object_id``: a second call with the same id is a
        no-op, never a ``DUPLICATE_ENTITY_ID`` violation. A second call with
        the *same id and a different type* is not specially detected here --
        :meth:`OcelLog.validate` has no such check either, since OCPQ
        Definition 2 types objects by their single declared type at
        declaration time; giving one id two types is a caller defect this
        class does not try to paper over.
        """
        if object_id in self._declared_object_ids:
            return
        self._declared_object_ids.add(object_id)
        self._log = self._log.with_objects(OcelObject(object_id, object_type))

    def record(
        self,
        *,
        activity: str,
        objects: Iterable[tuple[str, str]],
        outcome: Mapping[str, Any],
    ) -> None:
        """Declare ``objects`` (id, type) as needed, then append one event
        linking the session object and all of them."""
        object_ids = [self._session_id]
        for object_id, object_type in objects:
            self.ensure_object(object_id, object_type)
            object_ids.append(object_id)

        event_id = f"evt-{activity}-{next(self._event_counter)}-{uuid.uuid4().hex[:8]}"
        self._log = append_tool_call_event(
            self._log,
            event_id=event_id,
            activity=activity,
            object_ids=object_ids,
            outcome=outcome,
        )

    def close(self) -> OcelLog:
        """Validate the accumulated log (OCPQ Definition 2's structural
        laws) and return it. Raises :class:`~autofde_lab.ocel.refusals.OcelError`
        on any violation -- a session that produced an invalid log is a bug
        in this module, not a result to hand back silently."""
        self._log = self._log.validate()
        return self._log


def instrumented(
    recorder: OcelSessionRecorder,
    *,
    activity: str,
    objects_fn: Callable[..., Sequence[tuple[str, str]]],
) -> Callable[[F], F]:
    """Wrap ``fn`` so every real call is recorded as a real OCEL event.

    ``objects_fn`` receives the same ``(*args, **kwargs)`` the wrapped
    function was called with and must return the ``(object_id, object_type)``
    pairs (excluding the session object, added automatically) this call's
    event should link to -- e.g. for ``decision_solve(request)``,
    ``lambda request: [(f"domain-{request['domain']}", "Domain"), (f"solver-{request['solver']}", "Solver")]``.

    A raised exception is recorded as a real ``standing: ERROR`` event
    (never silently dropped) and then re-raised unchanged -- instrumentation
    must never change what the caller observes, only what gets logged
    alongside it.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            started = time.monotonic()
            try:
                objects = objects_fn(*args, **kwargs)
            except Exception:
                objects = []
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 -- recorded, then re-raised unchanged
                recorder.record(
                    activity=activity,
                    objects=objects,
                    outcome={
                        "standing": "ERROR",
                        "elapsed_s": time.monotonic() - started,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                raise
            outcome = _outcome_from_result(result, time.monotonic() - started)
            recorder.record(activity=activity, objects=objects, outcome=outcome)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def _outcome_from_result(result: Any, elapsed_s: float) -> dict:
    """Derive an OCEL outcome dict from a tool's return value.

    Tool functions in this repo return plain JSON-compatible dicts
    (`DecisionResult.as_dict()`, `DecisionCatalog.as_dict()`, ...), most of
    which already carry a ``standing`` key (``SOLVED``/``BOUNDED``/``REFUSED``)
    -- reuse it verbatim rather than re-deriving a parallel classification.
    A result with no ``standing`` key (``decision_catalog``,
    ``decision_cache_stats``) is real, successful data with nothing to
    classify; recorded as ``COMPLETED`` rather than left unclassified.
    """
    outcome: dict[str, Any] = {"elapsed_s": elapsed_s}
    if isinstance(result, Mapping) and "standing" in result:
        outcome["standing"] = result["standing"]
    else:
        outcome["standing"] = "COMPLETED"
    if isinstance(result, Mapping):
        if "receipt_sha256" in result:
            outcome["receipt_sha256"] = result["receipt_sha256"]
        if isinstance(result.get("compatible_solvers"), (list, tuple)):
            outcome["compatible_solver_count"] = len(result["compatible_solvers"])
            # Named tuple, not just the count -- lets ocel/decision_mining.py ask
            # whether a domain's compatible-solver set is deterministic across
            # matches (the count alone can't distinguish "always these same 3
            # solvers" from "3 different solvers each time").
            outcome["compatible_solvers"] = sorted(str(s) for s in result["compatible_solvers"])
        if isinstance(result.get("steps"), (list, tuple)):
            outcome["steps"] = len(result["steps"])
    return outcome
