"""Bounded multi-view query facade over admitted evidence records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

Record = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class QueryResult:
    view: str
    rows: tuple[Record, ...]
    examined: int


class PolyglotQueryPlane:
    def __init__(self, records: Iterable[Record]) -> None:
        self._records = tuple(dict(record) for record in records)

    def relational(self, predicate: Callable[[Record], bool]) -> QueryResult:
        rows = tuple(row for row in self._records if predicate(row))
        return QueryResult("relational", rows, len(self._records))

    def search(self, text: str) -> QueryResult:
        needle = text.casefold()
        rows = tuple(
            row
            for row in self._records
            if needle in " ".join(str(value) for value in row.values()).casefold()
        )
        return QueryResult("search", rows, len(self._records))

    def semantic(self, *, predicate: str, object_value: object) -> QueryResult:
        rows = tuple(row for row in self._records if row.get(predicate) == object_value)
        return QueryResult("semantic", rows, len(self._records))

    def process(self, *, case_id: object) -> QueryResult:
        rows = [row for row in self._records if row.get("case_id") == case_id]
        rows.sort(
            key=lambda row: (
                str(row.get("timestamp", "")),
                str(row.get("event_id", "")),
            )
        )
        return QueryResult("process", tuple(rows), len(self._records))
