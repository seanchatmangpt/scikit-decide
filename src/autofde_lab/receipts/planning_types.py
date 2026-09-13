"""The honest observation shape for one scikit-decide rollout step.

Superseding an earlier wiring that validated planning steps against
``wasm4pm_types.OcelEvent`` — a process-mining *event* shape (``id``/``type``/``time``/
``relationships``). Executed investigation (real ``rollout()`` over the real
``hub/domain/maze`` + ``hub/solver/p_astar.Astar``, see
``receipts/tests/test_real_rollout.py``) confirmed a real step carries none of those
fields: it is a plain ``(observation, action, Value(reward, cost))`` triple
(``autofde_lab.core.EnvironmentOutcome``, ``src/autofde_lab/core.py``). Coercing that
into ``OcelEvent`` would have made ``admit_typed`` accept data structurally unrelated
to what the model claims to validate. This module is the fix: validate what actually
comes out of a rollout, not a guessed process-mining shape.

If OCEL-style events are wanted later (e.g. to feed process-mining conformance
tooling downstream), that should be a separate *adapter* that maps a
``list[PlanStepOutcome]`` trajectory to synthetic ``OcelEvent``s (assigning a
synthetic ``id``/``type`` per step) — not this admission shape itself. See
``wasm4pm_types.py``'s module docstring for the same note from the other side.
"""

from __future__ import annotations

from pydantic import BaseModel


class PlanStepOutcome(BaseModel):
    """One rollout step, real field names only — nothing this shape doesn't
    actually carry. ``observation``/``action`` are stored as ``str(...)`` because
    scikit-decide domain state/action types are arbitrary user Python objects
    (``NamedTuple``s, ``Enum`` members, ...), not JSON-native; a future
    per-domain-typed integration can subclass this rather than widen it generically.
    """

    observation: str
    action: str
    reward: float
    cost: float
    termination: bool
    step_index: int


__all__ = ["PlanStepOutcome"]
