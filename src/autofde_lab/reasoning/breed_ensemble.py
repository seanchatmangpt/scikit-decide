# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A general-purpose, domain-agnostic orchestrator running many real
``~/wasm4pm`` cognition breeds concurrently via the real POWL v2 runner
(:func:`autofde_lab.powl.guard_executor.execute`), then arbitrating their real
conclusions via wasm4pm's own real ``meta_reasoning`` breed.

Why this exists
------------------
``~/wasm4pm`` has 55 real, independent, deterministic cognition breeds and no
chaining mechanism of its own -- confirmed by reading ``dispatch.rs`` directly:
nothing in wasm4pm composes breeds together. ``meta_reasoning`` is the one
breed built for cross-breed arbitration, but it works entirely off
**host-injected** flattened facts (``breed:<id>:conclusion`` /
``breed:<id>:confidence``) -- the composition has to happen outside wasm4pm.

``guard_executor.py`` (built and hammer-validated earlier this session) is
exactly that missing host: real, proven concurrency
(``max_workers``, a deterministic trace order under genuine thread
parallelism -- fixed this session after property-based testing caught it
leaking real scheduling nondeterminism), and a first-class
:class:`~autofde_lab.powl.guard_executor.ExecutionContext` for accumulating
cross-atom state. This module is the bridge: it builds a real
:class:`~autofde_lab.powl.algebra.PartialOrder` of one ``Atom`` per real breed
member, executes it with real concurrency, and lets wasm4pm's own real
``meta_reasoning`` breed do the arbitration -- never inventing a second,
competing arbitration algorithm here.

Domain-agnostic, per this codebase's own established law
----------------------------------------------------------
This module is **wasm4pm-aware** (it calls
:func:`autofde_lab.receipts.wasm4pm_cognition.run_cognition` and knows the
real ``breed:<id>:conclusion``/``confidence`` fact convention -- the same
layering :mod:`autofde_lab.reasoning.hearsay_cross_check` already
established for a single breed), but ``guard_executor.py`` itself is
completely untouched and stays unaware of wasm4pm entirely. Callers choose
*which* breeds to ensemble and how to translate their own task data into
each breed's real wire format (:class:`BreedEnsembleMember.build_input`) --
this module owns only the generic concurrent-invoke / accumulate / arbitrate
/ honest-partial-availability mechanics.

Real, not fabricated, confidence
-----------------------------------
:class:`~autofde_lab.receipts.wasm4pm_cognition.CognitionEvidence` carries no
universal normalized confidence field (it varies per breed). This module
derives one, generically, from the real ``BreedOutput.candidates`` array
every breed shares (``Candidate{id,score,eliminated,...}``, confirmed
present across the wasm4pm wire contract): the highest surviving
(non-eliminated) candidate's real ``score``. This is a real, stated,
conservative approximation -- a member whose real output carries no
candidates array derives confidence ``0.0`` (never fabricated as 1.0, never
silently dropped).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from autofde_lab.powl.algebra import Atom, PartialOrder
from autofde_lab.powl.guard_executor import ExecutionContext, execute
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder, execute_with_ocel
from autofde_lab.receipts.wasm4pm_cognition import (
    CognitionEvidence,
    NoEvidence,
    Wasm4pmCognitionUnavailable,
    run_cognition,
)

__all__ = ["BreedEnsembleMember", "BreedEnsembleResult", "run_breed_ensemble"]

#: The real meta_reasoning conflict-divergence threshold (CONF_DIVERGENCE in
#: meta_reasoning.rs) is 0.5 -- matched here only as the default so a caller
#: not naming an explicit threshold gets the same real bar wasm4pm's own
#: breed itself uses for "this counts as meaningful disagreement", not an
#: arbitrarily different number.
_DEFAULT_RESOLUTION_THRESHOLD = 0.5

#: The single shared decision key every member's conclusion is posted under
#: -- meta_reasoning treats a bare (no "key=") conclusion value as key
#: "decision" by its own real convention (confirmed via source read of
#: parse_reports), so every member competing under this one key is exactly
#: how a single overall verdict gets arbitrated across N members.
_DECISION_KEY = "decision"


def _run_coroutine_sync(coro: Any) -> Any:
    """Run a real coroutine to completion from a synchronous callable
    (`guard_executor.execute`'s `atom_invoker` contract is synchronous),
    without colliding with a caller's already-running event loop.

    Duplicated from (not imported from) `gymact_dspy_react.py`'s identical
    helper -- that module's own docstring states the same three-line
    function is not worth coupling separate modules together for; this
    module additionally needs it safe to call from multiple concurrent
    threads at once (`guard_executor`'s real `max_workers>1` path), which a
    fresh `ThreadPoolExecutor`-per-call already guarantees (no shared event
    loop across calls).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@dataclass(frozen=True, slots=True)
class BreedEnsembleMember:
    """One real wasm4pm breed to include in the ensemble.

    ``build_input`` is a zero-arg closure the caller pre-binds with whatever
    task-specific data that breed's real wire format needs (facts/rules/
    candidates/etc, per that breed's own real contract) -- this module never
    inspects or constrains its contents, matching `guard_executor.py`'s own
    "atom_invoker is opaque" design.
    """

    breed: str
    build_input: Callable[[], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class BreedEnsembleResult:
    """One real ensemble run's outcome -- full raw signal AND the arbitrated
    verdict, never just one or the other."""

    #: Every member that produced real, usable evidence (a real `selected`
    #: value) -- a member that was unavailable, produced no evidence, or
    #: produced no `selected` value is simply absent here, named honestly,
    #: never faked as agreement.
    member_evidence: Mapping[str, CognitionEvidence]
    #: The real `meta_reasoning` breed's own output, or `None` if fewer than
    #: 2 members produced usable evidence (arbitration genuinely needs ≥2
    #: real opinions -- never fabricated from one).
    arbitrated: CognitionEvidence | None
    #: The real, normalized winning weight behind `resolved` (winning
    #: weight for the shared decision key, divided by the total confidence
    #: summed across every usable member) -- `None` when `arbitrated` is
    #: `None`.
    resolution_weight: float | None
    #: Whether `resolution_weight >= resolution_threshold` -- the one
    #: legitimate bare bool here: a real, external-to-this-module threshold
    #: outcome, same justification as `guard_executor.ExecutionStep.failed`.
    resolved: bool = field(default=False)


def _derive_confidence(evidence: CognitionEvidence) -> float:
    """Real, generic, conservative confidence derivation -- see module
    docstring's "Real, not fabricated, confidence" section."""
    candidates = evidence.raw_output.get("candidates", [])
    scores = [
        float(c.get("score", 0.0))
        for c in candidates
        if isinstance(c, dict) and not c.get("eliminated", False)
    ]
    return max(scores) if scores else 0.0


def _run_one_member(member: BreedEnsembleMember, timeout_s: float) -> CognitionEvidence | None:
    """Real single-member invocation. Returns `None` (never raises) for a
    genuinely unavailable breed or a run that produced no trustworthy
    evidence -- both are real, honest "this member contributed nothing"
    outcomes, not distinguished further here since either way this member
    is simply absent from the ensemble."""
    try:
        evidence = _run_coroutine_sync(run_cognition(member.breed, timeout_s=timeout_s, **member.build_input()))
    except (Wasm4pmCognitionUnavailable, NoEvidence):
        return None
    if evidence.selected is None:
        return None
    return evidence


def run_breed_ensemble(
    members: Sequence[BreedEnsembleMember],
    *,
    resolution_threshold: float = _DEFAULT_RESOLUTION_THRESHOLD,
    max_workers: int | None = None,
    timeout_s: float = 15.0,
    recorder: OcelExecutionRecorder | None = None,
) -> BreedEnsembleResult:
    """Run every real `member` concurrently via the real POWL runner, then
    arbitrate via wasm4pm's own real `meta_reasoning` breed.

    Raises `ValueError` for `len(members) == 0` (nothing to ensemble). For
    `len(members) == 1`, runs that one breed directly -- no `PartialOrder`
    (which requires >=2 children by `algebra.py`'s own construction law), no
    concurrency, no arbitration possible -- with `resolved` computed
    straight from that one member's own derived confidence. This is a real,
    narrower, explicitly-named degenerate case, never silently presented as
    a real ensemble verdict (`arbitrated` stays `None`).
    """
    if not members:
        raise ValueError("run_breed_ensemble requires at least one member")

    if len(members) == 1:
        evidence = _run_one_member(members[0], timeout_s)
        if evidence is None:
            return BreedEnsembleResult(member_evidence={}, arbitrated=None, resolution_weight=None, resolved=False)
        confidence = _derive_confidence(evidence)
        return BreedEnsembleResult(
            member_evidence={members[0].breed: evidence},
            arbitrated=None,
            resolution_weight=None,
            resolved=confidence >= resolution_threshold,
        )

    node = PartialOrder(children=tuple(Atom(label=m.breed, consequence="READ") for m in members))
    context = ExecutionContext()

    def atom_invoker(atom: Atom, ctx: ExecutionContext) -> None:
        member = next(m for m in members if m.breed == atom.label)
        evidence = _run_one_member(member, timeout_s)
        if evidence is None:
            return
        confidence = _derive_confidence(evidence)
        ctx.attributes[atom.label] = evidence
        ctx.attributes[f"breed:{atom.label}:conclusion"] = evidence.selected
        ctx.attributes[f"breed:{atom.label}:confidence"] = confidence

    if recorder is not None:
        execute_with_ocel(
            node,
            guard_evaluator=lambda name, args: True,  # PartialOrder has no ChoiceGraph -- never consulted
            atom_invoker=atom_invoker,
            max_choice_transitions=1,
            max_workers=max_workers or len(members),
            context=context,
            recorder=recorder,
        )
    else:
        execute(
            node,
            guard_evaluator=lambda name, args: True,  # PartialOrder has no ChoiceGraph -- never consulted
            atom_invoker=atom_invoker,
            max_choice_transitions=1,
            max_workers=max_workers or len(members),
            context=context,
        )

    member_evidence: dict[str, CognitionEvidence] = {
        m.breed: context.attributes[m.breed] for m in members if m.breed in context.attributes
    }

    if len(member_evidence) < 2:
        return BreedEnsembleResult(member_evidence=member_evidence, arbitrated=None, resolution_weight=None, resolved=False)

    meta_facts = []
    total_confidence = 0.0
    for breed_id in member_evidence:
        conclusion = context.attributes[f"breed:{breed_id}:conclusion"]
        confidence = context.attributes[f"breed:{breed_id}:confidence"]
        meta_facts.append({"key": f"breed:{breed_id}:conclusion", "value": str(conclusion)})
        meta_facts.append({"key": f"breed:{breed_id}:confidence", "value": str(confidence)})
        total_confidence += confidence

    try:
        arbitrated = _run_coroutine_sync(run_cognition("meta_reasoning", facts=meta_facts, timeout_s=timeout_s))
    except (Wasm4pmCognitionUnavailable, NoEvidence):
        return BreedEnsembleResult(member_evidence=member_evidence, arbitrated=None, resolution_weight=None, resolved=False)

    winning_weight = 0.0
    for fact in arbitrated.raw_output.get("facts", []):
        if isinstance(fact, dict) and fact.get("key") == f"meta:weight:{_DECISION_KEY}":
            try:
                winning_weight = float(fact.get("value", 0.0))
            except (TypeError, ValueError):
                winning_weight = 0.0
            break

    resolution_weight = (winning_weight / total_confidence) if total_confidence > 0 else 0.0
    return BreedEnsembleResult(
        member_evidence=member_evidence,
        arbitrated=arbitrated,
        resolution_weight=resolution_weight,
        resolved=resolution_weight >= resolution_threshold,
    )
