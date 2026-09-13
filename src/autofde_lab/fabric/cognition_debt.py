"""Detection of repeated cognition that should be compiled out of hot paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from autofde_lab.fabric.selection import DecisionRegime


@dataclass(frozen=True, slots=True)
class CognitionEpisode:
    signature_key: str
    regime: DecisionRegime
    frontier_tokens: int
    verified: bool
    successful: bool = True

    def __post_init__(self) -> None:
        if self.frontier_tokens < 0:
            raise ValueError("frontier_tokens must be non-negative")


@dataclass(frozen=True, slots=True)
class CognitionDebtFinding:
    signature_key: str
    repeated_episodes: int
    frontier_tokens: int
    finding: str = "CANDIDATE:REPEATED_COGNITION_DEBT"
    reason: str = "verified HOT executions repeatedly consumed frontier-model tokens"


def detect_repeated_cognition_debt(
    episodes: Iterable[CognitionEpisode], *, min_repetitions: int = 2
) -> tuple[CognitionDebtFinding, ...]:
    """Return exact-signature HOT paths that repeatedly pay frontier inference.

    A finding is intentionally a CANDIDATE optimization defect, not an authority
    to rewrite the path. Compilation still requires admission, verification and
    the normal manufacture pipeline.
    """

    if min_repetitions < 2:
        raise ValueError("min_repetitions must be >= 2")
    grouped: dict[str, list[CognitionEpisode]] = {}
    for episode in episodes:
        if (
            episode.regime is DecisionRegime.HOT
            and episode.verified
            and episode.successful
            and episode.frontier_tokens > 0
        ):
            grouped.setdefault(episode.signature_key, []).append(episode)

    findings = [
        CognitionDebtFinding(
            signature_key=signature_key,
            repeated_episodes=len(rows),
            frontier_tokens=sum(row.frontier_tokens for row in rows),
        )
        for signature_key, rows in sorted(grouped.items())
        if len(rows) >= min_repetitions
    ]
    return tuple(findings)
