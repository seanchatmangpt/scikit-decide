from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Recommendation:
    book_id: str
    title: str
    score: float
    signals: Dict[str, float | bool | str]
    explanation: str


@dataclass(frozen=True)
class Intent:
    themes: List[str]
    exclude_recently_borrowed: bool = True
    max_pages: int | None = None
    avoid_long_series: bool = False
