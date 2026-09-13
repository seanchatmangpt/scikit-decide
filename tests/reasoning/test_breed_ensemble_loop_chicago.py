# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.reasoning.breed_ensemble_loop`.

Structural tests are LLM-free (a real, hand-written `interpret` callable
standing in for a live LM -- matching `test_sre_mitigation_portfolio_chicago.py`'s
own `_RealVariedMitigationProcessModule` pattern of a real callable/Module,
never a mock). One live test makes a real Groq call, `skipif`-gated on
`GROQ_API_KEY`, matching every other DSPy test in this repo.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import os

import dspy
import pytest

from autofde_lab.ocel.object_centric_conformance import check_object_centric_conformance
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder
from autofde_lab.powl.refusals import PowlError, PowlRefusal
from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.breed_ensemble import BreedEnsembleMember
from autofde_lab.reasoning.breed_ensemble_loop import _build_loop_graph, run_breed_ensemble_until_resolved
from autofde_lab.receipts.wasm4pm_cognition import Wasm4pmCognitionUnavailable, resolve_wpm_cognition_entry


def _hearsay_cli_available() -> bool:
    try:
        resolve_wpm_cognition_entry()
    except Wasm4pmCognitionUnavailable:
        return False
    return True


requires_real_wasm4pm_cli = pytest.mark.skipif(
    not _hearsay_cli_available(),
    reason=(
        "the built ~/wasm4pm apps/wasm4pm Node CLI is not available in this "
        "environment -- a real subprocess call is required and no mock "
        "substitute is used per .claude/rules/testing-chicago-style.md."
    ),
)

_HEARSAY_INPUT = {
    "facts": [{"key": "fact", "value": "pod crashlooping"}],
    "rules": [
        {"id": "r0", "premise": ["fact-hypotheses"], "conclusion": "hypothesis:oom kill", "certainty": 1.0},
    ],
}
_IBE_INPUT = {
    "candidates": [{"id": "oom-kill", "score": 0.0, "eliminated": False}],
    "facts": [{"key": "evidence", "value": "pod_restarts_spike"}],
    "rules": [{"id": "r0", "premise": ["oom-kill"], "conclusion": "pod_restarts_spike", "certainty": 1.0}],
}


# ---------------------------------------------------------------------------
# Structural: the real ChoiceGraph shape is a real, admitted POWL 2.0 model
# ---------------------------------------------------------------------------


def test_loop_graph_is_a_real_admitted_model() -> None:
    graph = _build_loop_graph()
    validate_model(graph)  # raises PowlError on any structural refusal
    assert len(graph.children) == 5


def test_loop_back_edge_targets_run_ensemble_never_start() -> None:
    """Per POWL 2.0's no-incoming-edge-to-Start rule, the real loop-back
    edge from `interpret_via_dspy` must target `run_ensemble` (index 2),
    never `Start` (index 0)."""
    graph = _build_loop_graph()
    loop_back_edges = [e for e in graph.edges if e.src == 4]  # interpret_via_dspy's outgoing edge
    assert len(loop_back_edges) == 1
    assert loop_back_edges[0].dst == 2  # run_ensemble, not Start


# ---------------------------------------------------------------------------
# Structural: guard dispatch and atom dispatch, real fake `interpret`
# ---------------------------------------------------------------------------


@requires_real_wasm4pm_cli
def test_single_round_resolves_immediately_when_the_ensemble_already_resolves() -> None:
    """Two real, genuinely-usable members on round 1 -- the loop must reach
    `causal_closure`... err, `ensemble_resolved` and stop without ever
    calling `interpret`."""
    call_count = {"interpret": 0}

    def never_called_interpret(**kwargs):
        call_count["interpret"] += 1
        raise AssertionError("interpret must not be called when round 1 already resolves")

    def build_members(_task_context: str):
        return [
            BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
            BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
        ]

    result, trajectory = run_breed_ensemble_until_resolved(
        build_members=build_members,
        initial_task_context="diagnose pod crash",
        interpret=never_called_interpret,
        resolution_threshold=0.1,
        max_rounds=5,
    )

    assert result.resolved is True
    assert trajectory == []
    assert call_count["interpret"] == 0


@requires_real_wasm4pm_cli
def test_real_ocel_v2_trace_is_produced_when_a_recorder_is_supplied_and_conforms() -> None:
    """Closes the real gap the van der Aalst-style audit found: this real,
    admitted, cyclic-`ChoiceGraph` process ran with zero OCEL trace
    anywhere. Confirm a real OCEL 2.0 log is produced when a `recorder` is
    supplied, and independently passes `check_object_centric_conformance`."""

    def build_members(_task_context: str):
        return [
            BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
            BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
        ]

    recorder = OcelExecutionRecorder(execution_id="breed-ensemble-loop-run-001")

    result, trajectory = run_breed_ensemble_until_resolved(
        build_members=build_members,
        initial_task_context="diagnose pod crash",
        resolution_threshold=0.1,
        max_rounds=5,
        recorder=recorder,
    )

    assert result.resolved is True
    assert trajectory == []  # resolved round 1 -- interpret_via_dspy never ran

    log = recorder.close()
    assert len(log.events) == 1  # only the real Atom "run_ensemble" -- decide is Silent, never an event

    intended = {"breed-ensemble-loop-run-001": ("run_ensemble",)}
    conformance = check_object_centric_conformance(log, intended_traces_by_object_id=intended)
    assert conformance.all_conform is True
    assert conformance.overall_fitness == 1.0


@requires_real_wasm4pm_cli
def test_real_two_round_loop_interprets_an_inconclusive_first_round() -> None:
    """Round 1: a single-member ensemble (the real, degenerate `len==1`
    case -- guaranteed `resolved=False` since `arbitrated` stays `None`).
    Round 2 (after a real, hand-written `interpret` call -- not an LM):
    a real two-member ensemble that resolves."""
    calls = {"n": 0}

    def build_members(_task_context: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return [BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT)]
        return [
            BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
            BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
        ]

    def real_interpret(**kwargs) -> dspy.Prediction:
        # A real, hand-written callable standing in for a live LM --
        # asserts it received the real round-1 data, then produces a real
        # reframed context for round 2.
        assert kwargs["arbitrated_conclusion"] == "none"  # round 1 had <2 usable members
        assert kwargs["round_index"] == 0
        return dspy.Prediction(
            interpretation="round 1 had only one usable member; widening the ensemble",
            next_round_task_context="diagnose pod crash (widened)",
        )

    result, trajectory = run_breed_ensemble_until_resolved(
        build_members=build_members,
        initial_task_context="diagnose pod crash",
        interpret=real_interpret,
        resolution_threshold=0.1,
        max_rounds=5,
    )

    assert calls["n"] == 2
    assert len(trajectory) == 1
    assert result.resolved is True
    assert result.arbitrated is not None


def test_exhausting_max_rounds_without_resolving_is_a_typed_refusal_not_a_silent_guess() -> None:
    """A real `interpret` that never produces a resolvable ensemble (the
    real `build_members` always returns a single, never-usable breed name)
    must raise `TRANSITION_BUDGET_EXHAUSTED`, never silently return a
    fabricated result."""

    def build_members(_task_context: str):
        return [BreedEnsembleMember(breed="not-a-real-breed-name", build_input=lambda: {})]

    def real_interpret(**kwargs) -> dspy.Prediction:
        return dspy.Prediction(interpretation="still nothing", next_round_task_context="try again")

    with pytest.raises(PowlError) as excinfo:
        run_breed_ensemble_until_resolved(
            build_members=build_members,
            initial_task_context="diagnose pod crash",
            interpret=real_interpret,
            resolution_threshold=0.1,
            max_rounds=2,
        )

    assert excinfo.value.refusal == PowlRefusal.TRANSITION_BUDGET_EXHAUSTED


# ---------------------------------------------------------------------------
# Live Groq: real dspy.ChainOfThought(InterpretBreedEnsemble) call
# ---------------------------------------------------------------------------

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used "
        "per .claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_groq_key
@requires_real_wasm4pm_cli
def test_live_interpret_via_dspy_reframes_an_inconclusive_round() -> None:
    """Real, live end-to-end: round 1's single-member ensemble is
    genuinely inconclusive; a real `dspy.ChainOfThought(InterpretBreedEnsemble)`
    call (real Groq LM) interprets it and produces a real
    `next_round_task_context`; round 2's real two-member ensemble
    resolves."""
    lm = dspy.LM("groq/openai/gpt-oss-120b", api_key=_GROQ_API_KEY, cache=False, max_tokens=8000)

    calls = {"n": 0}

    def build_members(_task_context: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return [BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT)]
        return [
            BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
            BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
        ]

    with dspy.context(lm=lm):
        result, trajectory = run_breed_ensemble_until_resolved(
            build_members=build_members,
            initial_task_context="diagnose a crash-looping pod",
            resolution_threshold=0.1,
            max_rounds=5,
        )

    assert calls["n"] == 2
    assert len(trajectory) == 1
    assert trajectory[0].next_round_task_context  # real, non-empty LM-produced text
    assert result.resolved is True
