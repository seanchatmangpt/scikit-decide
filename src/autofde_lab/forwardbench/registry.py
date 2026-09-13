from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Subject:
    slug: str
    title: str
    adapter: str
    source_standing: str
    vendor_slug: str
    repository: str
    path: str
    pinned_revision: str
    resolution_standing: str
    smoke_standing: str
    local_safe: bool
    requires_authority: bool

    @property
    def observed_standing(self) -> str:
        if self.smoke_standing != "NOT_RUN":
            return self.smoke_standing
        if self.resolution_standing == "PINNED":
            return "PINNED"
        return self.source_standing


@dataclass(frozen=True)
class CandidatePlan:
    status: str
    reason: str
    subject: str
    adapter: str = ""
    commands: tuple[str, ...] = ()
    standing: str = "UNKNOWN"


class ForwardBenchRegistry:
    """Reads a ggen-manufactured registry and returns candidate plans only.

    No method in this class executes a subprocess, cloud API, Terraform,
    Kubernetes, MCP server, or benchmark. It is deliberately SELECT-only.
    """

    def __init__(self, registry_path: str | Path):
        payload = json.loads(Path(registry_path).read_text())
        if payload.get("authority") != "SELECT_ONLY":
            raise ValueError("REFUSED:FORWARDBENCH_REGISTRY_AUTHORITY_DRIFT")
        self._subjects = {row["slug"]: Subject(**row) for row in payload["benchmarks"]}

    def list(self) -> list[Subject]:
        return [self._subjects[k] for k in sorted(self._subjects)]

    def resolve(self, query: str) -> Subject | None:
        key = query.strip().lower()
        if key in self._subjects:
            return self._subjects[key]
        matches = [s for s in self.list() if key and (key in s.slug.lower() or key in s.title.lower())]
        return matches[0] if len(matches) == 1 else None

    def plan(self, query: str) -> CandidatePlan:
        subject = self.resolve(query)
        if subject is None:
            return CandidatePlan("REFUSED", "REFUSED:UNKNOWN_OR_AMBIGUOUS_FORWARD_BENCH", query)
        if not subject.vendor_slug or not subject.repository:
            return CandidatePlan("REFUSED", "REFUSED:UNKNOWN_REPOSITORY", subject.slug, subject.adapter, standing=subject.observed_standing)
        if subject.requires_authority:
            return CandidatePlan("REFUSED", "REFUSED:LIVE_AUTHORITY_REQUIRED", subject.slug, subject.adapter, standing=subject.observed_standing)
        sync = f"bash docs/papers/generated/forwardbench/sync-gyms.sh {subject.vendor_slug}"
        probe = f"bash docs/papers/generated/forwardbench/probe-gyms.sh {subject.vendor_slug}"
        return CandidatePlan(
            "CANDIDATE",
            "SELECT_ONLY:NO_ACTUATION",
            subject.slug,
            subject.adapter,
            (sync, probe),
            subject.observed_standing,
        )
