# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""One decision epoch: a candidate plan plus where traversal of it has reached.

An epoch is immutable. Advancing produces a new epoch; superseding marks the old
one ``SUPERSEDED`` and never deletes it, so lineage stays inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from autofde_lab.agent.models import EpochStanding
from autofde_lab.fabric.canonical import sha256
from autofde_lab.powl.algebra import Atom, PowlNode
from autofde_lab.powl.bounds import DEFAULT_BOUND, ExecutionBound
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    ChoiceRecord,
    Marking,
    NodePath,
    enabled as _enabled,
    is_final as _is_final,
)
from autofde_lab.powl.normalize import model_digest

__all__ = ["DecisionEpoch", "atom_labels"]


def atom_labels(node: PowlNode) -> frozenset[str]:
    """Every ``Atom`` label reachable in ``node`` — used for preservation checks."""
    if isinstance(node, Atom):
        return frozenset({node.label})
    children = getattr(node, "children", ())
    out: set[str] = set()
    for child in children:
        out |= atom_labels(child)
    return frozenset(out)


@dataclass(frozen=True, slots=True)
class DecisionEpoch:
    """A candidate plan under bounded traversal. Computes; never actuates."""

    epoch_id: str
    model: PowlNode
    model_sha256: str
    bound: ExecutionBound = DEFAULT_BOUND
    # ``Marking`` defines ``__eq__`` in its body and is therefore unhashable,
    # so dataclasses treat it as a mutable default. It is in fact frozen.
    marking: Marking = field(default_factory=lambda: INITIAL_MARKING)
    choices: tuple[ChoiceRecord, ...] = ()
    supersedes: tuple[str, ...] = ()
    preserves: tuple[str, ...] = ()
    standing: EpochStanding = EpochStanding.UNKNOWN

    @classmethod
    def create(
        cls,
        model: PowlNode,
        *,
        session_id: str,
        index: int,
        bound: ExecutionBound = DEFAULT_BOUND,
        supersedes: tuple[str, ...] = (),
        preserves: tuple[str, ...] = (),
    ) -> DecisionEpoch:
        """Build epoch ``index`` of ``session_id`` over ``model``."""
        digest = model_digest(model)
        epoch_id = sha256(
            {
                "session_id": session_id,
                "index": index,
                "model_sha256": digest,
                "bound_sha256": bound.sha256(),
                "supersedes": list(supersedes),
                "preserves": sorted(preserves),
            }
        )
        return cls(
            epoch_id=epoch_id,
            model=model,
            model_sha256=digest,
            bound=bound,
            supersedes=tuple(supersedes),
            preserves=tuple(preserves),
            standing=EpochStanding.UNKNOWN,
        )

    #: Standings after which an epoch is closed to further traversal. A
    #: superseded epoch is kept for lineage, never resumed.
    TERMINAL_STANDINGS = frozenset({EpochStanding.SUPERSEDED})

    def enabled(self) -> frozenset[NodePath]:
        """Leaf paths that may advance next. A set — the epoch never picks.

        A terminal (``SUPERSEDED``) epoch enables nothing. Containment must not
        rest on ``AgentSession`` only ever addressing its last epoch: any caller
        holding a reference to a superseded epoch would otherwise be handed a
        live step set for a plan that has been replaced.
        """
        if self.standing in DecisionEpoch.TERMINAL_STANDINGS:
            return frozenset()
        return _enabled(self.model, self.marking, self.bound)

    def is_final(self) -> bool:
        """Whether the model is structurally complete under the current marking."""
        return _is_final(self.model, self.marking)

    def advanced(
        self, marking: Marking, choice: ChoiceRecord, standing: EpochStanding
    ) -> DecisionEpoch:
        """A new epoch identical to this one but one step further along."""
        return replace(
            self,
            marking=marking,
            choices=self.choices + (choice,),
            standing=standing,
        )

    def with_standing(self, standing: EpochStanding) -> DecisionEpoch:
        """A new epoch differing only in standing."""
        return replace(self, standing=standing)

    def labels(self) -> frozenset[str]:
        """Every atom label in this epoch's model."""
        return atom_labels(self.model)

    def lineage_material(self) -> dict[str, Any]:
        """Canonical description of this epoch's place in the lineage."""
        return {
            "epoch_id": self.epoch_id,
            "model_sha256": self.model_sha256,
            "bound_sha256": self.bound.sha256(),
            "supersedes": list(self.supersedes),
            "preserves": sorted(self.preserves),
            "standing": self.standing.value,
        }
