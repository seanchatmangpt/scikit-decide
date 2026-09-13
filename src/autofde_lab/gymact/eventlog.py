"""Real, in-memory, flat OCEL-shaped event log.

No external event-store dependency -- a real Python list backing real appends and
real reads, sufficient for the ERRC-scoped v1 (single object type: episode).

Kept as a real local shim, not replaced by the real `gymact` package's own
OCEL machinery (`gymact.ocel.receipts_to_ocel`, `gymact.kernel.GymAct.
episode_ocel_log`): that machinery builds its log from a list of real
`gymact.models.Receipt` objects, each carrying a real `Operation` enum value
-- and that enum has only 8 members (no `configure`/`reset`/`start`/`score`,
see `gymact.models.Operation`'s own docstring for why). This wrapper's
`GymActKernel` runs a 12-activity lifecycle (`kernel.OPERATIONS`), so
`EventLog` stays the log of record for `process.ConformanceChecker`'s replay.
For the 8 activities that do map onto a real `gymact.models.Operation`,
`GymActKernel` separately obtains a real `gymact.models.Receipt` from
`gymact.runtime.GymAct` and can additionally surface the real runtime's own
`episode_ocel_log(...)` for just that subset -- see
`GymActKernel.real_ocel_log`.
"""

from __future__ import annotations

from autofde_lab.gymact.models import KernelEvent


class EventLog:
    """Append-only log of `KernelEvent`s, ordered by insertion."""

    def __init__(self) -> None:
        self._events: list[KernelEvent] = []
        self._next_timestamp = 0

    def append(self, *, episode_id: str, activity: str, subject: str,
               attributes: dict | None = None) -> KernelEvent:
        event = KernelEvent(
            episode_id=episode_id,
            activity=activity,
            timestamp=self._next_timestamp,
            subject=subject,
            attributes=attributes or {},
        )
        self._next_timestamp += 1
        self._events.append(event)
        return event

    def events_for_episode(self, episode_id: str) -> list[KernelEvent]:
        return [e for e in self._events if e.episode_id == episode_id]

    def all_events(self) -> list[KernelEvent]:
        return list(self._events)
