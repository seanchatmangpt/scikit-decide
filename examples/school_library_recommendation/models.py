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
    objective: str = "balanced"


@dataclass(frozen=True)
class RankingPolicy:
    policy_id: str
    content_weight: float
    co_circulation_weight: float
    intent_weight: float
    curated_weight: float
    novelty_weight: float


@dataclass(frozen=True)
class CandidateDecision:
    book_id: str
    title: str
    admitted: bool
    reasons: tuple[str, ...]
    signals: Dict[str, float | bool | str]


@dataclass(frozen=True)
class PolicyEvaluation:
    policy: RankingPolicy
    hit_rate_at_k: float
    catalog_coverage: float
    novelty: float
    personalization: float
    intent_responsiveness: float
