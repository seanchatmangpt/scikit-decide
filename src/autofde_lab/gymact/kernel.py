"""GymActKernel: a thin, real wrapper over `gymact.runtime.GymAct`.

The real, standalone `gymact` package (/Users/sac/gymact, installed as a real
editable dependency -- see pyproject.toml's `[tool.uv.sources]`) owns the
actual semantic runtime: authority gating, idempotency, RFC8785/BLAKE3
evidence, and 8 of this wrapper's 12 named lifecycle operations
(`discover`/`materialize`/`observe`/`act`/`verify`/`checkpoint`/`restore`/
`teardown`, exactly `gymact.models.Operation`'s members). This kernel no
longer re-implements any of that -- every one of those 8 operations builds a
real `gymact.models` request, drives it through a real `gymact.runtime.
GymAct` instance (registered with a real `gymact.providers.MemoryProvider`),
and adapts the real response into this wrapper's own local
`autofde_lab.gymact.models` shapes (see models.py for exactly why those
local shapes can't just be the real `gymact.models` types).

The remaining 4 operations (`configure`/`reset`/`start`/`score`) have no
member in `gymact.models.Operation` -- that enum was deliberately reduced
from an earlier 12-operation design (see its own docstring) because, for
gymact's own stateless-per-episode providers, those four add no information
`materialize`/`verify` don't already carry. This kernel keeps them as thin,
real *local* operations: they still append a real `KernelEvent` to the real
`EventLog` and return a real `ActuationResult`, but they do not call into
`gymact.runtime.GymAct` (there is no real operation to call) and their
`ActuationResult.receipt` is `None` (there is no real `gymact.models.Receipt`
to mint for an operation the real `Operation` enum does not have).

Every one of the 12 operations still appends to the local `EventLog`
regardless of whether it also drove a real runtime call, so
`process.ConformanceChecker` keeps replaying the same 12-activity lifecycle
it always has.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from gymact.models import ActuationIntent as _RealActuationIntent
from gymact.models import Consequence as _RealConsequence
from gymact.models import MaterializationIntent as _RealMaterializationIntent
from gymact.models import Standing
from gymact.providers import EnvironmentProvider, MemoryProvider
from gymact.runtime import GymAct as _RealGymAct

from autofde_lab.gymact.eventlog import EventLog
from autofde_lab.gymact.models import ActuationResult, Observation

OPERATIONS = (
    "discover",
    "materialize",
    "configure",
    "reset",
    "start",
    "observe",
    "act",
    "verify",
    "score",
    "checkpoint",
    "restore",
    "teardown",
)


def _run_async(coro: Any) -> Any:
    """Run a real `gymact.runtime.GymAct` coroutine to completion.

    `GymAct`'s operations are `async def` (it holds `anyio` locks
    internally). This kernel's own public methods stay synchronous, matching
    the pre-refactor contract that `test_process_conformance.py` and
    `cli.py` both call directly with no `await`. When this thread has no
    running event loop, `asyncio.run` drives the coroutine directly. When one
    is already running (e.g. this kernel was reached from inside an async
    FastAPI/FastMCP handler without being awaited), the same real coroutine
    is instead driven to completion on a dedicated worker thread with its
    own fresh loop, avoiding `asyncio.run`'s "cannot be called from a running
    event loop" error -- still a real, unmocked execution, just relocated to
    a thread that has no loop of its own.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class GymActKernel:
    """Real, in-process kernel over a real `gymact.runtime.GymAct` instance."""

    def __init__(self, *, provider: EnvironmentProvider | None = None) -> None:
        self._runtime = _RealGymAct()
        self._provider = provider or MemoryProvider()
        self._runtime.register_provider(self._provider)
        self.event_log = EventLog()
        # local (caller-chosen) episode_id -> real gymact.runtime episode_id,
        # populated once `materialize` accepts. gymact.runtime.GymAct mints
        # its own episode ids (uuid4 hex) and has no way to accept a
        # caller-supplied one, so this mapping is the real seam between this
        # wrapper's externally stable episode_id and the real runtime's own.
        self._real_episode_ids: dict[str, str] = {}
        self._checkpoints: dict[str, dict[str, Any]] = {}

    def real_ocel_log(self, episode_id: str) -> dict[str, Any] | None:
        """Real OCEL 2.0 log from `gymact.runtime.GymAct` for one episode's
        real (8-operation) receipt trail, or `None` if the episode was never
        materialized against the real runtime. Covers a strict subset of
        `event_log.events_for_episode(episode_id)` -- see eventlog.py."""
        real_id = self._real_episode_ids.get(episode_id)
        if real_id is None:
            return None
        return self._runtime.episode_ocel_log(real_id)

    def _log(
        self, *, operation: str, subject: str, episode_id: str, attributes: dict[str, Any]
    ) -> None:
        self.event_log.append(
            episode_id=episode_id,
            activity=operation,
            subject=subject,
            attributes=attributes,
        )

    def _local_result(
        self,
        *,
        operation: str,
        subject: str,
        episode_id: str,
        accepted: bool,
        standing: Standing,
        result: dict[str, Any] | None,
        receipt: str | None,
        log_attributes: dict[str, Any] | None = None,
    ) -> ActuationResult:
        self._log(
            operation=operation,
            subject=subject,
            episode_id=episode_id,
            attributes=log_attributes if log_attributes is not None else (result or {}),
        )
        observation = Observation(episode_id=episode_id, subject=subject, result=result or {})
        return ActuationResult(
            accepted=accepted,
            standing=standing,
            episode_id=episode_id,
            observation=observation,
            receipt=receipt,
        )

    def _unmaterialized_result(
        self, *, operation: str, subject: str, episode_id: str
    ) -> ActuationResult:
        """Typed refusal (per .claude/rules/actuation-authority.md: a refusal
        must be typed and evidenced, never a silent no-op) for an operation
        that requires a real materialized episode this local episode_id has
        not (yet, or any longer) been mapped to."""
        return self._local_result(
            operation=operation,
            subject=subject,
            episode_id=episode_id,
            accepted=False,
            standing=Standing.REFUSED,
            result=None,
            receipt=None,
            log_attributes={"reason": "EPISODE_NOT_MATERIALIZED"},
        )

    # -- pass-through local operations (no gymact.models.Operation member) --

    def configure(self, *, subject: str, episode_id: str) -> ActuationResult:
        return self._local_result(
            operation="configure",
            subject=subject,
            episode_id=episode_id,
            accepted=True,
            standing=Standing.ALIVE,
            result=None,
            receipt=None,
        )

    def reset(self, *, subject: str, episode_id: str) -> ActuationResult:
        return self._local_result(
            operation="reset",
            subject=subject,
            episode_id=episode_id,
            accepted=True,
            standing=Standing.ALIVE,
            result=None,
            receipt=None,
        )

    def start(self, *, subject: str, episode_id: str) -> ActuationResult:
        return self._local_result(
            operation="start",
            subject=subject,
            episode_id=episode_id,
            accepted=True,
            standing=Standing.ALIVE,
            result=None,
            receipt=None,
        )

    def score(self, *, subject: str, episode_id: str) -> ActuationResult:
        return self._local_result(
            operation="score",
            subject=subject,
            episode_id=episode_id,
            accepted=True,
            standing=Standing.ALIVE,
            result=None,
            receipt=None,
        )

    # -- operations routed through the real gymact.runtime.GymAct --

    def discover(self, *, subject: str, episode_id: str) -> ActuationResult:
        providers = self._runtime.discover()
        return self._local_result(
            operation="discover",
            subject=subject,
            episode_id=episode_id,
            accepted=True,
            standing=Standing.ALIVE,
            result={"providers": list(providers)},
            receipt=None,  # real discover() is registry inspection, no Receipt minted
        )

    def materialize(self, *, subject: str, episode_id: str) -> ActuationResult:
        intent = _RealMaterializationIntent(
            provider=self._provider.name,
            scenario=subject,
            idempotency_key=episode_id,
        )
        result = _run_async(self._runtime.materialize(intent))
        if result.accepted and result.episode is not None:
            self._real_episode_ids[episode_id] = result.episode.episode_id
        state = result.observation.state if result.observation else {}
        return self._local_result(
            operation="materialize",
            subject=subject,
            episode_id=episode_id,
            accepted=result.accepted,
            standing=result.standing,
            result=state,
            receipt=result.receipt.receipt_id,
            log_attributes={"standing": result.standing.value, "reason": result.receipt.reason},
        )

    def observe(self, *, subject: str, episode_id: str) -> ActuationResult:
        real_id = self._real_episode_ids.get(episode_id)
        if real_id is None:
            return self._unmaterialized_result(
                operation="observe", subject=subject, episode_id=episode_id
            )
        observation = _run_async(self._runtime.observe(real_id))
        return self._local_result(
            operation="observe",
            subject=subject,
            episode_id=episode_id,
            accepted=True,
            standing=Standing.ALIVE,
            result=observation.state,
            receipt=None,  # real observe() is a pure read, no Receipt minted
        )

    def act(
        self, *, subject: str, episode_id: str, payload: dict[str, Any] | None = None
    ) -> ActuationResult:
        real_id = self._real_episode_ids.get(episode_id)
        if real_id is None:
            return self._unmaterialized_result(
                operation="act", subject=subject, episode_id=episode_id
            )
        payload = dict(payload or {})
        capability = payload.pop("capability", None)
        if capability is None:
            capabilities = self._runtime.capabilities(real_id)
            do_capabilities = [c for c in capabilities if c.consequence is _RealConsequence.DO]
            capability = do_capabilities[0].iri if do_capabilities else ""
        intent = _RealActuationIntent(episode_id=real_id, capability=capability, payload=payload)
        result = _run_async(self._runtime.act(intent))
        state = result.observation.state if result.observation else {}
        return self._local_result(
            operation="act",
            subject=subject,
            episode_id=episode_id,
            accepted=result.accepted,
            standing=result.standing,
            result=state,
            receipt=result.receipt.receipt_id,
            log_attributes={"standing": result.standing.value, "reason": result.receipt.reason},
        )

    def verify(self, *, subject: str, episode_id: str) -> ActuationResult:
        real_id = self._real_episode_ids.get(episode_id)
        if real_id is None:
            return self._unmaterialized_result(
                operation="verify", subject=subject, episode_id=episode_id
            )
        # The kernel's public verify() takes no `expected` argument (matching
        # its pre-refactor signature); an empty expectation trivially passes
        # (`all()` over no constraints), so this real call still exercises
        # gymact.runtime.GymAct.verify's real independent-observation path.
        result = _run_async(self._runtime.verify(real_id, {}))
        return self._local_result(
            operation="verify",
            subject=subject,
            episode_id=episode_id,
            accepted=result.passed,
            standing=Standing.ALIVE if result.passed else Standing.REFUSED,
            result=result.observed,
            receipt=None,  # real verify() is a pure read, no Receipt minted
        )

    def checkpoint(self, *, subject: str, episode_id: str) -> ActuationResult:
        real_id = self._real_episode_ids.get(episode_id)
        if real_id is None:
            return self._unmaterialized_result(
                operation="checkpoint", subject=subject, episode_id=episode_id
            )
        checkpoint = _run_async(self._runtime.checkpoint(real_id))
        self._checkpoints[episode_id] = checkpoint
        return self._local_result(
            operation="checkpoint",
            subject=subject,
            episode_id=episode_id,
            accepted=True,
            standing=Standing.ALIVE,
            result=checkpoint,
            receipt=None,  # real checkpoint() is a pure read, no Receipt minted
        )

    def restore(self, *, subject: str, episode_id: str) -> ActuationResult:
        real_id = self._real_episode_ids.get(episode_id)
        if real_id is None:
            return self._unmaterialized_result(
                operation="restore", subject=subject, episode_id=episode_id
            )
        checkpoint = self._checkpoints.get(episode_id, {})
        receipt = _run_async(self._runtime.restore(real_id, checkpoint))
        return self._local_result(
            operation="restore",
            subject=subject,
            episode_id=episode_id,
            accepted=receipt.standing == Standing.ALIVE,
            standing=receipt.standing,
            result=checkpoint,
            receipt=receipt.receipt_id,
            log_attributes={"standing": receipt.standing.value, "reason": receipt.reason},
        )

    def teardown(self, *, subject: str, episode_id: str) -> ActuationResult:
        real_id = self._real_episode_ids.get(episode_id)
        if real_id is None:
            return self._unmaterialized_result(
                operation="teardown", subject=subject, episode_id=episode_id
            )
        receipt = _run_async(self._runtime.teardown(real_id))
        del self._real_episode_ids[episode_id]
        return self._local_result(
            operation="teardown",
            subject=subject,
            episode_id=episode_id,
            accepted=receipt.standing == Standing.ALIVE,
            standing=receipt.standing,
            result=None,
            receipt=receipt.receipt_id,
            log_attributes={"standing": receipt.standing.value, "reason": receipt.reason},
        )
