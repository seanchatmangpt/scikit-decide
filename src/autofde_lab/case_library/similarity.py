# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Explainable similarity/retrieval for the CBR case library.

Similarity metric: Jaccard similarity over each :class:`~autofde_lab.case_library.model.ProblemSignature`'s
:meth:`~autofde_lab.case_library.model.ProblemSignature.feature_set`:

.. math::

    J(A, B) = \\frac{|A \\cap B|}{|A \\cup B|}

where ``A``/``B`` are the token sets described in ``model.py`` (one
``namespace=`` token, one ``kind=`` token per anomalous kind, one ``field=``
token per diverged field). This is chosen over a weighted/learned metric
because it is (a) symmetric, (b) bounded in ``[0, 1]``, (c) exactly
reproducible by hand from the two feature sets, and (d) has no free
parameters to overfit -- the only tunable is the caller-chosen acceptance
threshold, not the metric itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from autofde_lab.case_library.model import Case, ProblemSignature

__all__ = ["ScoredCase", "jaccard_similarity", "retrieve_similar_cases", "retrieve_best_match"]


def jaccard_similarity(left: ProblemSignature, right: ProblemSignature) -> float:
    """Return the Jaccard similarity of two signatures' feature sets.

    ``0.0`` when both feature sets are empty union (the only case the plain
    formula would divide by zero) -- two contentless signatures are not
    "identical", they carry no comparable information.
    """
    left_set = left.feature_set()
    right_set = right.feature_set()
    union = left_set | right_set
    if not union:
        return 0.0
    intersection = left_set & right_set
    return len(intersection) / len(union)


@dataclass(frozen=True)
class ScoredCase:
    """A stored :class:`Case` paired with its similarity score against a query."""

    case: Case
    score: float


def retrieve_similar_cases(
    query: ProblemSignature,
    candidates: list[Case],
    threshold: float = 0.5,
) -> list[ScoredCase]:
    """Return every candidate whose Jaccard score against ``query`` is ``>= threshold``.

    Ordered by descending score (ties broken by ``case_id`` for a
    deterministic, testable order). Returns ``[]`` -- never a fabricated
    low-confidence entry -- when nothing clears ``threshold``.
    """
    scored = [
        ScoredCase(case=candidate, score=jaccard_similarity(query, candidate.signature))
        for candidate in candidates
    ]
    matches = [entry for entry in scored if entry.score >= threshold]
    matches.sort(key=lambda entry: (-entry.score, entry.case.case_id))
    return matches


def retrieve_best_match(
    query: ProblemSignature,
    candidates: list[Case],
    threshold: float = 0.5,
) -> ScoredCase | None:
    """Return the single highest-scoring case above ``threshold``, or ``None``.

    ``None`` is the explicit, honest "no confident match" result required by
    this module's design: a caller must never receive a below-threshold case
    dressed up as a retrieval hit.
    """
    matches = retrieve_similar_cases(query, candidates, threshold=threshold)
    return matches[0] if matches else None
