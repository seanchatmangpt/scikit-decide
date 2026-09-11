from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, List

import pandas as pd
from models import CandidateDecision, Intent, RankingPolicy, Recommendation
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def load_data(data_dir: str | Path = "data") -> tuple[pd.DataFrame, pd.DataFrame]:
    data_path = Path(data_dir)
    catalog = pd.read_csv(data_path / "catalog.csv")
    circulation = pd.read_csv(
        data_path / "circulation.csv", parse_dates=["checkout_date"]
    )
    catalog["available"] = catalog["available"].astype(str).str.lower().eq("true")
    catalog["series"] = catalog["series"].fillna("")
    return catalog, circulation


def default_policy() -> RankingPolicy:
    return RankingPolicy(
        policy_id="baseline-v1",
        content_weight=0.45,
        co_circulation_weight=0.30,
        intent_weight=0.20,
        curated_weight=0.05,
        novelty_weight=0.0,
    )


class HybridRecommender:
    """Small, inspectable hybrid recommender for the Qvest interview demo.

    Candidate signals:
      * content similarity over catalog subjects + descriptions
      * item-to-item co-circulation from historical borrowing
      * librarian intent match from parsed natural language
      * inverse-popularity novelty for lawful discovery policies
      * availability / recency / long-series policy filters
    """

    def __init__(self, catalog: pd.DataFrame, circulation: pd.DataFrame):
        self.catalog = catalog.copy()
        self.circulation = circulation.copy().sort_values("checkout_date")
        self.book_index = {book_id: i for i, book_id in enumerate(self.catalog.book_id)}
        corpus = (
            self.catalog["subjects"].fillna("")
            + " "
            + self.catalog["description"].fillna("")
        ).tolist()
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.item_matrix = self.vectorizer.fit_transform(corpus)
        self.co_counts = self._build_co_circulation()
        self.popularity = Counter(self.circulation.book_id.tolist())
        self.max_popularity = max(self.popularity.values(), default=1)

    def _build_co_circulation(self) -> dict[str, Counter]:
        by_student: dict[str, list[str]] = defaultdict(list)
        for row in self.circulation.itertuples(index=False):
            by_student[row.student_id].append(row.book_id)

        co_counts: dict[str, Counter] = defaultdict(Counter)
        for books in by_student.values():
            unique_books = list(dict.fromkeys(books))
            for a in unique_books:
                for b in unique_books:
                    if a != b:
                        co_counts[a][b] += 1
        return co_counts

    def borrowed_books(self, student_id: str) -> list[str]:
        rows = self.circulation[self.circulation.student_id == student_id]
        return rows.sort_values("checkout_date").book_id.tolist()

    def recommend(
        self,
        student_id: str,
        intent: Intent | None = None,
        top_k: int = 5,
        policy: RankingPolicy | None = None,
    ) -> List[Recommendation]:
        recommendations, _ = self.recommend_with_trace(
            student_id=student_id,
            intent=intent,
            top_k=top_k,
            policy=policy,
        )
        return recommendations

    def recommend_with_trace(
        self,
        student_id: str,
        intent: Intent | None = None,
        top_k: int = 5,
        policy: RankingPolicy | None = None,
    ) -> tuple[List[Recommendation], List[CandidateDecision]]:
        intent = intent or Intent(themes=[])
        policy = policy or default_policy()
        borrowed = self.borrowed_books(student_id)
        content_scores = self._content_scores(borrowed)
        max_co = max(
            [
                count
                for src in borrowed
                for count in self.co_counts.get(src, {}).values()
            ]
            or [1]
        )

        ranked = []
        trace = []
        for row in self.catalog.itertuples(index=False):
            refusal_reasons = self._refusal_reasons(row, borrowed, intent)
            if refusal_reasons:
                trace.append(
                    CandidateDecision(
                        book_id=row.book_id,
                        title=row.title,
                        admitted=False,
                        reasons=tuple(refusal_reasons),
                        signals={},
                    )
                )
                continue

            content = float(content_scores[self.book_index[row.book_id]])
            co = (
                sum(
                    self.co_counts.get(src, Counter()).get(row.book_id, 0)
                    for src in borrowed
                )
                / max_co
            )
            intent_match = self._intent_match(row, intent.themes)
            curated_boost = (
                1.0
                if "library" in str(row.subjects).lower()
                or "books" in str(row.subjects).lower()
                else 0.0
            )
            novelty = 1.0 - (self.popularity.get(row.book_id, 0) / self.max_popularity)
            score = (
                policy.content_weight * content
                + policy.co_circulation_weight * co
                + policy.intent_weight * intent_match
                + policy.curated_weight * curated_boost
                + policy.novelty_weight * novelty
            )
            signals = {
                "content_similarity": round(float(content), 4),
                "co_circulation": round(float(co), 4),
                "intent_match": round(float(intent_match), 4),
                "librarian_curated_boost": bool(curated_boost),
                "novelty": round(float(novelty), 4),
                "available": bool(row.available),
                "policy_id": policy.policy_id,
            }
            ranked.append((score, row, signals))
            trace.append(
                CandidateDecision(
                    book_id=row.book_id,
                    title=row.title,
                    admitted=True,
                    reasons=("ADMITTED:RANKABLE",),
                    signals=signals,
                )
            )

        ranked.sort(key=lambda item: (-item[0], item[1].book_id))
        recommendations = [
            self._to_recommendation(score, row, signals)
            for score, row, signals in ranked[:top_k]
        ]
        return recommendations, trace

    def _content_scores(self, borrowed: list[str]):
        profile_indices = [self.book_index[b] for b in borrowed if b in self.book_index]
        if not profile_indices:
            return [0.0] * len(self.catalog)
        profile_vector = self.item_matrix[profile_indices].mean(axis=0)
        return cosine_similarity(profile_vector.A, self.item_matrix).flatten()

    @staticmethod
    def _refusal_reasons(row, borrowed: list[str], intent: Intent) -> list[str]:
        reasons = []
        if not row.available:
            reasons.append("REFUSED:UNAVAILABLE")
        if intent.exclude_recently_borrowed and row.book_id in borrowed:
            reasons.append("REFUSED:RECENTLY_BORROWED")
        if intent.max_pages is not None and int(row.length_pages) > intent.max_pages:
            reasons.append("REFUSED:MAX_PAGES")
        if intent.avoid_long_series and row.series:
            reasons.append("REFUSED:LONG_SERIES")
        return reasons

    @staticmethod
    def _intent_match(row, themes: Iterable[str]) -> float:
        themes = tuple(themes)
        if not themes:
            return 0.0
        haystack = f"{row.subjects} {row.description}".lower()
        hits = sum(1 for theme in themes if theme.lower() in haystack)
        return hits / len(themes)

    @staticmethod
    def _to_recommendation(score, row, signals) -> Recommendation:
        explanation = (
            "Recommended from admitted catalog evidence using content, co-circulation, "
            "librarian-intent, curation, and novelty signals under the selected policy."
        )
        return Recommendation(
            book_id=row.book_id,
            title=row.title,
            score=round(float(score), 4),
            signals=signals,
            explanation=explanation,
        )
