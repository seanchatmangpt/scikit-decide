# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Persistent case-based-reasoning (CBR) case library for Kubernetes faults.

Public API:

- :class:`~autofde_lab.case_library.model.ProblemSignature` -- normalized
  feature set for one diagnosed problem.
- :class:`~autofde_lab.case_library.model.Case` -- one solved/attempted
  trial: signature, diagnosis, mitigation commands, outcome.
- :class:`~autofde_lab.case_library.sqlite_store.CaseLibraryStore` --
  persistent SQLite store of cases.
- :func:`~autofde_lab.case_library.similarity.jaccard_similarity` -- the
  documented, hand-checkable similarity metric.
- :func:`~autofde_lab.case_library.similarity.retrieve_similar_cases` /
  :func:`~autofde_lab.case_library.similarity.retrieve_best_match` --
  retrieval over a candidate list.
- :func:`retrieve_from_store` -- convenience: load every case from a
  :class:`CaseLibraryStore` and retrieve the best match, or ``None``.
"""

from __future__ import annotations

from autofde_lab.case_library.model import Case, ProblemSignature
from autofde_lab.case_library.similarity import (
    ScoredCase,
    jaccard_similarity,
    retrieve_best_match,
    retrieve_similar_cases,
)
from autofde_lab.case_library.sqlite_store import CaseLibraryStore

__all__ = [
    "Case",
    "ProblemSignature",
    "ScoredCase",
    "CaseLibraryStore",
    "jaccard_similarity",
    "retrieve_similar_cases",
    "retrieve_best_match",
    "retrieve_from_store",
]


def retrieve_from_store(
    query: ProblemSignature,
    store: CaseLibraryStore,
    threshold: float = 0.5,
) -> ScoredCase | None:
    """Retrieve the best-matching case for ``query`` from ``store``.

    Loads every persisted case and delegates to
    :func:`~autofde_lab.case_library.similarity.retrieve_best_match`.
    Returns ``None`` -- never a fabricated low-confidence hit -- when no
    stored case's Jaccard score against ``query`` reaches ``threshold``.
    """
    return retrieve_best_match(query, store.all_cases(), threshold=threshold)
