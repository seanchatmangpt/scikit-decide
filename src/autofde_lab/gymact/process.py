"""The declared GymAct lifecycle as a real, hand-checkable transition table.

Per the ERRC cut: no pm4py/Petri-net dependency for v1. The lifecycle is exactly
the one already named in this session's design:

    discover -> materialize -> configure -> reset -> start
             -> observe <-> act (repeatable)
             -> verify -> score -> teardown

`ConformanceChecker.check` replays a real ordered list of `KernelEvent`s for one
episode against this table and reports the first illegal transition, if any --
behavioral conformance, distinct from (and complementary to) SHACL's structural
shape-checking.
"""

from __future__ import annotations

from pydantic import BaseModel

from autofde_lab.gymact.models import KernelEvent

# activity -> set of legal next activities
LIFECYCLE: dict[str, set[str]] = {
    "discover": {"materialize"},
    "materialize": {"configure"},
    "configure": {"reset"},
    "reset": {"start"},
    "start": {"observe"},
    "observe": {"act", "verify"},
    "act": {"observe", "verify"},
    "verify": {"score"},
    "score": {"teardown"},
    "teardown": set(),
}

START_ACTIVITY = "discover"


class Deviation(BaseModel):
    """A single named, evidenced conformance violation."""

    index: int
    from_activity: str | None
    to_activity: str
    reason: str


class ConformanceResult(BaseModel):
    """Real replay outcome: pass/fail with named evidence, not a fuzzy score."""

    conformant: bool
    deviations: list[Deviation] = []


class ConformanceChecker:
    """Replays a real episode's event trace against `LIFECYCLE`."""

    def check(self, events: list[KernelEvent]) -> ConformanceResult:
        if not events:
            return ConformanceResult(conformant=True, deviations=[])

        deviations: list[Deviation] = []

        first = events[0]
        if first.activity != START_ACTIVITY:
            deviations.append(
                Deviation(
                    index=0,
                    from_activity=None,
                    to_activity=first.activity,
                    reason=f"episode must start with '{START_ACTIVITY}', "
                    f"got '{first.activity}'",
                )
            )

        previous = first
        for i in range(1, len(events)):
            current = events[i]
            legal_next = LIFECYCLE.get(previous.activity, set())
            if current.activity not in legal_next:
                deviations.append(
                    Deviation(
                        index=i,
                        from_activity=previous.activity,
                        to_activity=current.activity,
                        reason=f"'{current.activity}' is not a legal successor "
                        f"of '{previous.activity}' (legal: {sorted(legal_next)})",
                    )
                )
            previous = current

        return ConformanceResult(conformant=not deviations, deviations=deviations)
