# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real object-centric conformance checking over `OcelLog`.

Closes the exact gap `level4_process_fitness.py`'s own docstring names:

    "This measures activity-sequence fitness only... A trace can score
    perfectly while every object-identity join in it is dangling or
    crossed."

Classic (control-flow-only) conformance flattens a log to one global
activity sequence and replays it against a Petri net -- blind to *which*
object each event belongs to. This module instead projects the log **per
object** (via its real `event_object_links`) and checks each object's own
observed activity sequence against what that object was supposed to do --
the thing a flattened check cannot see, since a crossed link produces a
real, detectable gap in one object's projected trace and an unexpected
extra event in another's.

Pure Python, no external binary dependency (unlike the existing
`wasm4pm_bridge`/`level4_process_fitness` token-replay path, which shells
out to the real `wpm` binary) -- operates directly on `OcelLog`'s own real
tables. Fitness is normalized edit distance
(`1 - levenshtein(observed, intended) / max(len(observed), len(intended))`),
computed via a small, real, hand-rolled DP implementation -- no new
dependency, matching `level4_process_fitness.py`'s own choice not to add a
mining-library dependency for this kind of check.

Identity is explicit or it does not exist (`.claude/rules/no-dual-bookkeeping.md`):
`intended_traces_by_object_id` is keyed by real object id, never inferred
from `object_type` alone -- two objects of the same type can have
different intended traces, and this module never assumes otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from autofde_lab.ocel.log import OcelLog

__all__ = [
    "ObjectTraceFitness",
    "ObjectCentricConformanceResult",
    "project_object_trace",
    "flattened_trace",
    "check_object_centric_conformance",
]


def _levenshtein(a: Sequence[str], b: Sequence[str]) -> int:
    """Real, hand-rolled edit distance -- stdlib-only, no new dependency."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _fitness(observed: Sequence[str], intended: Sequence[str]) -> float:
    if not observed and not intended:
        return 1.0
    distance = _levenshtein(observed, intended)
    denom = max(len(observed), len(intended))
    return 1.0 - (distance / denom if denom else 0.0)


@dataclass(frozen=True, slots=True)
class ObjectTraceFitness:
    object_id: str
    object_type: str
    intended_trace: tuple[str, ...]
    observed_trace: tuple[str, ...]
    fitness: float
    conforms: bool


@dataclass(frozen=True, slots=True)
class ObjectCentricConformanceResult:
    per_object: tuple[ObjectTraceFitness, ...]
    overall_fitness: float
    all_conform: bool


def _event_label(event) -> str:
    """The real, specific activity label for an event.

    `OcelExecutionRecorder.record_atom` (`powl/ocel_bridge.py`) stores the
    specific `Atom` label as a real event *attribute* named `"label"`,
    while `event.activity` itself is the generic OCEL event-type name
    (`"AtomInvoked"` for every atom) -- using `event.activity` alone would
    make every event indistinguishable and silently defeat this module's
    entire purpose. Falls back to `event.activity` for events genuinely
    produced by another OCEL producer with no `"label"` attribute, rather
    than raising -- this module must work over any real `OcelLog`, not
    only ones `execute_with_ocel` produced."""
    for attr in event.attributes:
        if attr.key == "label":
            return str(attr.value.value)
    return event.activity


def project_object_trace(log: OcelLog, object_id: str) -> tuple[str, ...]:
    """Real projection: every event linked to `object_id` via a real
    `EventObjectLink`, sorted by `timestamp_ns` (ties broken by event id
    for determinism), mapped to its real, specific activity label -- the
    per-object control-flow view a flattened check cannot produce."""
    linked_event_ids = {link.event_id for link in log.event_object_links if link.object_id == object_id}
    events = [e for e in log.events if e.id in linked_event_ids]
    events.sort(key=lambda e: (e.timestamp_ns, e.id))
    return tuple(_event_label(e) for e in events)


def flattened_trace(log: OcelLog) -> tuple[str, ...]:
    """The classic, object-blind global sequence -- every real event in
    the log, sorted by timestamp/id, ignoring which object(s) it touched.
    Exposed so a caller can demonstrate, concretely, that a flattened
    check misses what `check_object_centric_conformance` catches (see
    this module's own test suite)."""
    events = sorted(log.events, key=lambda e: (e.timestamp_ns, e.id))
    return tuple(_event_label(e) for e in events)


def check_object_centric_conformance(
    log: OcelLog,
    *,
    intended_traces_by_object_id: Mapping[str, Sequence[str]],
) -> ObjectCentricConformanceResult:
    """For each `object_id` in `intended_traces_by_object_id` (explicit,
    caller-supplied identity), project its real observed trace and score
    it against the intended one. An `object_id` absent from the log's real
    objects is a real error, never silently 0.0."""
    known_object_ids = {obj.id: obj.object_type for obj in log.objects}

    per_object: list[ObjectTraceFitness] = []
    for object_id, intended in intended_traces_by_object_id.items():
        if object_id not in known_object_ids:
            raise KeyError(f"object_id {object_id!r} is not a real object declared in this OcelLog")

        observed = project_object_trace(log, object_id)
        intended_tuple = tuple(intended)
        fitness = _fitness(observed, intended_tuple)
        per_object.append(
            ObjectTraceFitness(
                object_id=object_id,
                object_type=known_object_ids[object_id],
                intended_trace=intended_tuple,
                observed_trace=observed,
                fitness=fitness,
                conforms=(fitness == 1.0),
            )
        )

    overall_fitness = sum(o.fitness for o in per_object) / len(per_object) if per_object else 0.0
    all_conform = bool(per_object) and all(o.conforms for o in per_object)

    return ObjectCentricConformanceResult(
        per_object=tuple(per_object),
        overall_fitness=overall_fitness,
        all_conform=all_conform,
    )
