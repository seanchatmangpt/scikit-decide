# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for ``autofde_lab.fabric.dspy_ensemble``.

Real components exercised, no mocks:
  1. A real ``dspy.LM("groq/openai/gpt-oss-20b", api_key=...)`` configured
     against the real Groq API, using ``GROQ_API_KEY`` from the environment.
  2. A real ``dspy.Predict`` signature fired N times in parallel via real
     HTTP calls (``fire_ensemble`` -> ``ThreadPoolExecutor``).
  3. Real merge/vote logic (``merge_predictions``) exercised over the actual
     returned text of those N real predictions.

Named skip (never a mock substitute), matching this repo's own precedent in
``.claude/rules/testing-chicago-style.md`` (the TurboFieldfare worked
example): if ``GROQ_API_KEY`` is not set, the whole module skips.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("dspy")
import dspy

from autofde_lab.fabric.dspy_ensemble import (
    EnsemblePrediction,
    default_similarity,
    ensemble_predict,
    fire_ensemble,
    merge_predictions,
)

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
requires_real_groq_api_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in the environment -- real Groq-backed "
        "ensemble tests require a real, live API key (never a mock "
        "substitute); export GROQ_API_KEY to run this module."
    ),
)


class ArithmeticClaim(dspy.Signature):
    """Answer a simple arithmetic question with a short claim sentence."""

    question: str = dspy.InputField()
    answer: str = dspy.OutputField(
        desc="one short sentence stating the numeric answer"
    )


@pytest.fixture(scope="module")
def real_groq_lm() -> dspy.LM:
    """Configure the real Groq-backed LM used by every test in this module."""
    lm = dspy.LM(
        "groq/openai/gpt-oss-20b",
        api_key=_GROQ_API_KEY,
        temperature=1.0,
    )
    dspy.configure(lm=lm)
    return lm


@requires_real_groq_api_key
class TestFireEnsembleReal:
    """fire_ensemble against the real Groq API."""

    def test_fires_n_real_parallel_calls_and_returns_n_predictions(
        self, real_groq_lm: dspy.LM
    ) -> None:
        program = dspy.Predict(ArithmeticClaim)
        predictions = fire_ensemble(
            program,
            {"question": "What is 12 plus 30?"},
            n=5,
            output_field="answer",
        )

        assert len(predictions) == 5
        assert [p.index for p in predictions] == [0, 1, 2, 3, 4]
        for pred in predictions:
            assert isinstance(pred, EnsemblePrediction)
            assert isinstance(pred.output, str)
            assert pred.output.strip() != ""
            # Every real prediction should reference the correct sum
            # somewhere in its text -- gpt-oss-20b at basic arithmetic.
            assert "42" in pred.output

    def test_rejects_n_less_than_one(self, real_groq_lm: dspy.LM) -> None:
        program = dspy.Predict(ArithmeticClaim)
        with pytest.raises(ValueError):
            fire_ensemble(
                program, {"question": "What is 1 plus 1?"}, n=0, output_field="answer"
            )


@requires_real_groq_api_key
class TestEnsemblePredictReal:
    """End-to-end ensemble_predict: real N calls, real merge/vote."""

    def test_majority_clusters_on_a_convergent_arithmetic_question(
        self, real_groq_lm: dspy.LM
    ) -> None:
        # Low-ambiguity arithmetic: real gpt-oss-20b calls should converge
        # on "70" phrased in only a couple of distinct ways, giving a real
        # majority cluster to vote on.
        program = dspy.Predict(ArithmeticClaim)
        result = ensemble_predict(
            program,
            {"question": "What is 25 plus 45? Answer with the number only."},
            n=5,
            output_field="answer",
        )

        assert result.n == 5
        assert len(result.predictions) == 5
        assert sum(len(c) for c in result.clusters) == 5
        assert "70" in result.answer
        # A real majority should form on a question this unambiguous.
        assert result.agreed is True
        assert result.winning_cluster_size >= 3
        assert result.confidence == pytest.approx(result.winning_cluster_size / 5)
        assert 0.0 < result.confidence <= 1.0

    def test_confidence_reflects_true_support_never_inflated(
        self, real_groq_lm: dspy.LM
    ) -> None:
        program = dspy.Predict(ArithmeticClaim)
        result = ensemble_predict(
            program,
            {"question": "What is 100 divided by 4?"},
            n=6,
            output_field="answer",
        )
        # Confidence must exactly equal the largest cluster's real fraction
        # of n -- never a hardcoded/rounded stand-in.
        largest_cluster_size = max(len(c) for c in result.clusters)
        assert result.winning_cluster_size == largest_cluster_size
        assert result.confidence == pytest.approx(largest_cluster_size / 6)


class TestMergePredictionsPureLogic:
    """merge_predictions is pure Python -- exercised directly on real-shaped
    (but locally constructed) EnsemblePrediction objects, no LM call needed
    to test the voting arithmetic itself in isolation."""

    def test_total_disagreement_reports_low_honest_confidence(self) -> None:
        predictions = [
            EnsemblePrediction(index=0, output="the disk is full", prediction=None),
            EnsemblePrediction(
                index=1, output="a network partition occurred", prediction=None
            ),
            EnsemblePrediction(
                index=2, output="memory pressure caused an eviction", prediction=None
            ),
        ]
        result = merge_predictions(predictions, similarity_fn=default_similarity)

        assert result.agreed is False
        assert result.winning_cluster_size == 1
        assert result.confidence == pytest.approx(1 / 3)
        # Picks the most detailed (longest) answer honestly, not silently
        # claiming high confidence for it.
        assert result.answer == "memory pressure caused an eviction"

    def test_real_majority_wins_and_confidence_is_exact_fraction(self) -> None:
        predictions = [
            EnsemblePrediction(
                index=0,
                output="the CoreDNS pod is crashlooping due to a bad config",
                prediction=None,
            ),
            EnsemblePrediction(
                index=1,
                output="CoreDNS is crashlooping because of a bad configuration",
                prediction=None,
            ),
            EnsemblePrediction(
                index=2, output="the ingress target port is misconfigured", prediction=None
            ),
            EnsemblePrediction(
                index=3,
                output="CoreDNS pod crashloops from a bad config file",
                prediction=None,
            ),
        ]
        result = merge_predictions(predictions, similarity_fn=default_similarity)

        assert result.agreed is True
        assert result.winning_cluster_size == 3
        assert result.confidence == pytest.approx(0.75)
        assert "coredns" in result.answer.lower()

    def test_empty_predictions_rejected(self) -> None:
        with pytest.raises(ValueError):
            merge_predictions([])
