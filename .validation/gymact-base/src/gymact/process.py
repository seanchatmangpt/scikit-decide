"""Declared GymAct lifecycle as a real, hand-checkable transition table over
`gymact.models.Operation`, plus a real conformance checker that replays a real
episode's `Receipt.operation` sequence against it.

Scope note: `gymact.runtime.GymAct` already returns a `Receipt` (with a real
`operation: Operation` field) from every lifecycle call. This module does not
introduce a parallel event-log representation -- it operates directly on the
sequence of `Operation` values a caller has already collected from real
`Receipt`s, keeping one source of truth for "what happened."

This table covers 8 operations, not the 12 an earlier ontology-design pass
described (no `configure`/`reset`/`start`/`score` here) -- see
`gymact.models.Operation`'s docstring for why that's a deliberate Reduce,
not a gap.
"""

from __future__ import annotations

from pydantic import BaseModel

from gymact.models import Operation

# operation -> set of legal next operations. MATERIALIZE is the only legal
# start; OBSERVE/ACT/VERIFY are repeatable and may interleave; CHECKPOINT and
# RESTORE may occur between them; TEARDOWN is terminal.
LIFECYCLE: dict[Operation, set[Operation]] = {
    Operation.DISCOVER: {Operation.MATERIALIZE},
    Operation.MATERIALIZE: {
        Operation.OBSERVE,
        Operation.ACT,
        Operation.VERIFY,
        Operation.CHECKPOINT,
        Operation.TEARDOWN,
    },
    Operation.OBSERVE: {
        Operation.OBSERVE,
        Operation.ACT,
        Operation.VERIFY,
        Operation.CHECKPOINT,
        Operation.RESTORE,
        Operation.TEARDOWN,
    },
    Operation.ACT: {
        Operation.OBSERVE,
        Operation.ACT,
        Operation.VERIFY,
        Operation.CHECKPOINT,
        Operation.RESTORE,
        Operation.TEARDOWN,
    },
    Operation.VERIFY: {
        Operation.OBSERVE,
        Operation.ACT,
        Operation.VERIFY,
        Operation.CHECKPOINT,
        Operation.RESTORE,
        Operation.TEARDOWN,
    },
    Operation.CHECKPOINT: {
        Operation.OBSERVE,
        Operation.ACT,
        Operation.VERIFY,
        Operation.RESTORE,
        Operation.TEARDOWN,
    },
    Operation.RESTORE: {
        Operation.OBSERVE,
        Operation.ACT,
        Operation.VERIFY,
        Operation.CHECKPOINT,
        Operation.TEARDOWN,
    },
    Operation.TEARDOWN: set(),
}

# MATERIALIZE is the real lifecycle start (DISCOVER is registry inspection,
# not part of an episode's own trajectory).
START_OPERATION = Operation.MATERIALIZE


class Deviation(BaseModel):
    """A single named, evidenced conformance violation."""

    index: int
    from_operation: Operation | None
    to_operation: Operation
    reason: str


class ConformanceResult(BaseModel):
    """Real replay outcome: pass/fail with named evidence, not a fuzzy score."""

    conformant: bool
    deviations: list[Deviation] = []


class ConformanceChecker:
    """Replays a real episode's `Operation` sequence against `LIFECYCLE`."""

    def check(self, operations: list[Operation]) -> ConformanceResult:
        if not operations:
            return ConformanceResult(conformant=True, deviations=[])

        deviations: list[Deviation] = []

        first = operations[0]
        if first != START_OPERATION:
            deviations.append(
                Deviation(
                    index=0,
                    from_operation=None,
                    to_operation=first,
                    reason=f"episode must start with '{START_OPERATION}', got '{first}'",
                )
            )

        previous = first
        for i in range(1, len(operations)):
            current = operations[i]
            legal_next = LIFECYCLE.get(previous, set())
            if current not in legal_next:
                deviations.append(
                    Deviation(
                        index=i,
                        from_operation=previous,
                        to_operation=current,
                        reason=f"'{current}' is not a legal successor of "
                        f"'{previous}' (legal: {sorted(legal_next)})",
                    )
                )
            previous = current

        return ConformanceResult(conformant=not deviations, deviations=deviations)
