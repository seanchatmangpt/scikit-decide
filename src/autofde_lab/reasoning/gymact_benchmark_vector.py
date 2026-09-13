# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typed per-episode ``BenchmarkVector`` derived from real ``gymact`` Receipts
-- closing the gap this session's evidence record for capability 5 named:
``GymActWorldExperimentProvider`` (`gymact_world_experiment_provider.py`)
discards every real ``gymact.models.Receipt`` field except ``receipt_id``
(only ``receipt.receipt_id`` survives into ``ExperimentReceipt.observed_outcome_refs``),
even though the real Receipt already carries ``occurred_at``, ``costs``,
``pre_state_digest``/``post_state_digest``, and ``verified``. The only
scoring unit reaching ``PayoffHypergraph`` is
``planner_league.core.PayoffObservation(left_score, right_score, receipt_id)``
-- a scalar pair that collapses seven benchmark dimensions (success, cost,
latency, reversibility, violations, evidence completeness, portability) into
one opaque aggregate, contradicting the V2030.1.1 PRD's own acceptance line
54 falsifier: "candidate rankings expose objective tradeoffs instead of
hiding them in one opaque aggregate."

This module reads evidence; it mints none. No new scalar aggregate, no
change to ``PayoffObservation``, no change to
``GymActWorldExperimentProvider`` or ``laboratory.py``. Per
``.claude/rules/absence-is-not-evidence.md``, every field that cannot be
established from real data is a typed ``UNKNOWN`` (or ``None`` for
``latency_seconds``), never a coerced default.

Real API discrepancy from the evidence record, found and adapted to here
(not invented around)
-------------------------------------------------------------------------
The evidence record's ``proposed_step`` assumed a
``benchmark_vector_from_episode(runtime, episode_id, receipt)`` signature
reading ``runtime.episode_ocel_log(episode_id)``. Two real facts changed
that shape:

1. ``GymActWorldExperimentProvider.submit_experiment`` constructs its own
   ``gymact.runtime.GymAct`` instance *inside* an async helper and discards
   it before returning -- confirmed by reading
   ``gymact_world_experiment_provider.py:170,264-267`` -- so no caller of
   the real, currently-shipped provider can ever obtain that runtime
   afterward. A ``runtime``-typed parameter would be real-collaborator-shaped
   but uncallable by any real caller of the shipped provider.
2. The installed ``gymact`` (`gymact/kernel.py`) already exposes
   ``GymAct.episode_receipts(episode_id) -> list[Receipt]`` (kernel.py:148-150)
   -- a direct typed Receipt list, not a dict OCEL log requiring re-parsing.
   Reading that list directly is strictly more honest than parsing
   ``episode_ocel_log``'s event dict back into typed fields it was itself
   built from (`gymact/ocel.py`'s ``receipts_to_ocel`` already does that
   one, real conversion -- re-deriving it here would be exactly the
   dual-bookkeeping this repo's own law forbids).

So this module's real function takes the real per-episode Receipt trail
directly (``tuple[gymact.models.Receipt, ...]``, e.g. from a caller's own
``runtime.episode_receipts(episode_id)`` for a runtime it controls) plus the
real ``ExperimentReceipt`` a ``WorldExperimentProvider`` already returned for
that same intent -- both real, both typed, neither fabricated.

Reversibility: a second real discrepancy
-----------------------------------------
The evidence record's proposed reversibility rule compared "the teardown
receipt's post_state_digest" against "the materialization receipt's
pre_state_digest." Read directly this session (`gymact/kernel.py`'s real
``teardown()``, lines ~1078-1099): the real, successful TEARDOWN Receipt
carries only ``pre_state_digest`` -- ``post_state_digest`` is never set
(stays ``None`` by the field's own default). The proposed comparison is
therefore unrepresentable against the installed ``gymact`` version, not
merely unimplemented. This module uses the pair of real digests that *do*
exist for the same purpose: the first real ACT receipt's
``pre_state_digest`` (state immediately before any proposed action) against
the real TEARDOWN receipt's ``pre_state_digest`` (state immediately before
teardown, i.e. the final actuated state) -- both fields real per
`gymact/kernel.py`'s own `act()`/`teardown()` construction, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from gymact.models import CostDimension, Operation, Receipt

from autofde_lab.reasoning.laboratory import ExperimentReceipt

__all__ = ["BenchmarkVector", "benchmark_vector_from_episode"]

Reversibility = Literal["OBSERVED_REVERSIBLE", "OBSERVED_IRREVERSIBLE", "UNKNOWN"]
EvidenceCompleteness = Literal["COMPLETE", "PARTIAL", "UNKNOWN"]


@dataclass(frozen=True, slots=True)
class BenchmarkVector:
    """Seven-dimension per-episode benchmark evidence, kept plural by
    construction (per ``laboratory.py``'s own "plural matters" law) rather
    than collapsed into one aggregate. Portability (the same policy scored
    across two or more real ``gymact`` worlds) is explicitly NOT a field
    here -- it remains a named, un-closed gap; nothing below fabricates it."""

    success: bool
    violation_count: int
    cost: tuple[CostDimension, ...]
    latency_seconds: float | None
    reversibility: Reversibility
    evidence_completeness: EvidenceCompleteness


def _parse_occurred_at(value: str) -> datetime | None:
    """Real, honest ISO-8601 parse -- ``None`` (never a coerced epoch/zero)
    on any receipt whose ``occurred_at`` this session's installed
    ``datetime.fromisoformat`` cannot parse."""
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _latency_seconds(episode_receipts: tuple[Receipt, ...]) -> float | None:
    if len(episode_receipts) < 2:
        return None
    first = _parse_occurred_at(episode_receipts[0].occurred_at)
    last = _parse_occurred_at(episode_receipts[-1].occurred_at)
    if first is None or last is None:
        return None
    return (last - first).total_seconds()


def _reversibility(episode_receipts: tuple[Receipt, ...]) -> Reversibility:
    act_receipts = [r for r in episode_receipts if r.operation is Operation.ACT]
    teardown_receipts = [
        r for r in episode_receipts if r.operation is Operation.TEARDOWN
    ]
    if not act_receipts or not teardown_receipts:
        return "UNKNOWN"
    initial_digest = act_receipts[0].pre_state_digest
    final_digest = teardown_receipts[-1].pre_state_digest
    if initial_digest is None or final_digest is None:
        return "UNKNOWN"
    return (
        "OBSERVED_REVERSIBLE"
        if initial_digest == final_digest
        else "OBSERVED_IRREVERSIBLE"
    )


def _evidence_completeness(
    episode_receipts: tuple[Receipt, ...], receipt: ExperimentReceipt
) -> EvidenceCompleteness:
    if not receipt.observed_outcome_refs:
        return "UNKNOWN"
    real_receipt_ids = {r.receipt_id for r in episode_receipts}
    if all(ref in real_receipt_ids for ref in receipt.observed_outcome_refs):
        return "COMPLETE"
    return "PARTIAL"


def benchmark_vector_from_episode(
    episode_receipts: tuple[Receipt, ...], receipt: ExperimentReceipt
) -> BenchmarkVector:
    """Real per-episode benchmark evidence, read only from ``episode_receipts``
    (the real ``gymact.models.Receipt`` trail for one episode, e.g. from a
    caller-owned ``gymact.runtime.GymAct.episode_receipts(episode_id)``) and
    ``receipt`` (the real ``laboratory.ExperimentReceipt`` a
    ``WorldExperimentProvider`` already returned for the same
    ``ExperimentIntent``). Mints no new evidence; every field either derives
    from a real Receipt attribute or is a typed ``UNKNOWN``/``None``."""
    return BenchmarkVector(
        success=receipt.standing == "ALIVE",
        violation_count=len(receipt.postconditions_violated),
        cost=tuple(cost for r in episode_receipts for cost in r.costs),
        latency_seconds=_latency_seconds(episode_receipts),
        reversibility=_reversibility(episode_receipts),
        evidence_completeness=_evidence_completeness(episode_receipts, receipt),
    )
