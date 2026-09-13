# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Self-consistency / ensemble reasoning over DSPy predictions.

Standalone utility: no dependency on the k8s cluster or the sregym benchmark
harness. Fires N independent real DSPy/LM calls against the same signature
and input, then merges the N predictions on one output field by clustering
near-duplicate free-text answers and voting for the majority cluster.

Design mirrors ``autofde_lab.fabric.dspy.DSPyDecisionCompiler``: DSPy and its
LM are only used at the reasoning frontier (here: producing and comparing
candidate answers). The merge/vote arithmetic itself is plain, deterministic
Python running outside the language-model path.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EnsemblePrediction:
    """One raw prediction out of the N fired for a single ensemble call."""

    index: int
    output: str
    prediction: Any


@dataclass(frozen=True)
class EnsembleResult:
    """The merged outcome of an ensemble/self-consistency call.

    ``confidence`` is the fraction of the N predictions that fell in the
    winning cluster (``len(winning_cluster) / n``). When no cluster has more
    than one member (total disagreement), the most detailed single answer is
    still returned, but ``agreed`` is False and confidence reflects the true
    1/n support rather than being inflated.
    """

    answer: str
    confidence: float
    agreed: bool
    winning_cluster_size: int
    n: int
    clusters: list[list[EnsemblePrediction]]
    predictions: list[EnsemblePrediction]


SimilarityFn = Callable[[str, str], bool]


def default_similarity(a: str, b: str) -> bool:
    """Cheap heuristic: two answers are "the same claim" if they share a
    majority of their significant (len > 3) lowercase word tokens.

    This is intentionally simple and dependency-free. Callers that want a
    judge-LM-based similarity (a second small DSPy call asking "do these two
    claims describe the same root cause?") should pass their own
    ``similarity_fn`` of the same ``(str, str) -> bool`` shape — see
    ``make_dspy_judge_similarity``.
    """
    words_a = {w for w in _tokenize(a) if len(w) > 3}
    words_b = {w for w in _tokenize(b) if len(w) > 3}
    if not words_a or not words_b:
        return a.strip().lower() == b.strip().lower()
    overlap = words_a & words_b
    smaller = min(len(words_a), len(words_b))
    if smaller == 0:
        return False
    return (len(overlap) / smaller) >= 0.5


def _tokenize(text: str) -> list[str]:
    return [
        "".join(ch for ch in token if ch.isalnum())
        for token in text.lower().split()
    ]


def make_dspy_judge_similarity(judge_program: Any | None = None) -> SimilarityFn:
    """Build a similarity function backed by a real second DSPy call.

    The judge program is a ``dspy.Predict`` over a signature asking whether
    two claims describe the same root cause. Requires ``dspy`` to be
    installed and an LM already configured (``dspy.configure(lm=...)`` or
    per-call ``dspy.context(lm=...)``), exactly like any other DSPy call in
    this repo.
    """
    import dspy

    if judge_program is None:

        class SameRootCause(dspy.Signature):
            """Decide whether two short diagnostic claims describe the same
            underlying root cause, even if worded differently."""

            claim_a: str = dspy.InputField()
            claim_b: str = dspy.InputField()
            same_root_cause: bool = dspy.OutputField()

        judge_program = dspy.Predict(SameRootCause)

    def _judge(a: str, b: str) -> bool:
        result = judge_program(claim_a=a, claim_b=b)
        value = result.same_root_cause
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "yes", "1"}

    return _judge


def fire_ensemble(
    program: Any,
    kwargs: dict[str, Any],
    *,
    n: int,
    output_field: str,
    max_workers: int | None = None,
) -> list[EnsemblePrediction]:
    """Fire ``n`` independent real calls to ``program(**kwargs)`` in parallel.

    ``program`` is any callable DSPy module (``dspy.Predict``,
    ``dspy.ChainOfThought``, ...) already bound to a signature; the caller is
    responsible for configuring an LM with sampling (e.g.
    ``dspy.LM(..., temperature=...)``) so that repeated calls actually
    diversify rather than returning ``n`` identical greedy completions.

    Returns the raw ``n`` predictions in call order (not merged). Each
    ``EnsemblePrediction.output`` is ``str(prediction[output_field])``.
    """
    if n < 1:
        raise ValueError("n must be >= 1")

    def _call(index: int) -> EnsemblePrediction:
        prediction = program(**kwargs)
        output = str(getattr(prediction, output_field))
        return EnsemblePrediction(index=index, output=output, prediction=prediction)

    workers = max_workers or n
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_call, i) for i in range(n)]
        results = [future.result() for future in futures]
    return sorted(results, key=lambda p: p.index)


def merge_predictions(
    predictions: list[EnsemblePrediction],
    *,
    similarity_fn: SimilarityFn = default_similarity,
) -> EnsembleResult:
    """Cluster ``predictions`` by ``similarity_fn`` and vote for the winner.

    Clustering: single-linkage — a prediction joins the first existing
    cluster whose representative (first member) it is similar to, else it
    starts a new cluster. Deterministic given a deterministic
    ``similarity_fn`` and stable input order.

    Winner selection:
    - If the largest cluster has more than one member, it wins.
      ``agreed=True``, ``confidence = winning_cluster_size / n``. The
      representative answer is the longest (most detailed) member of that
      cluster.
    - If every cluster has exactly one member (total disagreement), the
      single most detailed (longest) answer across all predictions is
      returned, but ``agreed=False`` and ``confidence = 1 / n`` — the true,
      unfavorably low support, never inflated to look like a real majority.
    """
    if not predictions:
        raise ValueError("predictions must be non-empty")

    n = len(predictions)
    clusters: list[list[EnsemblePrediction]] = []
    for pred in predictions:
        placed = False
        for cluster in clusters:
            representative = cluster[0]
            if similarity_fn(representative.output, pred.output):
                cluster.append(pred)
                placed = True
                break
        if not placed:
            clusters.append([pred])

    largest = max(clusters, key=len)
    agreed = len(largest) > 1

    if agreed:
        winner_pool = largest
    else:
        winner_pool = predictions

    representative_pred = max(winner_pool, key=lambda p: len(p.output))
    confidence = len(largest) / n

    return EnsembleResult(
        answer=representative_pred.output,
        confidence=confidence,
        agreed=agreed,
        winning_cluster_size=len(largest),
        n=n,
        clusters=clusters,
        predictions=predictions,
    )


def ensemble_predict(
    program: Any,
    kwargs: dict[str, Any],
    *,
    n: int = 5,
    output_field: str = "answer",
    similarity_fn: SimilarityFn = default_similarity,
    max_workers: int | None = None,
) -> EnsembleResult:
    """Fire ``n`` real parallel DSPy calls and merge them by voting.

    Convenience wrapper composing :func:`fire_ensemble` and
    :func:`merge_predictions`. See both for the full contract.
    """
    predictions = fire_ensemble(
        program, kwargs, n=n, output_field=output_field, max_workers=max_workers
    )
    return merge_predictions(predictions, similarity_fn=similarity_fn)
