"""DFCM selection frontier over the read-only Awesome AI Gyms registry."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import tomllib

Compatibility = Literal["UNKNOWN", "COMPATIBLE", "REFUSED"]
_REGISTRY_COLUMNS = (
    "name",
    "canonical_url",
    "category",
    "kind",
    "modes",
    "tags",
    "provenance",
)


@dataclass(frozen=True, slots=True)
class AwesomeAIGymCandidate:
    """A discoverable gym candidate with canonical public identity and no DO authority."""

    gym_ref: str
    name: str
    canonical_url: str
    category: str
    kind: str
    modes: tuple[str, ...]
    tags: tuple[str, ...]
    provenance: tuple[str, ...]
    standing: Literal["UNKNOWN"] = "UNKNOWN"
    source_authority: Literal["NONE"] = "NONE"


@dataclass(frozen=True, slots=True)
class PlannerGymEdge:
    """One reversible planner×gym possibility in the AutoFDE selection frontier."""

    planner_ref: str
    gym_ref: str
    compatibility: Compatibility = "UNKNOWN"
    authority: Literal["SELECT_ONLY"] = "SELECT_ONLY"
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class GymActHandoffIntent:
    """Inert handoff manufactured after selection; GymAct must independently admit it."""

    planner_ref: str
    gym_ref: str
    requested_stage: Literal["CANDIDATE_ADMISSION"] = "CANDIDATE_ADMISSION"
    authority: Literal["NONE"] = "NONE"


def parse_awesome_ai_gyms_tsv(text: str) -> tuple[AwesomeAIGymCandidate, ...]:
    """Parse catalog candidates without importing, launching, or probing any gym."""

    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if tuple(reader.fieldnames or ()) != _REGISTRY_COLUMNS:
        raise ValueError(f"AWESOME_AI_GYMS_COLUMNS:{reader.fieldnames!r}")

    candidates: list[AwesomeAIGymCandidate] = []
    seen_urls: set[str] = set()
    for row in reader:
        canonical_url = row["canonical_url"].strip()
        provenance = tuple(value for value in row["provenance"].split(",") if value)
        if canonical_url in seen_urls:
            raise ValueError(f"AWESOME_AI_GYM_DUPLICATE_URL:{canonical_url}")
        if not canonical_url.startswith("https://") or not provenance:
            raise ValueError(f"AWESOME_AI_GYM_INVALID_CANDIDATE:{row['name']}")
        seen_urls.add(canonical_url)
        candidates.append(
            AwesomeAIGymCandidate(
                gym_ref=canonical_url,
                name=row["name"].strip(),
                canonical_url=canonical_url,
                category=row["category"].strip(),
                kind=row["kind"].strip(),
                modes=tuple(value for value in row["modes"].split(",") if value),
                tags=tuple(value for value in row["tags"].split(",") if value),
                provenance=provenance,
            )
        )
    return tuple(candidates)


def load_awesome_ai_gyms(path: str | Path) -> tuple[AwesomeAIGymCandidate, ...]:
    """Load the caller-selected catalog projection as inert selection candidates."""

    return parse_awesome_ai_gyms_tsv(Path(path).read_text(encoding="utf-8"))


def planner_refs_from_pyproject(text: str) -> tuple[str, ...]:
    """Read the canonical solver entry-point names without importing any planner."""

    document = tomllib.loads(text)
    project = document.get("project", {})
    entry_points = project.get("entry-points", {})
    solvers = entry_points.get("autofde_lab.solvers", {})
    if not isinstance(solvers, dict) or not solvers:
        raise ValueError("AUTOFDE_PLANNER_ENTRY_POINTS_MISSING")
    refs = tuple(sorted(str(name) for name in solvers))
    if len(set(refs)) != len(refs):
        raise ValueError("DUPLICATE_PLANNER_REF")
    return refs


def build_repo_planner_gym_frontier(
    candidates: tuple[AwesomeAIGymCandidate, ...], pyproject_text: str
) -> tuple[PlannerGymEdge, ...]:
    """Cross every catalog candidate with the repo-declared planner population."""

    return build_planner_gym_frontier(
        candidates, planner_refs_from_pyproject(pyproject_text)
    )


def build_planner_gym_frontier(
    candidates: tuple[AwesomeAIGymCandidate, ...], planner_refs: tuple[str, ...]
) -> tuple[PlannerGymEdge, ...]:
    """Preserve the full planner×gym cross-product before compatibility selection."""

    if len(set(planner_refs)) != len(planner_refs):
        raise ValueError("DUPLICATE_PLANNER_REF")
    return tuple(
        PlannerGymEdge(planner_ref=planner_ref, gym_ref=candidate.gym_ref)
        for candidate in candidates
        for planner_ref in planner_refs
    )


def classify_edge(
    frontier: tuple[PlannerGymEdge, ...],
    *,
    planner_ref: str,
    gym_ref: str,
    compatibility: Literal["COMPATIBLE", "REFUSED"],
    reason: str,
) -> tuple[PlannerGymEdge, ...]:
    """Classify exactly one edge while preserving every unrelated possibility."""

    if not reason.strip():
        raise ValueError("EDGE_CLASSIFICATION_REASON_REQUIRED")
    found = False
    classified: list[PlannerGymEdge] = []
    for edge in frontier:
        if edge.planner_ref == planner_ref and edge.gym_ref == gym_ref:
            found = True
            classified.append(replace(edge, compatibility=compatibility, reason=reason))
        else:
            classified.append(edge)
    if not found:
        raise KeyError(f"PLANNER_GYM_EDGE_NOT_FOUND:{planner_ref}:{gym_ref}")
    return tuple(classified)


def manufacture_gymact_handoff(edge: PlannerGymEdge) -> GymActHandoffIntent:
    """Manufacture an inert intent only after this edge is explicitly compatible."""

    if edge.compatibility != "COMPATIBLE":
        raise ValueError(
            f"GYMACT_HANDOFF_REQUIRES_COMPATIBLE_EDGE:{edge.compatibility}"
        )
    return GymActHandoffIntent(planner_ref=edge.planner_ref, gym_ref=edge.gym_ref)
