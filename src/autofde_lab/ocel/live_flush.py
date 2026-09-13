# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Record one real OCEL 2.0 event and flush the session log to SQLite in the
same call.

Exists because :func:`autofde_lab.ocel.mcp_instrumentation.instrumented`
wraps *synchronous* callables (a plain ``functools.wraps`` decorator around
``fn(*args, **kwargs)``) and cannot wrap an ``async def`` tool call without
either awaiting inside a decorator that was never built for that, or forcing
every caller through an async-aware rewrite of that module. The real driver
this function was built for --
``vendor/gyms/sregym/clients/autofde_lab_planner/driver.py``'s
``call_kubectl()``/``submit()`` -- calls a real ``fastmcp`` ``Client.call_tool``
via ``await``, so the record step happens inline in the caller's own async
function body instead of through a decorator.

The "flush on every call" design (rather than flushing once at the end) is
deliberate: :func:`autofde_lab.ocel.sqlite_store.to_sqlite` is a full
overwrite of a small per-problem log (tens of events for one SREGym trial),
cheap at this scale, and means the on-disk database is queryable *while the
trial is still running* -- real-time process intelligence, not a report
generated after the fact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder
from autofde_lab.ocel.sqlite_store import to_sqlite

__all__ = ["record_and_flush"]


def record_and_flush(
    recorder: OcelSessionRecorder,
    *,
    activity: str,
    objects: Iterable[tuple[str, str]],
    outcome: Mapping[str, Any],
    path: str | Path,
) -> None:
    """Append one event to ``recorder`` and immediately persist the whole
    session log to the SQLite database at ``path``.

    Not validated here (:meth:`OcelSessionRecorder.close` does that, once,
    at the end of the session) -- an intermediate flush mid-session is
    allowed to be a structurally-incomplete-but-honest snapshot (e.g. an
    object referenced by the most recent event, declared in the same
    ``record()`` call that added it, is always present by construction; there
    is no window where a flush observes a dangling reference).
    """
    recorder.record(activity=activity, objects=objects, outcome=outcome)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_sqlite(recorder.log, path)
