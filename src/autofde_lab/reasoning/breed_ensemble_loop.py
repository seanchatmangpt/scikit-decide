# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, admitted POWL v2 `ChoiceGraph` loop driving
:func:`autofde_lab.reasoning.breed_ensemble.run_breed_ensemble` round after
round, with a DSPy signature interpreting each inconclusive round and
reframing the task for the next one.

`run_breed_ensemble` is deliberately single-shot (per this session's own
YAGNI decision) -- this module is the separate, explicit place round-to-round
convergence lives, mirroring
`autofde_lab.reasoning.gymact_dspy_react.SreTroubleshootingDecisionBackend`'s
own established loop idiom exactly: a guarded, cyclic `ChoiceGraph` walked by
the real, LLM-free `guard_executor.execute()`, where the guard predicate
itself is a real, deterministic check (`state["last_result"].resolved`) --
never an LLM call inside the guard. The LLM's only role is interpreting *why*
a round didn't resolve and producing the next round's task framing; it never
arbitrates between breeds itself (`meta_reasoning` already does that, inside
`run_breed_ensemble`).
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import dspy

from autofde_lab.powl.algebra import Atom, ChoiceGraph, ChoiceGraphEdge, End, Guard, NodeId, Silent, Start
from autofde_lab.powl.guard_executor import execute
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder, execute_with_ocel
from autofde_lab.powl.refusals import PowlError, PowlRefusal
from autofde_lab.reasoning.breed_ensemble import BreedEnsembleMember, BreedEnsembleResult, run_breed_ensemble

__all__ = ["InterpretBreedEnsemble", "run_breed_ensemble_until_resolved"]


class InterpretBreedEnsemble(dspy.Signature):
    """Given one round's real breed-ensemble result, interpret why it did or
    didn't resolve and, if not, reframe the task for another round. Never
    asked to itself arbitrate between breeds -- that's meta_reasoning's
    real, already-computed job; this signature only interprets WHY a round
    was inconclusive and reframes the task (e.g. narrower hypothesis
    wording, an added discriminating fact) -- it never invents new breed
    opinions itself."""

    task_context: str = dspy.InputField(desc="free-text description of what's being decided this round")
    member_evidence_summary: str = dspy.InputField(
        desc="one line per real member: breed, conclusion, confidence"
    )
    arbitrated_conclusion: str = dspy.InputField(
        desc="meta_reasoning's real winning conclusion, or 'none' if fewer than 2 members produced usable evidence"
    )
    resolution_weight: str = dspy.InputField(desc="the real normalized winning weight, or 'n/a'")
    round_index: int = dspy.InputField()
    interpretation: str = dspy.OutputField(desc="a plain-language, real read of why this round did or didn't resolve")
    next_round_task_context: str = dspy.OutputField(
        desc="the reframed task_context to use for the next round's build_members call"
    )


def _summarize_evidence(result: BreedEnsembleResult) -> tuple[str, str, str]:
    lines = [
        f"{breed}: {evidence.selected!r}" for breed, evidence in result.member_evidence.items()
    ]
    member_evidence_summary = "\n".join(lines) if lines else "none"
    arbitrated_conclusion = result.arbitrated.selected if result.arbitrated is not None else "none"
    resolution_weight = f"{result.resolution_weight:.4f}" if result.resolution_weight is not None else "n/a"
    return member_evidence_summary, arbitrated_conclusion or "none", resolution_weight


def _build_loop_graph() -> ChoiceGraph:
    """`Start -> run_ensemble -> decide -> {End on ensemble_resolved | interpret_via_dspy -> run_ensemble}`
    -- mirrors `SreTroubleshootingDecisionBackend._build_investigation_graph()`'s
    own real shape: the loop-back edge targets `run_ensemble` (node index 2),
    never `Start`, per POWL 2.0's no-incoming-edge-to-Start rule."""
    return ChoiceGraph(
        children=(
            Start(),  # 0
            End(),  # 1
            Atom(label="run_ensemble", consequence="READ"),  # 2
            Silent(),  # 3 -- decide
            Atom(label="interpret_via_dspy", consequence="PURE"),  # 4
        ),
        edges=frozenset(
            [
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(3)),
                ChoiceGraphEdge(NodeId(3), NodeId(1), guard=Guard("ensemble_resolved")),
                ChoiceGraphEdge(NodeId(3), NodeId(4)),  # else: not resolved -- interpret and retry
                ChoiceGraphEdge(NodeId(4), NodeId(2)),  # loop back to run_ensemble, never Start
            ]
        ),
        start=0,
        end=1,
    )


def run_breed_ensemble_until_resolved(
    *,
    build_members: Callable[[str], Sequence[BreedEnsembleMember]],
    initial_task_context: str,
    interpret: Callable[..., dspy.Prediction] | None = None,
    resolution_threshold: float = 0.5,
    max_rounds: int = 5,
    recorder: OcelExecutionRecorder | None = None,
) -> tuple[BreedEnsembleResult, list[dspy.Prediction]]:
    """Drive `run_breed_ensemble` round after round via a real, admitted,
    guarded `ChoiceGraph`, using `interpret` (default:
    `dspy.ChainOfThought(InterpretBreedEnsemble)`) to reframe an inconclusive
    round's task context for the next one.

    `build_members(task_context) -> Sequence[BreedEnsembleMember]` is called
    fresh every round with the current (possibly DSPy-reframed) task
    context -- this module never inspects or constructs `BreedEnsembleMember`
    instances itself, matching `run_breed_ensemble`'s own "caller supplies
    the domain-specific parts" design.

    Bounded by `max_rounds` via the real `max_choice_transitions` mechanism
    -- exhausting it without resolving raises the real, existing
    `PowlError(PowlRefusal.TRANSITION_BUDGET_EXHAUSTED)`, never a silent
    "give up and guess". Returns `(final_result, interpretation_trajectory)`
    on success -- the trajectory is the real, ordered list of every real
    `dspy.Prediction` produced along the way, for a caller that wants to
    inspect why each round didn't resolve.
    """
    interpreter = interpret if interpret is not None else dspy.ChainOfThought(InterpretBreedEnsemble)

    state: dict[str, Any] = {
        "task_context": initial_task_context,
        "round_index": 0,
        "last_result": None,
    }
    trajectory: list[dspy.Prediction] = []

    def guard_evaluator(predicate_name: str, _predicate_args: dict) -> bool:
        if predicate_name == "ensemble_resolved":
            last_result: BreedEnsembleResult | None = state["last_result"]
            return last_result is not None and last_result.resolved
        return False

    def atom_invoker(atom: Atom) -> None:
        if atom.label == "run_ensemble":
            members = build_members(state["task_context"])
            state["last_result"] = run_breed_ensemble(members, resolution_threshold=resolution_threshold)
            return
        if atom.label == "interpret_via_dspy":
            last_result: BreedEnsembleResult = state["last_result"]
            member_evidence_summary, arbitrated_conclusion, resolution_weight = _summarize_evidence(last_result)
            prediction = interpreter(
                task_context=state["task_context"],
                member_evidence_summary=member_evidence_summary,
                arbitrated_conclusion=arbitrated_conclusion,
                resolution_weight=resolution_weight,
                round_index=state["round_index"],
            )
            trajectory.append(prediction)
            state["task_context"] = prediction.next_round_task_context
            state["round_index"] += 1
            return
        raise AssertionError(f"unreachable: unknown atom label {atom.label!r}")  # pragma: no cover

    graph = _build_loop_graph()
    # Each round is 2 real transitions (run_ensemble->decide, decide->interpret_via_dspy
    # or decide->End) plus the loop-back transition (interpret_via_dspy->run_ensemble) --
    # bound generously per round so max_rounds genuinely caps real rounds, not transitions.
    max_choice_transitions = 1 + max(1, max_rounds) * 3

    try:
        if recorder is not None:
            execute_with_ocel(
                graph,
                guard_evaluator=guard_evaluator,
                atom_invoker=atom_invoker,
                max_choice_transitions=max_choice_transitions,
                recorder=recorder,
            )
        else:
            execute(
                graph,
                guard_evaluator=guard_evaluator,
                atom_invoker=atom_invoker,
                max_choice_transitions=max_choice_transitions,
            )
    except PowlError as exc:
        if exc.refusal == PowlRefusal.TRANSITION_BUDGET_EXHAUSTED:
            raise PowlError(
                PowlRefusal.TRANSITION_BUDGET_EXHAUSTED,
                f"breed ensemble did not resolve within max_rounds={max_rounds}",
            ) from exc
        raise

    final_result: BreedEnsembleResult = state["last_result"]
    return final_result, trajectory
