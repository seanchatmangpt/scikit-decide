"""Chicago-style tests for Level 4 control-flow conformance.

Real collaborators throughout: the real ``wpm`` binary as a real subprocess, the real
committed ``.pnml`` on disk, real crown trial evidence directories on disk. No mocks, no
stubs, no monkeypatching. Assertions are on final state -- the real numbers ``wpm``
printed and the real activity sequences the trials left behind.

Skips are named and structural, never silent substitutions:
``BLOCKED:WPM_BINARY_ABSENT`` when no built ``wpm`` exists, and
``BLOCKED:NO_CROWN_TRIAL_EVIDENCE`` when this checkout carries no trial directories.
Per ``.claude/rules/absence-is-not-evidence.md`` neither absence is treated as a pass.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from autofde_lab.ocel.level4_process_fitness import (
    GOLDEN_LOG_PATH,
    INTENDED_MODEL_PATH,
    check_trial_fitness,
    golden_baseline,
    golden_model_metric_swap_witness,
    level4_trace_to_wasm4pm_json,
    trial_activity_sequence,
)
from autofde_lab.ocel.wasm4pm_bridge import Wasm4pmUnavailable, resolve_wpm_binary

REPO_ROOT = Path(__file__).resolve().parents[2]
CROWN_DIR = REPO_ROOT / "docs" / "evidence" / "crown1" / "attempt4"


def _wpm_present() -> bool:
    try:
        resolve_wpm_binary()
    except Wasm4pmUnavailable:
        return False
    return True


def _trial_dirs() -> list[Path]:
    if not CROWN_DIR.is_dir():
        return []
    return sorted(p for p in CROWN_DIR.glob("realtrial_*") if p.is_dir())


requires_wpm = pytest.mark.skipif(
    not _wpm_present(), reason="BLOCKED:WPM_BINARY_ABSENT -- no built 'wpm' on this machine"
)
requires_trials = pytest.mark.skipif(
    not _trial_dirs(),
    reason=f"BLOCKED:NO_CROWN_TRIAL_EVIDENCE -- no realtrial_* dirs under {CROWN_DIR}",
)


def test_committed_model_and_golden_log_are_on_disk() -> None:
    """The model is committed, not mined at test time."""
    assert INTENDED_MODEL_PATH.is_file(), INTENDED_MODEL_PATH
    assert GOLDEN_LOG_PATH.is_file(), GOLDEN_LOG_PATH
    pnml = INTENDED_MODEL_PATH.read_text(encoding="utf-8")
    # Every Level 4 activity must have a real transition in the committed net, or the
    # model silently cannot see part of the chain.
    from autofde_lab.hub.domain.gym_procedure.level4_ocel import LEVEL4_EVENT_TYPES

    for activity in LEVEL4_EVENT_TYPES:
        assert f'<text>{activity}</text>' in pnml, f"no transition for {activity}"
    assert "<finalmarkings>" in pnml and "<initialMarking>" in pnml


@requires_wpm
def test_golden_baseline_is_the_real_reachable_ceiling_and_is_not_one() -> None:
    """Real replay of the committed golden log against the committed model.

    Pins the measured defect: the ILP-mined net does NOT perfectly replay the log it was
    mined from, so 1.0 is unreachable and must never be used as the comparison point.
    """
    report = asyncio.run(golden_baseline())
    assert report.total_cases == 6
    assert 0.0 < report.avg_fitness < 1.0, report.avg_fitness
    assert report.avg_fitness == pytest.approx(0.8685, abs=1e-4)
    # Constant source/sink token artifact on every trace -- the reason fitness < 1.
    assert report.deviations, "expected the golden log itself to deviate"
    assert all(d.tokens_missing == 2 and d.tokens_remaining == 3 for d in report.deviations)
    assert report.precision is not None and report.generalization is not None


@requires_wpm
def test_wpm_discover_mislabels_simplicity_and_fitness() -> None:
    """Defect 1, pinned by real runs so an upstream fix fails loudly instead of drifting.

    ``discover``'s "Simplicity" row is byte-for-byte ``conformance``'s avg fitness,
    because ``wasm4pm-cli`` destructures ``(net, fitness, precision)`` as
    ``(net, simplicity, fitness)``.
    """
    discover_simplicity, conformance_avg_fitness = asyncio.run(
        golden_model_metric_swap_witness()
    )
    assert discover_simplicity == pytest.approx(conformance_avg_fitness, abs=1e-4)


@requires_trials
def test_real_trial_activity_sequences_are_level4_vocabulary() -> None:
    """The observed sequences come from real trial artifacts, in observed order.

    Every trial starts at ``TaskAdmitted``; **most do not finish the chain.** Of the ten
    crown trials on disk, three reach ``ReplayCompleted``, three stop at
    ``PlanConstructed`` and four stop at ``ProbeExecuted`` after only 3-4 events. That is
    real truncation in the evidence, not a defect in this measurement, and it is the
    dominant source of the low fitness reported below -- asserted here so a later run
    that silently completes more trials shows up as a failure to re-derive.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_ocel import LEVEL4_EVENT_TYPES

    lasts: list[str] = []
    for d in _trial_dirs():
        seq = trial_activity_sequence(d)
        assert seq, f"empty activity sequence for {d.name}"
        assert set(seq) <= set(LEVEL4_EVENT_TYPES), set(seq) - set(LEVEL4_EVENT_TYPES)
        assert seq[0] == "TaskAdmitted", (d.name, seq[0])
        lasts.append(seq[-1])

    assert lasts.count("ReplayCompleted") == 3
    assert lasts.count("PlanConstructed") == 3
    assert lasts.count("ProbeExecuted") == 4


@requires_trials
def test_intra_receipt_ordering_is_unrecorded_wherever_actuation_happened() -> None:
    """UNKNOWN, not conforming and not deviating: the order simply is not recorded.

    ``ActuationOpened``/``ActuationClosed``/``ReceiptEmitted`` share one timestamp, so
    on any trial that actually actuated the two tie-breaks produce different sequences
    from the same evidence. That difference existing is the proof the ordering is absent
    from the data. On trials truncated before actuation there is nothing to tie, and the
    tie-break correctly makes no difference -- which is why this is asserted per-trial
    against whether the trial actuated, not globally.
    """
    actuated_and_differs = 0
    for d in _trial_dirs():
        by_id = trial_activity_sequence(d, tie_break="id")
        by_chain = trial_activity_sequence(d, tie_break="chain")
        assert sorted(by_id) == sorted(by_chain), "tie-break must permute, never add/drop"
        if "ActuationOpened" in by_id:
            assert by_id != by_chain, (
                f"{d.name} actuated but the tie-break made no difference; intra-receipt "
                "ordering may now be recorded and this test's premise needs re-deriving"
            )
            actuated_and_differs += 1
        else:
            assert by_id == by_chain, f"{d.name} never actuated but ordering still moved"
    assert actuated_and_differs == 3


def test_wasm4pm_json_keeps_only_concept_name() -> None:
    """The honest ceiling, asserted rather than only documented.

    Everything object-shaped is dropped on the way into wasm4pm, which is why a high
    fitness score cannot be Level 4 standing.
    """
    doc = level4_trace_to_wasm4pm_json([("case-a", ["TaskAdmitted", "SessionStarted"])])
    (trace,) = doc["traces"]
    assert [e["attributes"][0]["key"] for e in trace["events"]] == [
        "concept:name",
        "concept:name",
    ]
    assert all(len(e["attributes"]) == 1 for e in trace["events"])
    assert "objects" not in doc and "relationships" not in doc


@requires_wpm
@requires_trials
def test_real_trials_against_committed_model_are_scored_and_deviate() -> None:
    """The headline measurement, run for real over every crown trial on disk."""
    dirs = _trial_dirs()
    result = asyncio.run(check_trial_fitness(dirs))

    assert result.tie_break == "id"
    assert result.report.total_cases == len(dirs)
    assert result.case_ids == tuple(d.name for d in dirs)
    assert 0.0 < result.report.avg_fitness < result.baseline.avg_fitness
    assert result.report.conforming_cases == 0, (
        "if this ever becomes non-zero, note the golden log itself scores 0 conforming "
        "cases too -- see the module docstring's defect 2 before reading it as success"
    )
    assert 0.0 < result.fitness_vs_baseline < 1.0

    # Deviations are real and attributable to real trials by position, not by name.
    assert len(result.report.deviations) == len(dirs)
    for dev in result.report.deviations:
        assert result.case_ids[int(dev.case_id)] in {d.name for d in dirs}
        assert dev.tokens_missing > 0 or dev.tokens_remaining > 0


@requires_wpm
@requires_trials
def test_chain_tie_break_is_model_biased_and_scores_no_worse() -> None:
    """The diagnostic split: ordering ties into the model's shape cannot hurt fitness.

    This is exactly why a ``"chain"`` number is not evidence -- it is constructed to
    favour the model. Asserted so the bias is visible in test output, not hidden.
    """
    dirs = _trial_dirs()
    neutral = asyncio.run(check_trial_fitness(dirs, tie_break="id"))
    biased = asyncio.run(check_trial_fitness(dirs, tie_break="chain"))
    assert biased.report.avg_fitness >= neutral.report.avg_fitness
