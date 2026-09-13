# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the dogfood loop.

Real collaborators throughout: real archived trial directories under
``docs/evidence/crown1``, the real :class:`~autofde_lab.ocel.log.OcelLog`
projection and its real ``validate``, the real
:func:`~autofde_lab.hub.domain.gym_procedure.typed_induction.induce_typed_domain`,
the real receipt SQLite ledgers, and real files written to disk. Every
assertion is on final state -- parsed logs, computed digests, measured
divergences, written JSON -- never on "was this called".

No test double of any kind appears here. The evidence corpus is a real
committed artifact in this repository, so there is no collaborator that is
infeasible in-process and therefore no case for the one legitimate exception.

The corpus is skipped-with-a-name (never silently passed) if it is absent
from the checkout, per the same discipline the module itself applies to
absent trial artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.dogfood import (
    MIN_EPISODES_FOR_RANKING,
    AdvisorySignals,
    CandidateComparison,
    DisagreementRecord,
    EpisodeOcel,
    ModelObservationDivergence,
    Unknown,
    advisory_signals,
    compare_candidates_vs_committed,
    compare_discovered_model_vs_observed,
    ingest_episode,
    record_disagreement,
)

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "docs" / "evidence" / "crown1"


def _trial_dirs() -> list[Path]:
    return sorted(p for p in CORPUS.glob("attempt*/realtrial_*") if p.is_dir())


@pytest.fixture(scope="module")
def trials() -> list[Path]:
    dirs = _trial_dirs()
    if not dirs:
        pytest.skip(f"no archived crown trial directories under {CORPUS}")
    return dirs


@pytest.fixture(scope="module")
def actuated_trial(trials: list[Path]) -> Path:
    """A real trial that reached actuation and committed a plan."""
    for trial in trials:
        if (trial / "actuation" / "episode.ocel.json").is_file() and (
            trial / "actuation" / "commitment.ttl"
        ).is_file():
            return trial
    pytest.skip("no archived trial reached actuation with a commitment")


@pytest.fixture(scope="module")
def unactuated_trial(trials: list[Path]) -> Path:
    """A real trial that never reached actuation -- the honest-absence case."""
    for trial in trials:
        if not (trial / "actuation" / "episode.ocel.json").is_file():
            return trial
    pytest.skip("every archived trial reached actuation; no absence case to check")


# --- 1. ingest -------------------------------------------------------------


def test_ingest_episode_parses_and_validates_a_real_ocel(actuated_trial: Path) -> None:
    episode = ingest_episode(actuated_trial)
    assert isinstance(episode, EpisodeOcel)
    assert episode.structurally_valid is True, episode.validation_error
    assert episode.validation_error is None
    assert episode.n_events > 0
    assert episode.n_objects > 0
    assert episode.activity_counts.get("act", 0) > 0
    assert len(episode.digest) == 64
    assert episode.source.endswith("actuation/episode.ocel.json")

    # The digest is over the real projection and must be reproducible.
    assert ingest_episode(actuated_trial).digest == episode.digest

    # The parsed event count matches the raw document -- a real round trip,
    # not a number the module invented.
    raw = json.loads(Path(episode.source).read_text(encoding="utf-8"))
    assert episode.n_events == len(raw["events"])
    assert episode.n_objects == len(raw["objects"])


def test_ingest_episode_returns_named_unknown_when_no_ocel(
    unactuated_trial: Path,
) -> None:
    result = ingest_episode(unactuated_trial)
    assert isinstance(result, Unknown)
    assert result.status == "UNKNOWN"
    assert result.absent == (
        str(unactuated_trial / "actuation" / "episode.ocel.json"),
    )
    assert "Absent, not empty" in result.detail


def test_ingest_episode_unknown_on_a_directory_that_does_not_exist(
    tmp_path: Path,
) -> None:
    result = ingest_episode(tmp_path / "no_such_trial")
    assert isinstance(result, Unknown)
    assert result.absent and result.absent[0].endswith("episode.ocel.json")


# --- 2. the model's own error ---------------------------------------------


def test_model_vs_observed_measures_a_real_divergence(actuated_trial: Path) -> None:
    result = compare_discovered_model_vs_observed(actuated_trial)
    assert isinstance(result, ModelObservationDivergence)
    assert result.committed_plan, "an actuated trial must carry a committed plan"
    assert result.n_probes > 0

    # One divergence row per committed step, in plan order, naming the real action.
    assert len(result.per_action) == len(result.committed_plan)
    assert [d.action for d in result.per_action] == list(result.committed_plan)
    assert [d.step_index for d in result.per_action] == list(
        range(len(result.committed_plan))
    )

    # Every step is backed by a real receipt read out of the SQLite ledger.
    for divergence in result.per_action:
        assert divergence.observed_standing in {"ALIVE", "REFUSED", "BLOCKED", None}
        if divergence.observed_standing is not None:
            assert divergence.observed_pre_state_digest
            assert divergence.observed_post_state_digest

    # The receipt chain really is a chain: step N's post digest is step N+1's pre.
    linked = [d for d in result.per_action if d.observed_pre_state_digest]
    for earlier, later in zip(linked, linked[1:]):
        assert earlier.observed_post_state_digest == later.observed_pre_state_digest

    assert result.sources, "a measured result must name what it read"


def test_model_vs_observed_finds_the_derived_dimension_error(
    trials: list[Path],
) -> None:
    """The measured signal this loop exists for.

    Across the archived corpus, the induced ``TypedDomain`` predicts a final
    state that really does disagree with the observed one -- notably on
    ``solved``, which is derived from other dimensions and which no action
    sets unconditionally. This test asserts the loop *finds* that error, not
    that the error is absent.
    """
    mismatched: dict[str, int] = {}
    measured = 0
    for trial in trials:
        result = compare_discovered_model_vs_observed(trial)
        if not isinstance(result, ModelObservationDivergence):
            continue
        if result.observed_final_state is None:
            continue
        measured += 1
        for mismatch in result.final_state_mismatches:
            mismatched[str(mismatch["dimension"])] = (
                mismatched.get(str(mismatch["dimension"]), 0) + 1
            )
    if measured == 0:
        pytest.skip("no archived trial carries both a commitment and a final state")
    assert mismatched, (
        "the induced model is being reported as perfectly predictive across "
        f"{measured} real episodes -- that would be the suspicious result"
    )
    assert "solved" in mismatched


def test_model_vs_observed_unknown_without_a_commitment(
    unactuated_trial: Path,
) -> None:
    result = compare_discovered_model_vs_observed(unactuated_trial)
    assert isinstance(result, Unknown)
    assert result.absent
    assert any("commitment.ttl" in a or "typed_probe_log" in a for a in result.absent)


# --- 3. candidates vs committed -------------------------------------------


def test_candidates_vs_committed_reads_the_real_federation(
    actuated_trial: Path,
) -> None:
    result = compare_candidates_vs_committed(actuated_trial)
    assert isinstance(result, CandidateComparison)

    raw = json.loads((actuated_trial / "federation.json").read_text(encoding="utf-8"))
    assert result.n_planners_attempted == len(raw)
    assert len(result.candidates) == len(raw)
    assert {c.planner for c in result.candidates} == {a["planner"] for a in raw}
    assert sum(result.outcome_counts.values()) == len(raw)

    # produced_candidate is exactly "returned a non-empty plan" on real data.
    for candidate, attempt in zip(result.candidates, raw):
        assert candidate.produced_candidate is bool(attempt.get("plan"))
        assert candidate.plan == tuple(attempt.get("plan") or ())

    # Agreement is computed against the committed sequence in commitment.ttl.
    for planner in result.agreeing_planners:
        match = next(c for c in result.candidates if c.planner == planner)
        assert match.plan == result.committed_plan
    for planner in result.disagreeing_planners:
        match = next(c for c in result.candidates if c.planner == planner)
        assert match.plan and match.plan != result.committed_plan

    assert len(result.distinct_candidate_plans) == len(
        {c.plan for c in result.candidates if c.produced_candidate}
    )


def test_candidates_vs_committed_unknown_without_federation(tmp_path: Path) -> None:
    result = compare_candidates_vs_committed(tmp_path)
    assert isinstance(result, Unknown)
    assert result.absent == (str(tmp_path / "federation.json"),)


# --- 4. durable disagreement record ---------------------------------------


def test_record_disagreement_writes_a_real_readable_file(
    actuated_trial: Path, tmp_path: Path
) -> None:
    record = record_disagreement(actuated_trial, out_dir=tmp_path)
    assert isinstance(record, DisagreementRecord)

    destination = tmp_path / "dogfood" / "disagreement.json"
    assert destination.is_file()
    on_disk = json.loads(destination.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == record.run_id
    assert on_disk["resolution"] == record.resolution
    assert on_disk["written_to"] == str(destination)
    assert record.written_to == str(destination)

    comparison = compare_candidates_vs_committed(actuated_trial)
    assert isinstance(comparison, CandidateComparison)
    assert record.n_planners_attempted == comparison.n_planners_attempted
    assert record.n_distinct_candidate_plans == len(comparison.distinct_candidate_plans)
    assert record.disagreement_detected is (
        len(comparison.distinct_candidate_plans) > 1
    )
    assert record.resolution in {
        "NO_COMMITMENT",
        "COMMITTED_PLAN_FROM_TYPED_SEARCH_NO_PLANNER_MATCH",
    } or record.resolution.startswith("COMMITTED_PLAN_MATCHED_BY_")

    # The source artifact is untouched -- this loop reads, it does not rewrite.
    assert not (actuated_trial / "dogfood").exists()


def test_record_disagreement_propagates_unknown(tmp_path: Path) -> None:
    result = record_disagreement(tmp_path / "nothing", out_dir=tmp_path)
    assert isinstance(result, Unknown)
    assert not (tmp_path / "dogfood").exists()


# --- 5. advisory signals ---------------------------------------------------


def test_advisory_signals_refuses_a_ranking_below_the_floor(
    actuated_trial: Path,
) -> None:
    signals = advisory_signals([actuated_trial])
    assert isinstance(signals, AdvisorySignals)
    assert signals.n_episodes == 1
    assert signals.n_episodes < MIN_EPISODES_FOR_RANKING
    assert signals.planner_ranking == ()
    assert signals.ranking_refused is not None
    assert "MIN_EPISODES_FOR_RANKING" in signals.ranking_refused
    # Counts are still reported -- refusing to rank is not refusing to observe.
    assert signals.planner_agreement_counts


def test_advisory_signals_aggregates_the_real_corpus(trials: list[Path]) -> None:
    signals = advisory_signals(trials)
    assert isinstance(signals, AdvisorySignals)
    assert signals.n_trial_dirs == len(trials)
    assert 0 < signals.n_episodes <= signals.n_trial_dirs
    assert set(signals.per_trial_status) == {str(t) for t in trials}

    if signals.n_episodes >= MIN_EPISODES_FOR_RANKING:
        assert signals.ranking_refused is None
        assert signals.planner_ranking
        assert set(signals.planner_ranking) == set(signals.planner_agreement_counts)
        # The ranking really is ordered by observed agreement.
        matched = [
            signals.planner_agreement_counts[p]["matched_committed"]
            for p in signals.planner_ranking
        ]
        assert matched == sorted(matched, reverse=True)
    else:
        assert signals.ranking_refused is not None
        assert signals.planner_ranking == ()

    # Every counted attempt is real: totals match the federation files.
    total_attempts = sum(
        row["attempts"] for row in signals.planner_agreement_counts.values()
    )
    on_disk = sum(
        len(json.loads((t / "federation.json").read_text(encoding="utf-8")))
        for t in trials
        if (t / "federation.json").is_file()
    )
    assert total_attempts == on_disk

    # Trials that could not be measured are named, not silently dropped.
    unmeasured = [k for k, v in signals.per_trial_status.items() if v != "MEASURED"]
    for key in unmeasured:
        assert signals.per_trial_status[key].startswith("UNKNOWN: ")
    if unmeasured:
        assert signals.unresolved


def test_advisory_signals_unknown_when_no_episode_exists_anywhere(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "a"
    empty.mkdir()
    result = advisory_signals([empty])
    assert isinstance(result, Unknown)
    assert "zero verified episodes" in result.detail
    assert "absence of evidence" in result.detail
    assert result.absent


def test_advisory_signals_unknown_on_empty_input() -> None:
    result = advisory_signals([])
    assert isinstance(result, Unknown)
    assert result.absent == ("<trial_dirs>",)
