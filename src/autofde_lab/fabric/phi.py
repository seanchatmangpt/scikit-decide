# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""phi: Anomaly -> ProblemInstance, a closed encoder table keyed by RelationClass.

`autofde_lab_planner.scanner.models.Anomaly` is the uniform shape every
ObjectKindAnalyzer emits (see that module's docstring: same dataclass
regardless of K8s `kind` or `relation_class`). This module is the other half
of the admission boundary: it turns one `Anomaly` into a real, instantiated
scikit-decide domain object that a solver can actually call `solve()` on --
never a synthetic/mock domain, per `.claude/rules/testing-chicago-style.md`.

The table is closed and enumerable: exactly the four `RelationClass` values
declared in `autofde_lab_planner.scanner.models` are handled, each mapped to
a real, already-existing domain-primitive constructor in this repo (no new
domain types invented here):

- ``declared_vs_observed``   -> a small `DeterministicPlanningDomain` in the
  style of `tests/domains/test_graph_domain.py`'s `ChainDomain` (two-state
  reconciliation domain: observed -> declared).
- ``dangling_reference``     -> `GraphDomain`
  (`autofde_lab.hub.domain.graph_domain.GraphDomain.GraphDomain`), built from
  the anomaly's own object as a state with no path to any goal -- the
  domain-level encoding of "reference does not resolve".
- ``insufficient_capability`` -> `RCPSP`
  (`autofde_lab.hub.domain.rcpsp.rcpsp_sk.RCPSP`), one task whose resource
  requirement is the anomaly's observed demand against a resource whose
  capacity is the anomaly's expected/available amount.
- ``aggregate_threshold``    -> `RCPSP`, the resource-sum-vs-limit case: one
  task carrying the full aggregate demand against the threshold capacity.

Per `.claude/rules/absence-is-not-evidence.md`, a `RelationClass` this table
does not know how to encode is never silently dropped or guessed at -- `phi`
raises `PhiUnrepresentable` (an explicit, typed, UNREPRESENTABLE result), and
that is also what happens if `expected`/`observed` cannot be parsed into the
numbers the target primitive requires.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from autofde_lab import D, DeterministicPlanningDomain, ImplicitSpace, Space, Value
from autofde_lab.hub.domain.graph_domain.GraphDomain import ActionSpace, GraphDomain
from autofde_lab.hub.domain.rcpsp.rcpsp_sk import RCPSP
from autofde_lab_planner.scanner.models import Anomaly, RelationClass

ProblemInstance = object
"""Alias for whatever real scikit-decide `Domain` subclass phi() returns.

Not a new type -- every value phi() actually produces is a real, importable
domain class already defined elsewhere in this repo (`ReconcileDomain`,
`GraphDomain`, `RCPSP`). This alias exists only for the encoder table's
signature; `Domain` itself is not imported here to avoid overclaiming a
type hierarchy phi()'s outputs don't share beyond "real scikit-decide
domain".
"""


@dataclass(frozen=True, slots=True)
class PhiUnrepresentable:
    """Explicit UNREPRESENTABLE result. Never raised silently, never dropped.

    Per `.claude/rules/absence-is-not-evidence.md`: when a `RelationClass`
    (or an `Anomaly`'s `observed`/`expected` payload) cannot be projected
    into a real domain-primitive constructor, phi() returns this typed
    value instead of guessing, defaulting, or coercing.
    """

    relation_class: RelationClass | str
    reason: str


class PhiUnrepresentableError(ValueError):
    """Raised by phi() when the encoder table has no lawful mapping.

    Carries the same `PhiUnrepresentable` payload as its `.result` attribute
    so callers that want the typed value instead of an exception can catch
    this and read `.result` rather than parsing the message string.
    """

    def __init__(self, result: PhiUnrepresentable):
        self.result = result
        super().__init__(f"UNREPRESENTABLE:{result.relation_class}:{result.reason}")


def _extract_number(text: str | None) -> float | None:
    """Pull the first integer/float literal out of a free-text field.

    `Anomaly.observed`/`.expected` are free-text (`detail` is explicitly
    documented as human-readable), so this is a best-effort parse, not a
    guarantee -- callers must treat a `None` return as UNREPRESENTABLE, not
    as "zero". A malformed `Anomaly` whose `observed`/`expected` is not
    `str | None` at all (e.g. an `int`, a corrupted record) is treated the
    same way -- `re.search` would raise `TypeError` on a non-`str`/`bytes`
    argument, and that is not this function's job to surface; the caller's
    `None`-is-UNREPRESENTABLE contract already covers it.
    """
    if text is None:
        return None
    if not isinstance(text, str):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match is None:
        return None
    return float(match.group(0))


def _field(anomaly: Anomaly, name: str, relation_class: "RelationClass | str"):
    """Read one declared field off `anomaly`, never leaking a raw `AttributeError`.

    Used only to read the `Anomaly`'s own fields *before* any domain
    constructor runs -- never wrapped around a constructor call. That
    placement is what keeps this narrow: a missing/malformed field on the
    `Anomaly` itself becomes a typed `PhiUnrepresentableError` named at the
    `phi()` boundary (case 2), while an unrelated failure raised from
    *inside* `ReconcileDomain`/`GraphDomain`/`RCPSP`'s own constructor is
    never caught here and propagates as itself -- so it can never be
    mislabeled UNREPRESENTABLE for a reason that has nothing to do with
    representability (case 4).
    """
    try:
        return getattr(anomaly, name)
    except AttributeError as exc:
        raise PhiUnrepresentableError(
            PhiUnrepresentable(
                relation_class=relation_class,
                reason=f"anomaly is missing required field {name!r} ({exc})",
            )
        ) from exc


class ReconcileDomain(DeterministicPlanningDomain):
    """Two-state deterministic domain: observed -> declared, via `reconcile`.

    Built in the same style as `tests/domains/test_graph_domain.py`'s
    `ChainDomain` template: a hand-written `DeterministicPlanningDomain`
    subclass with an explicit finite transition table, used here to encode
    a `declared_vs_observed` anomaly as "one action closes the gap between
    what the cluster declares and what the scanner observed".
    """

    def __init__(self, observed_state: str, declared_state: str):
        self.observed_state = observed_state
        self.declared_state = declared_state
        self.transitions = {observed_state: {"reconcile": declared_state}}

    def _get_next_state(self, memory, event):
        return self.transitions[memory][event]

    def _get_transition_value(self, memory, event, next_state=None):
        return Value(cost=1.0)

    def _is_terminal(self, state):
        return state == self.declared_state

    def _get_action_space_(self) -> Space[D.T_event]:
        return ImplicitSpace(lambda x: True)

    def _get_applicable_actions_from(self, memory):
        return ActionSpace(list(self.transitions.get(memory, {}).keys()))

    def _get_goals_(self):
        return ImplicitSpace(lambda x: x == self.declared_state)

    def _get_initial_state_(self):
        return self.observed_state

    def _get_observation_space_(self):
        return ImplicitSpace(lambda x: True)


def _encode_declared_vs_observed(anomaly: Anomaly) -> ReconcileDomain:
    relation_class = anomaly.relation_class
    namespace = _field(anomaly, "namespace", relation_class)
    object_name = _field(anomaly, "object_name", relation_class)
    observed = _field(anomaly, "observed", relation_class)
    expected = _field(anomaly, "expected", relation_class)
    if expected is None:
        raise PhiUnrepresentableError(
            PhiUnrepresentable(
                relation_class=relation_class,
                reason="declared_vs_observed anomaly has no `expected` value "
                "to reconcile toward",
            )
        )
    observed_state = f"{namespace}/{object_name}:{observed}"
    declared_state = f"{namespace}/{object_name}:{expected}"
    return ReconcileDomain(observed_state=observed_state, declared_state=declared_state)


def _encode_dangling_reference(anomaly: Anomaly) -> GraphDomain:
    namespace = _field(anomaly, "namespace", anomaly.relation_class)
    object_name = _field(anomaly, "object_name", anomaly.relation_class)
    dangling_state = f"{namespace}/{object_name}"
    # A dangling reference is, at the domain level, a state with no outgoing
    # edge to any goal: the referenced target does not exist to transition
    # into. next_state_map carries the state with zero actions, and targets
    # is deliberately empty -- there is no reachable goal state, which is
    # exactly what "dangling" means.
    next_state_map: dict[str, dict[str, str]] = {dangling_state: {}}
    next_state_attributes: dict[str, dict[str, dict[str, float]]] = {
        dangling_state: {}
    }
    return GraphDomain(
        next_state_map=next_state_map,
        next_state_attributes=next_state_attributes,
        targets=set(),
    )


def _encode_insufficient_capability(anomaly: Anomaly) -> RCPSP:
    relation_class = anomaly.relation_class
    observed = _field(anomaly, "observed", relation_class)
    expected = _field(anomaly, "expected", relation_class)
    field = _field(anomaly, "field", relation_class)
    demand = _extract_number(observed)
    capacity = _extract_number(expected)
    if demand is None or capacity is None:
        raise PhiUnrepresentableError(
            PhiUnrepresentable(
                relation_class=relation_class,
                reason="insufficient_capability requires a numeric `observed` "
                f"demand and `expected` capacity (got observed={observed!r}, "
                f"expected={expected!r})",
            )
        )
    resource_name = field or "capacity"
    task_id = 1
    tasks_mode = {task_id: {1: {"duration": 1, resource_name: int(demand)}}}
    return RCPSP(
        tasks_mode=tasks_mode,
        max_horizon=1,
        successors={task_id: []},
        resource_names=[resource_name],
        resource_availability={resource_name: int(capacity)},
        resource_renewable={resource_name: True},
    )


def _encode_aggregate_threshold(anomaly: Anomaly) -> RCPSP:
    relation_class = anomaly.relation_class
    observed = _field(anomaly, "observed", relation_class)
    expected = _field(anomaly, "expected", relation_class)
    field = _field(anomaly, "field", relation_class)
    aggregate_demand = _extract_number(observed)
    threshold = _extract_number(expected)
    if aggregate_demand is None or threshold is None:
        raise PhiUnrepresentableError(
            PhiUnrepresentable(
                relation_class=relation_class,
                reason="aggregate_threshold requires a numeric `observed` "
                "aggregate and `expected` threshold (got observed="
                f"{observed!r}, expected={expected!r})",
            )
        )
    resource_name = field or "aggregate"
    # The aggregate case is encoded as a single task carrying the full
    # already-summed demand against the threshold capacity -- the RCPSP
    # resource-sum-vs-limit primitive `CLAUDE.md`'s task description points
    # at, without inventing a multi-task decomposition the scanner's Anomaly
    # (a single flat record) doesn't actually give us the data to construct.
    task_id = 1
    tasks_mode = {task_id: {1: {"duration": 1, resource_name: int(aggregate_demand)}}}
    return RCPSP(
        tasks_mode=tasks_mode,
        max_horizon=1,
        successors={task_id: []},
        resource_names=[resource_name],
        resource_availability={resource_name: int(threshold)},
        resource_renewable={resource_name: True},
    )


_ENCODERS: dict[RelationClass, Callable[[Anomaly], ProblemInstance]] = {
    "declared_vs_observed": _encode_declared_vs_observed,
    "dangling_reference": _encode_dangling_reference,
    "insufficient_capability": _encode_insufficient_capability,
    "aggregate_threshold": _encode_aggregate_threshold,
}
"""The closed encoder table. Exactly the four `RelationClass` literals.

Enumerable by construction: `set(_ENCODERS) == set(RelationClass.__args__)`
is asserted by `tests/fabric/test_phi_chicago.py` so the table can never
silently drift out of sync with the scanner's own `RelationClass` Literal.
"""


def phi(anomaly: Anomaly) -> ProblemInstance:
    """Encode one scanner `Anomaly` into a real, instantiated domain object.

    Raises `PhiUnrepresentableError` (carrying a `PhiUnrepresentable` typed
    result on `.result`) when `anomaly.relation_class` has no entry in the
    closed encoder table, when `anomaly` is itself so malformed that even
    `.relation_class` cannot be read (a corrupted/duck-typed object missing
    the attribute entirely), or when the anomaly's other fields cannot be
    read or parsed into what the matched domain primitive requires. Never
    returns a placeholder or guessed domain in any of these cases.
    """
    try:
        relation_class = anomaly.relation_class
    except AttributeError as exc:
        raise PhiUnrepresentableError(
            PhiUnrepresentable(
                relation_class="<unreadable>",
                reason=f"malformed anomaly: `.relation_class` is unreadable ({exc})",
            )
        ) from exc

    encoder = _ENCODERS.get(relation_class)
    if encoder is None:
        raise PhiUnrepresentableError(
            PhiUnrepresentable(
                relation_class=relation_class,
                reason=f"no encoder registered for relation_class "
                f"{relation_class!r}; closed table only covers "
                f"{sorted(_ENCODERS)}",
            )
        )
    return encoder(anomaly)
