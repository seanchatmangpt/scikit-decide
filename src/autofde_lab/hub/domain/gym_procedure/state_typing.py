# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typed state dimensions for discovered models.

The real GymAct bridge surfaced a state shape the earlier discrete
fact-set IR could not honestly hold: `CubeCounterProvider.observe()`
returns `{"counter": int, "target": int, "reward": float, "solved": bool}`
-- a continuous `reward`, two integers, and a boolean. Coercing all of
that into `frozenset[str]` facts (``"reward=0.16666666666666666"``) is
lossy in a way that silently invents distinct "facts" for every float
value and destroys ordering/metric structure.

So: classify every observed dimension, keep the rich observation in the
discovered model, and let each *projection* decide what it can represent.
A projection that cannot represent a dimension returns
``UNREPRESENTABLE:<reason>`` rather than silently erasing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DimensionKind(str, Enum):
    BOOLEAN = "BOOLEAN"
    CATEGORICAL = "CATEGORICAL"
    CATEGORICAL_ID = "CATEGORICAL_ID"
    INTEGER = "INTEGER"
    CONTINUOUS = "CONTINUOUS"
    OBJECT_VALUED = "OBJECT_VALUED"
    UNKNOWN = "UNKNOWN"


#: An INTEGER dimension is re-classified CATEGORICAL_ID when it carries a
#: NEGATIVE SENTINEL over a small label set. `lock_and_key`'s `held_key` is
#: exactly that: -1 means "holding nothing", 0/1/2 name distinct keys.
#:
#: Arithmetic on such a dimension is a category error of the same family
#: this module exists to catch one level down. Measured: probing
#: `pick_key[key=2]` from the empty hand observed -1 -> 2 and the delta
#: induction learned `held_key: +3`, so the model believed picking that key
#: twice would leave key 5 in hand. Absolute effects are the only sound
#: reading of an identity.
#:
#: The discriminator is deliberately narrow -- a negative value must have
#: been really observed. `counter`, `raw`, `output`, `locks_open` are all
#: small integer dimensions too and none of them is ever negative, so none
#: is caught by this rule and none loses its delta semantics.
CATEGORICAL_ID_MAX_LABELS = 8


@dataclass(frozen=True)
class StateDimension:
    name: str
    kind: DimensionKind
    observed_values: tuple[Any, ...] = ()

    def is_metric(self) -> bool:
        """True when ordering/arithmetic on this dimension is meaningful.

        CATEGORICAL_ID is deliberately NOT metric even though its values are
        integers -- a key identity has no arithmetic.
        """
        return self.kind in (DimensionKind.INTEGER, DimensionKind.CONTINUOUS)


def classify_value(value: Any) -> DimensionKind:
    # bool before int: bool is a subclass of int in Python, and treating
    # `solved=True` as an integer dimension would be a real modelling error.
    if isinstance(value, bool):
        return DimensionKind.BOOLEAN
    if isinstance(value, int):
        return DimensionKind.INTEGER
    if isinstance(value, float):
        return DimensionKind.CONTINUOUS
    if isinstance(value, str):
        return DimensionKind.CATEGORICAL
    if isinstance(value, (dict, list, tuple, set)):
        return DimensionKind.OBJECT_VALUED
    if value is None:
        return DimensionKind.UNKNOWN
    return DimensionKind.UNKNOWN


def classify_observation(
    observations: list[dict[str, Any]],
) -> dict[str, StateDimension]:
    """Classify every dimension seen across one or more real observations.

    A dimension observed with conflicting kinds across samples (e.g. int
    then str) is recorded UNKNOWN rather than being forced into whichever
    kind happened to appear first -- an honest "we do not yet know the
    type" beats a confident wrong one.
    """
    seen: dict[str, list[Any]] = {}
    for obs in observations:
        for k, v in obs.items():
            seen.setdefault(k, []).append(v)

    dims: dict[str, StateDimension] = {}
    for name, values in seen.items():
        kinds = {classify_value(v) for v in values}
        # An INTEGER dimension that later shows a float is really CONTINUOUS;
        # that widening is a real generalization, not a conflict.
        if kinds == {DimensionKind.INTEGER, DimensionKind.CONTINUOUS}:
            kind = DimensionKind.CONTINUOUS
        elif len(kinds) == 1:
            kind = next(iter(kinds))
        else:
            kind = DimensionKind.UNKNOWN
        if kind is DimensionKind.INTEGER and _is_categorical_id(values):
            kind = DimensionKind.CATEGORICAL_ID
        dims[name] = StateDimension(name=name, kind=kind, observed_values=tuple(values))
    return dims


def _is_categorical_id(values: list[Any]) -> bool:
    """A small integer label set carrying a negative sentinel. See
    `CATEGORICAL_ID_MAX_LABELS` for why the test is this narrow."""
    ints = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
    if len(ints) != len(values) or not ints:
        return False
    distinct = set(ints)
    return len(distinct) <= CATEGORICAL_ID_MAX_LABELS and min(distinct) < 0


@dataclass(frozen=True)
class ProjectionResult:
    """Either a projected artifact, or a typed refusal naming what was lost."""

    representation: str
    artifact: Any = None
    unrepresentable_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.unrepresentable_reason is None

    @classmethod
    def unrepresentable(cls, representation: str, reason: str) -> ProjectionResult:
        return cls(
            representation=representation,
            artifact=None,
            unrepresentable_reason=f"UNREPRESENTABLE:{reason}",
        )


def propositionalize(
    observation: dict[str, Any], dims: dict[str, StateDimension]
) -> tuple[frozenset[str], dict[str, str]]:
    """Project a rich observation down to a boolean fact-set for STRIPS-like
    planners, returning BOTH the facts and a per-dimension record of what
    that projection cost.

    Boolean/categorical/integer dimensions propositionalize soundly
    (``solved=True``, ``counter=2``). Continuous dimensions do NOT --
    every distinct float becomes its own unrelated "fact", destroying the
    metric structure that made it continuous. Those are reported as
    UNREPRESENTABLE and excluded from the fact-set rather than silently
    inflating the state space with meaningless distinct atoms.
    """
    facts: set[str] = set()
    losses: dict[str, str] = {}
    for name, value in observation.items():
        dim = dims.get(name)
        kind = dim.kind if dim else classify_value(value)
        if kind in (
            DimensionKind.BOOLEAN,
            DimensionKind.CATEGORICAL,
            DimensionKind.CATEGORICAL_ID,
            DimensionKind.INTEGER,
        ):
            facts.add(f"{name}={value}")
        elif kind is DimensionKind.CONTINUOUS:
            losses[name] = (
                "UNREPRESENTABLE:CONTINUOUS_DIMENSION_HAS_NO_SOUND_PROPOSITIONAL_ENCODING"
            )
        elif kind is DimensionKind.OBJECT_VALUED:
            losses[name] = (
                "UNREPRESENTABLE:OBJECT_VALUED_DIMENSION_REQUIRES_TYPED_PREDICATES"
            )
        else:
            losses[name] = "UNREPRESENTABLE:UNKNOWN_DIMENSION_KIND"
    return frozenset(facts), losses
