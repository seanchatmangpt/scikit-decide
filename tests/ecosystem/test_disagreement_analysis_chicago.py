# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for :mod:`disagreement_analysis`, on real archived trials.

No test double of any kind appears here. Every test reads the real archived
crown artifacts under ``docs/evidence/crown1/`` from disk, runs the real
classifier over the real induced model, and asserts on the real returned
state. The reference trial is ``resource_flow`` seed ``3979297810``
(``attempt5``): 49 planners attempted, 13 produced candidates, 0 matched the
committed plan ``mine -> refine -> assemble -> burn_catalyst``, while the
induced model mispredicted ``dead_end`` and ``solved`` in the very episode it
authorized.

Trials whose evidence is absent from the checkout are skipped by a named
``pytest.mark.skipif`` -- never substituted with a fabricated fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.disagreement_analysis import (
    CAUSE_VOCABULARY,
    CorpusClassification,
    DisagreementClassification,
    NextExperiment,
    classify_corpus,
    classify_disagreement,
    next_discriminating_experiment,
)
from autofde_lab.hub.domain.gym_procedure.dogfood import (
    MIN_EPISODES_FOR_RANKING,
    Unknown,
    compare_candidates_vs_committed,
)

REPO = Path(__file__).resolve().parents[2]
CROWN = REPO / "docs" / "evidence" / "crown1"
REFERENCE = (
    CROWN / "attempt5" / "realtrial_3979297810_cfe99310-809b-478e-a72b-dff5965aa188"
)

requires_reference = pytest.mark.skipif(
    not (REFERENCE / "federation.json").is_file(),
    reason=f"archived reference trial absent from this checkout: {REFERENCE}",
)


def _all_trials() -> list[Path]:
    if not CROWN.is_dir():
        return []
    return sorted(p for p in CROWN.glob("attempt*/realtrial_*") if p.is_dir())


@pytest.fixture(scope="module")
def classification() -> DisagreementClassification:
    result = classify_disagreement(REFERENCE)
    assert isinstance(result, DisagreementClassification), result
    return result


@requires_reference
def test_reference_trial_counts_match_the_archived_federation(classification):
    """The classifier's own counts are re-derived from the real federation record."""
    federation = json.loads((REFERENCE / "federation.json").read_text())
    producing = [a for a in federation if a.get("plan")]

    assert classification.n_planners_attempted == len(federation) == 49
    assert classification.n_producing_candidates == len(producing) == 13
    assert classification.n_disagreeing == 13
    assert classification.committed_plan == (
        "mine",
        "refine",
        "assemble",
        "burn_catalyst",
    )

    comparison = compare_candidates_vs_committed(REFERENCE)
    assert comparison.agreeing_planners == ()
    assert len(comparison.disagreeing_planners) == 13


@requires_reference
def test_every_hypothesis_is_in_vocabulary_and_carries_a_real_citation(classification):
    """A named cause without an on-disk citation must not exist."""
    for hypothesis in classification.hypotheses:
        assert hypothesis.cause in CAUSE_VOCABULARY or hypothesis.cause.startswith(
            "UNKNOWN:"
        ), hypothesis.cause
        assert hypothesis.citations, hypothesis
        for citation in hypothesis.citations:
            assert Path(citation.artifact).exists(), citation
            assert citation.field and citation.value, citation


@requires_reference
def test_citations_quote_the_actual_federation_detail_verbatim(classification):
    """Each cited ``federation.json`` field really holds the cited value."""
    federation = json.loads((REFERENCE / "federation.json").read_text())
    checked = 0
    for hypothesis in classification.hypotheses:
        for citation in hypothesis.citations:
            if not citation.artifact.endswith("federation.json"):
                continue
            if not citation.field.startswith("["):
                continue
            index = int(citation.field.split("]")[0][1:])
            assert federation[index]["detail"].startswith(citation.value[:60])
            assert federation[index]["planner"] == hypothesis.planner
            checked += 1
    assert checked >= 13


@requires_reference
def test_unknown_is_a_common_respectable_outcome(classification):
    """Most of this trial's disagreements are honestly unclassifiable."""
    assert classification.n_unknown == 6
    assert classification.cause_counts == {
        "MODEL_DEFECT": 5,
        "REPRESENTATION_MISMATCH": 2,
        "UNKNOWN:REPEATABILITY_UNOBSERVED": 5,
        "UNKNOWN:PROBE_FEDERATION_CONFLICT": 1,
    }
    for hypothesis in classification.hypotheses:
        if hypothesis.is_unknown:
            assert "What would classify it" in hypothesis.detail or hypothesis.competing


@requires_reference
def test_model_defect_is_only_claimed_with_independent_mismatch_evidence(
    classification,
):
    """MODEL_DEFECT cites the real mispredicted ``dead_end``/``solved``."""
    mismatch_dims = {
        m["dimension"] for m in classification.model_final_state_mismatches
    }
    assert mismatch_dims == {"dead_end", "solved"}

    defects = [h for h in classification.hypotheses if h.cause == "MODEL_DEFECT"]
    assert len(defects) == 5
    for hypothesis in defects:
        assert hypothesis.model_says_applicable is True
        assert hypothesis.disputed_action not in (hypothesis.environment_applicable or ())
        assert any(
            citation.field == "final_state_mismatches"
            for citation in hypothesis.citations
        ), hypothesis


@requires_reference
def test_probe_federation_conflict_names_the_real_contradicting_probe(classification):
    """The one evidence conflict points at a real, re-checkable probe record."""
    conflicts = [
        h
        for h in classification.hypotheses
        if h.cause == "UNKNOWN:PROBE_FEDERATION_CONFLICT"
    ]
    assert len(conflicts) == 1
    hypothesis = conflicts[0]
    assert hypothesis.planner == "DSPyPolicy"
    assert hypothesis.disputed_action == "mine"

    citation = next(c for c in hypothesis.citations if "probe_log[" in c.field)
    index = int(citation.field.split("[")[1].rstrip("]"))
    probe_log = json.loads((REFERENCE / "typed_probe_log.json").read_text())["probe_log"]
    record = probe_log[index]
    assert record["action"] == "mine"
    assert record["applicable"] is True


@requires_reference
def test_projection_loss_is_not_claimed_when_no_loss_was_recorded(classification):
    """``representation_losses`` is empty here, so nothing may be blamed on it."""
    assert classification.representation_losses == {}
    assert "PROJECTION_LOSS" not in classification.cause_counts


@requires_reference
def test_next_experiment_reuses_the_existing_probe_proposer():
    """The derived experiment is the existing proposer's output, not a new one."""
    experiment = next_discriminating_experiment(REFERENCE)
    assert isinstance(experiment, NextExperiment), experiment
    assert experiment.cannot_distinguish is None
    assert experiment.reused_proposer == "discovered_domain.propose_discriminating_probe"
    assert experiment.experiment["kind"] == "PRECONDITION_DISCRIMINATION"
    assert experiment.experiment["action"] == "burn_catalyst"
    assert "MODEL_DEFECT" in experiment.distinguishes
    assert "REPRESENTATION_MISMATCH" in experiment.distinguishes
    assert experiment.experiment["reached_states_to_test"]
    # The two causes that are claims about an unarchived artifact are named as
    # undecidable by any live probe, rather than silently dropped.
    assert experiment.would_require
    assert "PROJECTION_LOSS" in experiment.would_require[0]


@requires_reference
def test_absent_trial_returns_typed_unknown_naming_the_path(tmp_path):
    """Absence is reported as absence, with the exact missing artifact."""
    result = classify_disagreement(tmp_path)
    assert isinstance(result, Unknown)
    assert result.status == "UNKNOWN"
    assert any("federation.json" in a for a in result.absent), result.absent


@pytest.mark.skipif(not _all_trials(), reason="no archived crown trials in checkout")
def test_corpus_refuses_to_rank_below_the_dogfood_floor():
    """Aggregation carries n_episodes and refuses ranking on the same floor."""
    trials = _all_trials()
    corpus = classify_corpus(trials)
    assert isinstance(corpus, CorpusClassification), corpus
    assert corpus.n_trial_dirs == len(trials)
    assert corpus.min_episodes_for_ranking == MIN_EPISODES_FOR_RANKING
    if corpus.n_episodes < MIN_EPISODES_FOR_RANKING:
        assert corpus.ranking_refused
        assert f"n_episodes={corpus.n_episodes}" in corpus.ranking_refused
        assert corpus.cause_ranking == ()
        assert corpus.cause_counts, "counts are reported even when ranking is refused"
    else:
        assert corpus.ranking_refused is None
        assert corpus.cause_ranking


def test_empty_corpus_is_unknown_not_a_clean_aggregate():
    result = classify_corpus([])
    assert isinstance(result, Unknown)
    assert "no trial directories" in result.detail


@pytest.mark.skipif(not _all_trials(), reason="no archived crown trials in checkout")
def test_classifier_is_read_only_over_the_archive():
    """Classification must not create, modify, or delete any archived artifact.

    The ``receipts.sqlite3-shm`` / ``-wal`` sidecars are excluded and the
    exclusion is the finding, not a convenience: SQLite touches the shared-memory
    sidecar of a WAL database even for a ``mode=ro`` connection, which
    :func:`dogfood._receipt_rows` opens. No evidence file's *content* changes;
    the sidecar mtime does. Asserting otherwise would fail for a reason that has
    nothing to do with this module.
    """

    def snapshot() -> dict[Path, tuple[int, int]]:
        return {
            p: (p.stat().st_mtime_ns, p.stat().st_size)
            for t in _all_trials()
            for p in t.rglob("*")
            if p.is_file() and p.suffix not in (".sqlite3-shm", ".sqlite3-wal")
        }

    before = snapshot()
    for trial in _all_trials():
        classify_disagreement(trial)
        next_discriminating_experiment(trial)
    assert snapshot() == before
