# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.reasoning.breed_ensemble`.

Real collaborators throughout: real subprocess calls to `~/wasm4pm`'s real
built Node CLI (no GROQ/paid API involved -- local subprocess only, same
gating pattern as `tests/reasoning/test_hearsay_cross_check_chicago.py`),
and the real, unmodified `guard_executor.execute()`.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import time

import pytest

from autofde_lab.ocel.object_centric_conformance import check_object_centric_conformance
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder
from autofde_lab.reasoning.breed_ensemble import BreedEnsembleMember, run_breed_ensemble
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

def test_zero_members_raises_value_error() -> None:
    with pytest.raises(ValueError):
        run_breed_ensemble([])


@requires_real_wasm4pm_cli
def test_single_member_runs_directly_with_no_arbitration() -> None:
    """The real, explicitly-narrower degenerate case: `arbitrated` stays
    `None` even when the one member itself produced real evidence."""
    result = run_breed_ensemble([BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT)])
    assert "hearsay" in result.member_evidence
    assert result.member_evidence["hearsay"].selected == "hypothesis:oom kill"
    assert result.arbitrated is None
    assert result.resolution_weight is None


@requires_real_wasm4pm_cli
def test_real_concurrent_two_member_ensemble_is_genuinely_faster_than_serial() -> None:
    """Real wall-clock proof of concurrency at this composition layer.
    (`guard_executor.py`'s own concurrency mechanism is already proven with
    real distinct thread identifiers in `test_guard_executor_property_based.py`
    -- this test proves the composition built on top of it genuinely uses
    that mechanism, via real measured timing, matching
    `scripts/powl_runner_concurrency_benchmark.py`'s own methodology for a
    black-box caller that cannot instrument the internal atom_invoker
    directly.)"""
    members = [
        BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
        BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
    ]

    # Both variants run the SAME two members and pay the SAME real,
    # necessarily-serial `meta_reasoning` arbitration call afterward (an
    # earlier version of this test compared against a baseline that skipped
    # arbitration entirely -- an apples-to-oranges ~2.4s discrepancy this
    # session caught via direct instrumentation, not a real concurrency
    # regression). Isolating `max_workers=1` vs `max_workers=2` on the
    # identical two-member ensemble isolates just the real gathering-phase
    # speedup.
    def _run_once(max_workers: int) -> float:
        start = time.perf_counter()
        run_breed_ensemble(members, max_workers=max_workers, timeout_s=20.0)
        return time.perf_counter() - start

    serial_samples = sorted(_run_once(1) for _ in range(3))
    concurrent_samples = sorted(_run_once(2) for _ in range(3))
    serial_median = serial_samples[1]
    concurrent_median = concurrent_samples[1]

    assert concurrent_median < serial_median


@requires_real_wasm4pm_cli
def test_real_arbitration_resolves_a_genuine_disagreement() -> None:
    """Two real members whose real conclusions genuinely differ
    (`hearsay` -> `"hypothesis:oom kill"`, `abductive_ibe` -> `"oom-kill"`) --
    `meta_reasoning`'s real confidence-weighted vote must pick a real
    winner, never asserted from documentation of its algorithm alone."""
    members = [
        BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
        BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
    ]
    result = run_breed_ensemble(members, max_workers=2, timeout_s=20.0)

    assert set(result.member_evidence) == {"hearsay", "abductive_ibe"}
    assert result.member_evidence["hearsay"].selected != result.member_evidence["abductive_ibe"].selected
    assert result.arbitrated is not None
    # abductive_ibe's real, non-zero derived confidence dominates hearsay's
    # real, honestly-zero one (hearsay's BreedOutput carries no populated
    # `candidates` array in this fixture -- a real, stated property of the
    # generic candidate-based confidence derivation, not a test artifact).
    assert result.arbitrated.selected == "decision=oom-kill"
    assert result.resolution_weight is not None
    assert result.resolution_weight > 0.9


@requires_real_wasm4pm_cli
def test_fewer_than_two_usable_members_never_fabricates_arbitration() -> None:
    """One real member plus one deliberately-invalid breed name (real
    `NoEvidence`/rejection) -- fewer than 2 usable members must never
    produce a fabricated `arbitrated` verdict."""
    members = [
        BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
        BreedEnsembleMember(breed="not-a-real-breed-name", build_input=lambda: {}),
    ]
    result = run_breed_ensemble(members, max_workers=2, timeout_s=20.0)

    assert set(result.member_evidence) == {"hearsay"}
    assert result.arbitrated is None
    assert result.resolution_weight is None
    assert result.resolved is False


@requires_real_wasm4pm_cli
def test_resolution_threshold_is_a_real_caller_configurable_bar() -> None:
    members = [
        BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
        BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
    ]
    lenient = run_breed_ensemble(members, max_workers=2, resolution_threshold=0.1, timeout_s=20.0)
    # This fixture's real winning weight lands at ~1.0 (hearsay's generic
    # confidence derivation is honestly 0.0 here -- see the arbitration
    # test above), so an unreachable threshold (>1.0, real floating-point
    # rounding can otherwise push a ~1.0 ratio either side of a threshold
    # sitting right at the boundary) is what proves the bar is real and
    # caller-configurable without relying on float-boundary luck.
    strict = run_breed_ensemble(members, max_workers=2, resolution_threshold=1.5, timeout_s=20.0)

    assert lenient.resolved is True
    assert strict.resolved is False


@requires_real_wasm4pm_cli
def test_real_ocel_v2_trace_is_produced_when_a_recorder_is_supplied_and_conforms() -> None:
    """Closes the real gap the van der Aalst-style audit found: this real,
    admitted, concurrent POWL process ran with zero OCEL trace anywhere.
    Confirm a real OCEL 2.0 log is produced when a `recorder` is supplied,
    and independently passes `check_object_centric_conformance`."""
    recorder = OcelExecutionRecorder(execution_id="breed-ensemble-run-001")
    members = [
        BreedEnsembleMember(breed="hearsay", build_input=lambda: _HEARSAY_INPUT),
        BreedEnsembleMember(breed="abductive_ibe", build_input=lambda: _IBE_INPUT),
    ]

    result = run_breed_ensemble(members, max_workers=2, timeout_s=20.0, recorder=recorder)
    assert result.member_evidence  # real evidence was produced

    log = recorder.close()
    assert len(log.events) == 2

    intended = {"breed-ensemble-run-001": ("hearsay", "abductive_ibe")}
    conformance = check_object_centric_conformance(log, intended_traces_by_object_id=intended)
    assert conformance.all_conform is True
    assert conformance.overall_fitness == 1.0
