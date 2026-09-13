"""Local Pydantic v2 kernel types for the autofde-lab GymAct wrapper.

Re-exports `gymact.models.Standing` from the real, standalone `gymact` package
(/Users/sac/gymact) directly -- its five extra members (`UNKNOWN`,
`PARTIAL_ALIVE`, `BUILD_BROKEN`, `UNSUPPORTED`, `REFUSED` beyond this
wrapper's original `"ALIVE"` literal) are a strict superset of what this
kernel produced before, and `StrEnum` members compare equal to their string
value, so every existing `result.standing == "ALIVE"`-style assertion keeps
working unchanged.

`ActuationIntent`, `Observation`, `ActuationResult`, and `KernelEvent` stay
local, real (not faked) Pydantic models rather than re-exports, because their
field shapes genuinely do not match the real `gymact.models` types of the
same name -- see the docstring on each class below for the exact fields that
differ and why. `GymActKernel` (kernel.py) builds real `gymact.models`
request objects internally and adapts their real responses into these local
shapes at the boundary; it does not re-derive kernel logic the real package
already owns.
"""

from __future__ import annotations

from typing import Any

from gymact.models import Standing
from pydantic import BaseModel, ConfigDict

__all__ = [
    "ActuationIntent",
    "ActuationResult",
    "KernelEvent",
    "Observation",
    "Standing",
]


class ActuationIntent(BaseModel):
    """What a caller asks the kernel to do.

    Kept local instead of re-exporting `gymact.models.ActuationIntent`
    because two fields genuinely differ in shape, not just in name:

    - `subject` (e.g. `"cloudgoat"`): this wrapper's caller-chosen label for
      an episode's benchmark subject. The real `ActuationIntent` has no such
      field -- subject identity there is implicit in which `provider` a
      `MaterializationIntent` names.
    - `operation`: here a free string naming any of this kernel's 12
      lifecycle operations (`"discover"`, `"configure"`, `"score"`, ...). The
      real `ActuationIntent.operation` is `Literal[Operation.ACT]` -- fixed
      to exactly one of the real 8-operation enum's members, because that
      model exists solely to request a real actuation, not to name any
      lifecycle step generically. It also requires a `capability` (IRI)
      field this wrapper's callers never supply.
    """

    model_config = ConfigDict(frozen=True)

    subject: str
    operation: str
    episode_id: str
    payload: dict[str, Any] = {}
    authority_ref: str | None = None
    idempotency_key: str | None = None


class Observation(BaseModel):
    """Evidence about the world after (or independent of) an actuation.

    Kept local instead of re-exporting `gymact.models.Observation` because
    the real model has no `subject` field (it carries `state` +
    `state_digest`, keyed only by `episode_id`) while this wrapper's callers
    and tests construct/compare `Observation(episode_id=..., subject=...,
    result=...)` directly. `GymActKernel` builds a real `gymact.models.
    Observation` when it calls into the real runtime and copies its `state`
    into this local model's `result` field.
    """

    model_config = ConfigDict(frozen=True)

    episode_id: str
    subject: str
    result: dict[str, Any] = {}


class ActuationResult(BaseModel):
    """What the kernel returns for one lifecycle operation.

    Kept local instead of re-exporting `gymact.models.ActuationResult`
    because: (1) the real model has no top-level `episode_id` field (only
    `effect`/`observation`/`receipt`, each of which carries or implies the
    episode elsewhere), while every caller of this wrapper keys results by
    `episode_id` directly; (2) the real model's `receipt: Receipt` field is
    required (never optional) and is a full `gymact.models.Receipt` object,
    while this wrapper's tests construct results with `receipt=None` and
    expect a bare `str | None` (a receipt id, not the full receipt). The
    `standing` field's *type* is the real, re-exported `gymact.models.
    Standing` enum (see module docstring) -- only the surrounding envelope
    shape differs, not the standing vocabulary itself.
    """

    model_config = ConfigDict(frozen=True)

    accepted: bool
    standing: Standing
    episode_id: str
    observation: Observation | None = None
    receipt: str | None = None


class KernelEvent(BaseModel):
    """One flat OCEL-shaped log entry: (episode_id, activity, timestamp, subject).

    `timestamp` is a monotonically increasing integer sequence number assigned
    by `EventLog.append`, not wall-clock time -- deterministic and trivially
    orderable for conformance replay, with no `datetime.now()` nondeterminism
    to pin in tests.

    No equivalent exists in `gymact.models`: the real package's OCEL log
    (`gymact.ocel.receipts_to_ocel`) is built from a list of real
    `gymact.models.Receipt` objects, one real `Operation` enum value per
    event -- it cannot represent this wrapper's four extra activities
    (`configure`/`reset`/`start`/`score`), which are not members of that
    enum (see `gymact.models.Operation`'s own docstring for why that
    reduction from 12 to 8 operations was deliberate). `KernelEvent` is this
    wrapper's own real, local replay log covering the full 12-activity
    lifecycle `ConformanceChecker` (process.py) checks against; for the 8
    activities that do have a real `gymact.models.Operation` counterpart,
    `GymActKernel` additionally obtains a real `gymact.models.Receipt` from
    the real runtime and threads its `receipt_id` through as this event's/
    result's `receipt` string.
    """

    model_config = ConfigDict(frozen=True)

    episode_id: str
    activity: str
    timestamp: int
    subject: str
    attributes: dict[str, Any] = {}
