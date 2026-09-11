from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

from .models import Fact


class FactStore:
    """Deterministic observation -> fact compiler. The LM never admits facts."""

    def __init__(self, *, max_facts: int = 1400, max_value_chars: int = 800) -> None:
        self.max_facts = max_facts
        self.max_value_chars = max_value_chars
        self._facts: dict[str, Fact] = {}

    @property
    def facts(self) -> list[Fact]:
        return list(self._facts.values())

    def ingest(self, source: str, raw: str) -> list[Fact]:
        try:
            payload: Any = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pairs = (
                (f"line[{i}]", line)
                for i, line in enumerate(str(raw).splitlines())
                if line.strip()
            )
        else:
            pairs = self._flatten(payload)

        admitted: list[Fact] = []
        for path, value in pairs:
            if len(self._facts) >= self.max_facts:
                break
            text = self._safe_value(path, value)[: self.max_value_chars]
            digest = hashlib.sha256(f"{source}\0{path}\0{text}".encode()).hexdigest()[
                :24
            ]
            fact = Fact(id=f"fact:{digest}", source=source, path=path, value=text)
            if fact.id not in self._facts:
                self._facts[fact.id] = fact
                admitted.append(fact)
        return admitted

    @staticmethod
    def _semantic_list_segment(item: Any, index: int) -> str:
        if not isinstance(item, dict):
            return f"[{index}]"
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            return f"[{index}]"
        name = metadata.get("name")
        if not name:
            return f"[{index}]"
        namespace = metadata.get("namespace") or "_cluster"
        kind = item.get("kind") or "Object"
        safe = lambda value: str(value).replace("/", "_").replace("]", "_")
        return f"[kind={safe(kind)},ns={safe(namespace)},name={safe(name)}]"

    def _flatten(self, value: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
        if isinstance(value, dict):
            for key in sorted(value, key=str):
                yield from self._flatten(value[key], f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                segment = self._semantic_list_segment(item, index)
                yield from self._flatten(item, f"{path}{segment}")
        else:
            yield path, value

    @staticmethod
    def _safe_value(path: str, value: Any) -> str:
        lowered = path.lower()
        if any(
            token in lowered
            for token in ("secret", "token", "password", "privatekey", ".data.")
        ):
            digest = hashlib.sha256(str(value).encode()).hexdigest()[:16]
            return f"<redacted:{digest}>"
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
