from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import BenchmarkScore, FrontierStanding


@dataclass(frozen=True, slots=True)
class Scoreboard:
    rows: tuple[BenchmarkScore, ...]

    @classmethod
    def from_scores(cls, scores: Iterable[BenchmarkScore]) -> "Scoreboard":
        rows = tuple(
            sorted(
                scores,
                key=lambda row: (
                    row.standing is not FrontierStanding.SOTA_SURPASSED,
                    -row.score,
                    -row.coverage,
                    row.cost_usd,
                    row.architecture_digest,
                ),
            )
        )
        return cls(rows)

    @property
    def champion(self) -> BenchmarkScore | None:
        return self.rows[0] if self.rows else None

    @property
    def sota_winners(self) -> tuple[BenchmarkScore, ...]:
        return tuple(
            row for row in self.rows if row.standing is FrontierStanding.SOTA_SURPASSED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "champion": self.champion.to_dict() if self.champion else None,
            "rows": [row.to_dict() for row in self.rows],
        }

    def write_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        )
        return destination
