# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The persistent agent session: an append-only stack of decision epochs.

Scope, stated once and binding on everything below: this computes **candidate
plans**. It does not actuate, admit, broker, or issue an authoritative receipt.
``EpochReceipt`` and ``AgentOutcome`` are descriptions of a bounded traversal,
carrying an explicit claim ceiling so they cannot be read as admissions.

``ExecutionBound`` is immutable for the life of a session and its digest is
folded into ``AgentOutcome.input_sha256``. Without that fold, two runs under
different caps would produce outcome digests that *look* comparable and are not
— a bounded traversal that stopped at its cap and one that ran to completion are
different claims, and the digest must say so.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any, Optional, Sequence

from autofde_lab.agent.bridge import (
    IntentRegisteringPolicies,
    SessionRolloutCallback,
    resolve_enabled_node,
)
from autofde_lab.agent.epoch import DecisionEpoch
from autofde_lab.agent.ledger import IntentToken, OccurrenceLedger
from autofde_lab.agent.models import (
    AGENT_OUTCOME_SCHEMA,
    EPOCH_RECEIPT_SCHEMA,
    AgentOutcome,
    EpochReceipt,
    EpochStanding,
)
from autofde_lab.schema_ids import DECISION_RESULT_SCHEMA
from autofde_lab.agent.refusals import (
    BLOCKED_ACTION_NODE_UNRESOLVED,
    CLAIM_CEILING,
    AgentRefusal,
    AgentRefusalCode,
)
from autofde_lab.fabric.canonical import implementation_identity, sha256
from autofde_lab.fabric.models import (
    CacheStatus,
    DecisionRequest,
    DecisionResult,
    DecisionStanding,
    DecisionStep,
)
from autofde_lab.powl.algebra import Atom, PowlNode
from autofde_lab.powl.bounds import DEFAULT_BOUND, ExecutionBound
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    ChoiceRecord,
    Marking,
    NodePath,
    enabled as _enabled,
    fire,
    node_at,
    trace_of,
)
from autofde_lab.powl.refusals import PowlError, PowlRefusal
from autofde_lab.powl.identity import OccurrenceKey, activity_sha256, node_id
from autofde_lab.solvers import Solver
from autofde_lab.utils import rollout

__all__ = ["AgentSession"]


def _activity_of(node: PowlNode) -> str:
    return activity_sha256(node) if isinstance(node, Atom) else node_id(node)


class AgentSession:
    """A persistent, epoch-structured candidate-planning session."""

    def __init__(
        self,
        domain: Any,
        solver: Any = None,
        *,
        bound: ExecutionBound = DEFAULT_BOUND,
        session_id: str | None = None,
        ledger: OccurrenceLedger | None = None,
    ) -> None:
        self._domain = domain
        self._solver = solver
        self._bound = bound  # immutable for the session's whole life
        self._ledger = ledger if ledger is not None else OccurrenceLedger()
        # A ledger handed in from a previous process may be mid-intent. That is
        # the one state recovery cannot resolve, so refuse here, at the door.
        self._ledger.assert_resumable()

        self._session_id = session_id or sha256(
            {
                "domain": implementation_identity(type(domain)),
                "solver": None if solver is None else implementation_identity(type(solver)),
                "bound_sha256": bound.sha256(),
            }
        )
        self._random = random.Random(self._session_id)
        self._epochs: list[DecisionEpoch] = []
        self._receipts: list[EpochReceipt] = []
        self._pending: tuple[IntentToken, NodePath, tuple[NodePath, ...]] | None = None
        self._closed = False

    # ── properties ─────────────────────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def bound(self) -> ExecutionBound:
        """The session's immutable traversal budget."""
        return self._bound

    @property
    def ledger(self) -> OccurrenceLedger:
        return self._ledger

    @property
    def epochs(self) -> tuple[DecisionEpoch, ...]:
        return tuple(self._epochs)

    @property
    def random(self) -> random.Random:
        """Seeded from ``session_id`` so tie-breaks are reproducible."""
        return self._random

    # ── epoch lifecycle ────────────────────────────────────────────────────

    def open_epoch(
        self,
        model: PowlNode,
        supersedes: Sequence[str] | None = None,
        preserves: Sequence[str] | None = None,
        marking: Marking | None = None,
    ) -> DecisionEpoch:
        """Push a new epoch. Never pops: superseded epochs stay in the stack.

        ``marking`` is the position the new epoch starts from. Absent, traversal
        starts empty. A replan supplies the seed produced by
        :func:`autofde_lab.agent.replan.seed_marking`, which is what makes
        preserved work structurally unable to re-execute — a preserved leaf is
        in ``completed_paths`` and so can never enter ``enabled``. This session
        does not compute that seed and never infers one.
        """
        if self._closed:
            raise AgentRefusal(
                AgentRefusalCode.SESSION_CLOSED, "session is closed"
            )
        supersedes = tuple(supersedes or ())
        preserves = tuple(preserves or ())
        known = {e.epoch_id for e in self._epochs}
        unknown = [e for e in supersedes if e not in known]
        if unknown:
            raise AgentRefusal(
                AgentRefusalCode.UNKNOWN_SUPERSEDED_EPOCH,
                "supersedes names an epoch this session never opened",
                details={"unknown": unknown},
            )
        epoch = DecisionEpoch.create(
            model,
            session_id=self._session_id,
            index=len(self._epochs),
            bound=self._bound,
            supersedes=supersedes,
            preserves=preserves,
        )
        if marking is not None:
            epoch = replace(epoch, marking=marking)
        missing = sorted(set(preserves) - set(epoch.labels()))
        if missing:
            raise AgentRefusal(
                AgentRefusalCode.PRESERVATION_VIOLATED,
                "new model drops activities the caller required preserved",
                details={"missing": missing},
            )
        for index, existing in enumerate(self._epochs):
            if existing.epoch_id in supersedes:
                self._epochs[index] = existing.with_standing(EpochStanding.SUPERSEDED)
        self._epochs.append(epoch)
        return epoch

    def replan(
        self,
        model: PowlNode,
        preserves: Sequence[str] = (),
        marking: Marking | None = None,
    ) -> DecisionEpoch:
        """Supersede the current epoch with ``model``, preserving named activities."""
        if not self._epochs:
            raise AgentRefusal(
                AgentRefusalCode.NO_OPEN_EPOCH, "replan() before any epoch was opened"
            )
        return self.open_epoch(
            model,
            supersedes=(self._epochs[-1].epoch_id,),
            preserves=preserves,
            marking=marking,
        )

    def _current(self) -> DecisionEpoch:
        if not self._epochs:
            raise AgentRefusal(
                AgentRefusalCode.NO_OPEN_EPOCH, "no epoch is open"
            )
        return self._epochs[-1]

    # ── intent plumbing (called by the bridge, not by users) ───────────────

    def _has_outstanding_intent(self) -> bool:
        return self._pending is not None

    def _register_intent(self, action: Any) -> IntentToken:
        epoch = self._current()
        live = tuple(sorted(epoch.enabled()))
        path = resolve_enabled_node(epoch, action)  # refuses rather than guessing
        token = self._ledger.intend(
            path,
            context_sha256=self._context_sha256(epoch),
            activity_sha256=_activity_of(node_at(epoch.model, path)),
            detail="PRE_ACT",
        )
        self._pending = (token, path, live)
        return token

    def _commit_intent(self, outcome: Any = None, detail: str = "") -> None:
        if self._pending is None:
            raise AgentRefusal(
                AgentRefusalCode.ACTION_NODE_UNRESOLVED,
                "an act completed with no outstanding intent; "
                "the node is never recovered from the action after the fact",
                details={"detail": detail},
            )
        token, path, live = self._pending
        self._pending = None
        epoch = self._current()
        marking = fire(
            epoch.model,
            epoch.marking,
            path,
            context_sha256=self._context_sha256(epoch),
            bound=self._bound,
        )
        record = ChoiceRecord(
            step=len(epoch.choices),
            path=path,
            enabled=live,
            chosen=path,
            decided_by=self._decided_by(),
            context_sha256=self._context_sha256(epoch),
        )
        advanced = epoch.advanced(marking, record, EpochStanding.PARTIAL_ALIVE)
        self._epochs[-1] = advanced
        self._ledger.commit(
            token,
            outcome=None,  # the domain outcome is evidence, not ledger identity
            activity_sha256=_activity_of(node_at(epoch.model, path)),
            detail=detail,
        )

    def _context_sha256(self, epoch: DecisionEpoch) -> str:
        return sha256({"session_id": self._session_id, "epoch_id": epoch.epoch_id})

    def _decided_by(self) -> str:
        if self._solver is None:
            return "policy:autofde_lab.utils.rollout.RandomWalk"
        cls = type(self._solver)
        return f"policy:{cls.__module__}.{cls.__qualname__}"

    # ── stepping by node path ──────────────────────────────────────────────

    def step(
        self, path: NodePath, *, decided_by: str | None = None
    ) -> tuple[ChoiceRecord, OccurrenceKey]:
        """Advance the current epoch past the leaf at ``path``.

        The path-addressed counterpart of :meth:`advance`. It exists because a
        rollout-driven advance can only reach nodes an action resolves to, and
        a :class:`~autofde_lab.powl.algebra.ChoiceGraph`'s boundary nodes are
        ``Silent`` by construction under the POWL 2.0 boundary law — no domain
        action ever names them, so a model containing a choice is unreachable
        through :meth:`advance` alone.

        The two-phase ledger discipline is identical: enabledness is checked,
        then ``INTENDED`` is written, then the structural fire happens, then
        ``COMMITTED``. Nothing here invokes an ``Atom``'s ``action`` payload,
        and nothing here actuates.
        """
        epoch = self._current()
        live = _enabled(epoch.model, epoch.marking, self._bound)
        if path not in live:
            # checked before the intent is written, so a rejected step cannot
            # leave the ledger unresumable
            raise PowlError(
                PowlRefusal.LANGUAGE_MISMATCH,
                f"path {path} is not enabled; enabled={sorted(live)}",
            )
        node = node_at(epoch.model, path)
        activity = _activity_of(node)
        context = self._context_sha256(epoch)
        token = self._ledger.intend(
            path, context_sha256=context, activity_sha256=activity, detail="PRE_ACT"
        )
        marking = fire(
            epoch.model, epoch.marking, path, context_sha256=context, bound=self._bound
        )
        record = ChoiceRecord(
            step=len(epoch.choices),
            path=path,
            enabled=tuple(sorted(live)),
            chosen=path,
            decided_by=decided_by or self._decided_by(),
            context_sha256=context,
        )
        self._epochs[-1] = epoch.advanced(
            marking, record, EpochStanding.PARTIAL_ALIVE
        )
        key = self._ledger.commit(
            token, activity_sha256=activity, detail="POST_STEP"
        )
        return record, key

    def seal_epoch(self) -> EpochReceipt:
        """Receipt the current epoch without running a domain rollout.

        Standing is read off the marking, exactly as :meth:`advance` does: final
        => ``ALIVE``, some steps => ``PARTIAL_ALIVE``, none => ``UNKNOWN``. The
        receipt carries no domain evidence because no domain rollout ran, and
        says so by leaving ``evidence`` ``None`` rather than fabricating one.
        """
        epoch = self._current()
        if epoch.is_final():
            standing = EpochStanding.ALIVE
        elif epoch.choices:
            standing = EpochStanding.PARTIAL_ALIVE
        else:
            standing = EpochStanding.UNKNOWN
        epoch = epoch.with_standing(standing)
        self._epochs[-1] = epoch
        receipt = self._receipt(epoch, None, [], None)
        self._receipts.append(receipt)
        return receipt

    # ── advancing ──────────────────────────────────────────────────────────

    def advance(
        self, observation: Any = None, max_steps: int | None = None
    ) -> EpochReceipt:
        """Run one bounded rollout against the current epoch and receipt it."""
        epoch = self._current()
        callback = SessionRolloutCallback(self)
        policy = self._policy()
        # ``rollout`` calls ``solver.reset()`` only for ``isinstance(solver, Solver)``,
        # and the proxy is not a ``Solver``. Do it here so wrapping a real solver
        # does not silently skip its reset.
        reset = getattr(policy, "reset", None)
        if callable(reset) and isinstance(policy, Solver):
            reset()
        proxy = IntentRegisteringPolicies(policy, self)
        blocked_reason: str | None = None
        episodes: list[Any] = []
        try:
            episodes = (
                rollout(
                    self._domain,
                    proxy,
                    from_memory=observation,
                    num_episodes=1,
                    max_steps=max_steps,
                    render=False,
                    verbose=False,
                    action_formatter=None,
                    outcome_formatter=None,
                    observation_formatter=None,
                    return_episodes=True,
                    rollout_callback=callback,
                )
                or []
            )
        except AgentRefusal as refusal:
            if refusal.code is not AgentRefusalCode.ACTION_NODE_UNRESOLVED:
                raise
            blocked_reason = BLOCKED_ACTION_NODE_UNRESOLVED

        epoch = self._current()
        if blocked_reason is not None:
            standing = EpochStanding.BLOCKED
        elif epoch.is_final():
            standing = EpochStanding.ALIVE
        elif epoch.choices:
            standing = EpochStanding.PARTIAL_ALIVE
        else:
            standing = EpochStanding.UNKNOWN
        epoch = epoch.with_standing(standing)
        self._epochs[-1] = epoch

        receipt = self._receipt(epoch, blocked_reason, episodes, max_steps)
        self._receipts.append(receipt)
        return receipt

    def _policy(self) -> Any:
        if self._solver is not None:
            return self._solver
        domain = self._domain

        class _RandomWalk:
            def sample_action(self, observation: Any, domain: Any = None) -> Any:
                return {
                    agent: [space.sample()]
                    for agent, space in domain.get_applicable_actions().items()
                }

            def is_policy_defined_for(self, observation: Any) -> bool:
                return True

        del domain
        return _RandomWalk()

    # ── receipts ───────────────────────────────────────────────────────────

    def _evidence(
        self, epoch: DecisionEpoch, episodes: list[Any], max_steps: int | None
    ) -> DecisionResult | None:
        if not episodes:
            return None
        observations, actions, values = episodes[0]
        steps = tuple(
            DecisionStep(
                index=i,
                observation=observations[i],
                action=actions[i],
                next_observation=observations[i + 1],
                value=values[i],
                termination=(i == len(actions) - 1),
                info=None,
            )
            for i in range(len(actions))
        )
        request = DecisionRequest(
            domain=type(self._domain).__qualname__,
            solver=None if self._solver is None else type(self._solver).__qualname__,
            max_steps=int(max_steps or 0),
            use_cache=False,
        )
        payload = {
            "request": request.semantic_dict(),
            "epoch_id": epoch.epoch_id,
            "bound_sha256": self._bound.sha256(),
        }
        trajectory = sha256([s.as_dict() for s in steps])
        return DecisionResult(
            schema=DECISION_RESULT_SCHEMA,
            standing=DecisionStanding.BOUNDED,
            request=request,
            solver=self._decided_by(),
            initial_observation=observations[0] if observations else None,
            steps=steps,
            terminal=False,
            cache_status=CacheStatus.BYPASS,
            input_sha256=sha256(payload),
            trajectory_sha256=trajectory,
            receipt_sha256=sha256({"input": sha256(payload), "traj": trajectory}),
            claim_ceiling=CLAIM_CEILING,
        )

    def _receipt(
        self,
        epoch: DecisionEpoch,
        blocked_reason: str | None,
        episodes: list[Any],
        max_steps: int | None,
    ) -> EpochReceipt:
        evidence = self._evidence(epoch, episodes, max_steps)
        material = {
            "schema": EPOCH_RECEIPT_SCHEMA,
            "session_id": self._session_id,
            "epoch_id": epoch.epoch_id,
            "model_sha256": epoch.model_sha256,
            "bound_sha256": self._bound.sha256(),
            "standing": epoch.standing.value,
            "blocked_reason": blocked_reason,
            "marking": epoch.marking.digest_material(),
            "trace": list(trace_of(epoch.model, epoch.choices)),
            "ledger_sha256": self._ledger.sha256(),
        }
        return EpochReceipt(
            schema=EPOCH_RECEIPT_SCHEMA,
            session_id=self._session_id,
            epoch_id=epoch.epoch_id,
            model_sha256=epoch.model_sha256,
            bound_sha256=self._bound.sha256(),
            standing=epoch.standing,
            blocked_reason=blocked_reason,
            steps=len(epoch.choices),
            trace=trace_of(epoch.model, epoch.choices),
            occurrences=self._ledger.occurrences(),
            marking_sha256=sha256(epoch.marking.digest_material()),
            supersedes=epoch.supersedes,
            preserves=epoch.preserves,
            evidence=evidence,
            claim_ceiling=CLAIM_CEILING,
            receipt_sha256=sha256(material),
        )

    def outcome(self) -> AgentOutcome:
        """The whole-session envelope over every epoch receipt so far."""
        self._ledger.assert_resumable()
        receipts = tuple(self._receipts)
        blocked = [r for r in receipts if r.standing is EpochStanding.BLOCKED]
        if not receipts:
            standing, reason = EpochStanding.UNKNOWN, None
        elif blocked:
            standing, reason = EpochStanding.BLOCKED, blocked[0].blocked_reason
        elif all(
            r.standing in (EpochStanding.ALIVE, EpochStanding.SUPERSEDED)
            for r in receipts
        ):
            standing, reason = EpochStanding.ALIVE, None
        else:
            standing, reason = EpochStanding.PARTIAL_ALIVE, None

        input_material = {
            "session_id": self._session_id,
            "domain": implementation_identity(type(self._domain)),
            "solver": (
                None
                if self._solver is None
                else implementation_identity(type(self._solver))
            ),
            # Load-bearing: without the bound, two runs under different caps
            # would produce comparable-looking digests for incomparable claims.
            "bound_sha256": self._bound.sha256(),
            "models": [e.model_sha256 for e in self._epochs],
        }
        input_sha256 = sha256(input_material)
        lineage_sha256 = sha256([e.lineage_material() for e in self._epochs])
        return AgentOutcome(
            schema=AGENT_OUTCOME_SCHEMA,
            session_id=self._session_id,
            epochs=receipts,
            standing=standing,
            blocked_reason=reason,
            claim_ceiling=CLAIM_CEILING,
            input_sha256=input_sha256,
            lineage_sha256=lineage_sha256,
            receipt_sha256=sha256(
                {
                    "input_sha256": input_sha256,
                    "lineage_sha256": lineage_sha256,
                    "ledger_sha256": self._ledger.sha256(),
                    "epochs": [r.receipt_sha256 for r in receipts],
                    "standing": standing.value,
                }
            ),
        )

    def close(self) -> AgentOutcome:
        """Freeze the session and return its outcome."""
        out = self.outcome()
        self._closed = True
        return out
