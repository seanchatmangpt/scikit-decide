# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real token-replay conformance of a POWL 2.0 model against a real OCEL 2.0
event log -- the INTENDED/OBSERVED relation `.claude/rules/no-dual-bookkeeping.md`
requires as an explicit, typed edge, never inferred from either side alone.

What this answers
------------------
"Is this real, observed OCEL 2.0 activity sequence a legal trace of this real
POWL 2.0 model?" -- decided by literally replaying the observed sequence
through the model's own real executor (`enabled()`/`fire()`), the same
functions `run_pipeline` uses to drive the model forward. This is NOT a mined
Petri-net proxy (contrast `autofde_lab.ocel.level4_process_fitness`, which
scores a *different*, hand-authored intended model via a lossy,
concept-name-only ILP-mined Petri net) -- every step here is checked against
the real POWL v2 structure directly, so nothing is lost translating to a
surrogate representation.

Why this direction, and not the reverse
----------------------------------------
`ocel.powl_replay.replay_structural_fires` and `runner.run_pipeline` already
go POWL -> OCEL (forward simulation: drive the model, record what happened).
A log produced that way trivially conforms to the model that produced it --
proving nothing about a genuinely *independent* observed trace. This module
is the other direction, POWL x OCEL -> conformance verdict, for a log this
module did not itself produce (e.g. a real live SREGym trial's OCEL log) --
the actual conformance-checking relation `no-dual-bookkeeping.md` requires,
never derived from either side alone.

What "conforms" means here, precisely
--------------------------------------
Strict prefix replay: the observed sequence of `(activity, detail)` pairs
(read off each event's own real attributes, never re-derived from timing or
ordering) is walked in log order. At each step, the current real `Marking`'s
`enabled()` set is consulted; if any enabled path's node carries the observed
label, the lexicographically-smallest such path is fired (deterministic
tie-break made explicit here, in the conformance checker -- never inside
`executor.py`, whose own law is "the executor never chooses"). The first
observed label with NO matching enabled path is the exact point of
divergence, reported by index and label, not just a boolean.

This is strict: it does not attempt alignment-based approximate conformance
(inserting/skipping observed events to find a better-fitting path) the way a
full alpha/ETConformance implementation would. A real divergence is reported
honestly as a divergence, never silently repaired into a fit."""

from __future__ import annotations

from dataclasses import dataclass

from autofde_lab.ocel.model import OcelEvent
from autofde_lab.powl.algebra import Atom, PowlNode
from autofde_lab.powl.bounds import DEFAULT_BOUND, ExecutionBound
from autofde_lab.powl.executor import INITIAL_MARKING, Marking, enabled, fire, is_final, node_at

__all__ = ["ConformanceResult", "check_ocel_conformance", "observed_labels_from_events"]

_FIRE_ACTIVITIES = frozenset({"powl_structural_fire", "powl_action_binding_error"})


def observed_labels_from_events(events: tuple[OcelEvent, ...]) -> tuple[str, ...]:
    """Real, direct extraction of the observed structural-fire label
    sequence from real OCEL events -- reads each event's own `detail`
    attribute (the same field `runner.run_pipeline` and
    `ocel.powl_replay.replay_structural_fires` both write with the real
    fired Atom's label / `path:...` marker), in the log's own event order.
    Non-fire activities (anything outside `_FIRE_ACTIVITIES`) are skipped,
    never coerced into a fire this module did not actually observe."""
    labels: list[str] = []
    for event in events:
        if event.activity not in _FIRE_ACTIVITIES:
            continue
        detail = next(
            (a.value.value for a in event.attributes if a.key == "detail"), None
        )
        if detail is None:
            continue
        labels.append(str(detail))
    return tuple(labels)


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    """The real, typed verdict -- never a bare boolean. `conforms` is true
    only when every observed label was matched to a real enabled path AND
    the model reached a real final marking after the last observed fire."""

    conforms: bool
    fired_count: int
    observed_count: int
    final: bool
    divergence_index: int | None
    divergence_label: str | None
    divergence_enabled_labels: tuple[str, ...] | None


def _label_of(node: PowlNode, path) -> str:
    return node.label if isinstance(node, Atom) else f"path:{path}"


def check_ocel_conformance(
    model: PowlNode,
    events: tuple[OcelEvent, ...],
    *,
    bound: ExecutionBound = DEFAULT_BOUND,
) -> ConformanceResult:
    """Real token-replay: walk `observed_labels_from_events(events)` against
    `model`'s own real `enabled()`/`fire()`, starting from `INITIAL_MARKING`.
    Never mutates `events`; never re-derives observed order from anything
    but the events' own real, given order."""
    observed = observed_labels_from_events(events)
    marking: Marking = INITIAL_MARKING
    fired_count = 0

    for index, label in enumerate(observed):
        live = enabled(model, marking, bound)
        candidates = sorted(
            path for path in live if _label_of(node_at(model, path), path) == label
        )
        if not candidates:
            enabled_labels = tuple(
                sorted(_label_of(node_at(model, path), path) for path in live)
            )
            return ConformanceResult(
                conforms=False,
                fired_count=fired_count,
                observed_count=len(observed),
                final=False,
                divergence_index=index,
                divergence_label=label,
                divergence_enabled_labels=enabled_labels,
            )
        chosen = candidates[0]
        marking = fire(model, marking, chosen, bound=bound)
        fired_count += 1

    final = is_final(model, marking)
    return ConformanceResult(
        conforms=final,
        fired_count=fired_count,
        observed_count=len(observed),
        final=final,
        divergence_index=None if final else len(observed),
        divergence_label=None,
        divergence_enabled_labels=None,
    )
