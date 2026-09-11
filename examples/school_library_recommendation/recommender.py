from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, List

import pandas as pd
from models import Intent, Recommendation
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


class HybridRecommender:
    """Small, inspectable hybrid recommender for the Qvest interview demo.

    Candidate signals:
      * content similarity over catalog subjects + descriptions
      * item-to-item co-circulation from historical borrowing
      * librarian intent match from parsed natural language
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
        self, student_id: str, intent: Intent | None = None, top_k: int = 5
    ) -> List[Recommendation]:
        intent = intent or Intent(themes=[])
        borrowed = self.borrowed_books(student_id)
        if not borrowed:
            return self._cold_start(intent, top_k)

        profile_indices = [self.book_index[b] for b in borrowed if b in self.book_index]
        profile_vector = self.item_matrix[profile_indices].mean(axis=0)
        content_scores = cosine_similarity(profile_vector.A, self.item_matrix).flatten()

        max_co = max(
            [
                count
                for src in borrowed
                for count in self.co_counts.get(src, {}).values()
            ]
            or [1]
        )
        rows = []
        for row in self.catalog.itertuples(index=False):
            if not row.available:
                continue
            if intent.exclude_recently_borrowed and row.book_id in borrowed:
                continue
            if (
                intent.max_pages is not None
                and int(row.length_pages) > intent.max_pages
            ):
                continue
            if intent.avoid_long_series and row.series:
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
            score = (
                0.45 * content + 0.30 * co + 0.20 * intent_match + 0.05 * curated_boost
            )
            rows.append((score, row, content, co, intent_match, curated_boost))

        rows.sort(key=lambda item: item[0], reverse=True)
        return [self._to_recommendation(*item) for item in rows[:top_k]]

    def _cold_start(self, intent: Intent, top_k: int) -> List[Recommendation]:
        candidates = []
        for row in self.catalog[self.catalog.available].itertuples(index=False):
            intent_match = self._intent_match(row, intent.themes)
            score = 0.7 * intent_match + 0.3 * (1.0 / max(int(row.length_pages), 1))
            candidates.append((score, row, 0.0, 0.0, intent_match, 0.0))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [self._to_recommendation(*item) for item in candidates[:top_k]]

    @staticmethod
    def _intent_match(row, themes: Iterable[str]) -> float:
        if not themes:
            return 0.0
        haystack = f"{row.subjects} {row.description}".lower()
        hits = sum(1 for theme in themes if theme.lower() in haystack)
        return hits / len(list(themes)) if themes else 0.0

    @staticmethod
    def _to_recommendation(
        score, row, content, co, intent_match, curated_boost
    ) -> Recommendation:
        explanation = (
            f"Recommended because it matches prior borrowing patterns "
            f"and has catalog evidence for {row.subjects}."
        )
        return Recommendation(
            book_id=row.book_id,
            title=row.title,
            score=round(float(score), 4),
            signals={
                "content_similarity": round(float(content), 4),
                "co_circulation": round(float(co), 4),
                "intent_match": round(float(intent_match), 4),
                "librarian_curated_boost": bool(curated_boost),
                "available": bool(row.available),
            },
            explanation=explanation,
        )
