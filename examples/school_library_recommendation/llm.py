"""Bounded language layer for the school-library demo.

The production design can swap this deterministic parser for an LLM call that returns
this same schema. The recommender never lets the language layer directly rank books.
"""
from __future__ import annotations

import re
from models import Intent

THEME_TERMS = {
    "funny": "humor",
    "humor": "humor",
    "mystery": "mystery",
    "puzzle": "puzzles",
    "science fiction": "science fiction",
    "sci-fi": "science fiction",
    "fantasy": "fantasy",
    "adventure": "adventure",
    "graphic": "graphic novel",
    "animals": "animals",
}


def parse_librarian_request(text: str) -> Intent:
    """Convert a natural-language librarian request into structured constraints.

    This deliberately acts like the contract an LLM would satisfy, but runs offline for
    the interview demo. A real LLM adapter should validate output against this schema.
    """
    normalized = text.lower()
    themes = []
    for surface, canonical in THEME_TERMS.items():
        if surface in normalized and canonical not in themes:
            themes.append(canonical)

    max_pages = None
    if any(word in normalized for word in ["short", "shorter", "quick read"]):
        max_pages = 300
    match = re.search(r"under\s+(\d+)\s+pages", normalized)
    if match:
        max_pages = int(match.group(1))

    avoid_long_series = any(phrase in normalized for phrase in ["not part of a long series", "avoid long series", "standalone"])

    return Intent(themes=themes, exclude_recently_borrowed=True, max_pages=max_pages, avoid_long_series=avoid_long_series)
