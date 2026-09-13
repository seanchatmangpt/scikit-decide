"""Compile mature planner selection into replayable candidate hot paths.

This module is deliberately below the actuation boundary. It turns a HOT
selection decision into a content-bound candidate artifact that can be reused
without repeating registry ranking. Reuse is admitted only when every bound
identity still matches; drift returns a typed refusal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum

from autofde_lab.fabric.cache import SQLiteERRCCache
from autofde_lab.fabric.selection import DecisionRegime, SelectionDecision


class HotPathStanding(str, Enum):
    COMPILED = "COMPILED"
    REUSED = "REUSED"
    REFUSED_NOT_HOT = "REFUSED:NOT_HOT"
    REFUSED_AMBIGUOUS = "REFUSED:AMBIGUOUS_HOT_ROUTE"
    REFUSED_IDENTITY_DRIFT = "REFUSED:HOT_PATH_IDENTITY_DRIFT"
    REFUSED_CACHE_MISS = "REFUSED:HOT_PATH_CACHE_MISS"
    REFUSED_AUTHORITY_ESCALATION = "REFUSED:HOT_PATH_AUTHORITY_ESCALATION"
    REFUSED_MALFORMED = "REFUSED:HOT_PATH_MALFORMED"


@dataclass(frozen=True, slots=True)
class HotPathIdentity:
    signature_key: str
    planner_id: str
    objective: str
    environment: str
    hardware: str
    capability_digest: str
    policy_digest: str
    selector_revision: str

    def canonical_json(self) -> str:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HotPathArtifact:
    identity: HotPathIdentity
    evidence_count: int
    candidate_only: bool = True

    def __post_init__(self) -> None:
        if self.evidence_count < 2:
            raise ValueError("evidence_count must preserve repeated HOT evidence")
        if not self.candidate_only:
            raise ValueError("hot-path artifacts never carry execution authority")

    def to_payload(self) -> dict[str, object]:
        return {
            "identity": asdict(self.identity),
            "evidence_count": self.evidence_count,
            "candidate_only": self.candidate_only,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "HotPathArtifact":
        identity = payload.get("identity")
        if not isinstance(identity, dict):
            raise ValueError("hot-path payload is missing identity")
        return cls(
            identity=HotPathIdentity(**identity),
            evidence_count=int(payload["evidence_count"]),
            candidate_only=bool(payload["candidate_only"]),
        )


@dataclass(frozen=True, slots=True)
class HotPathResult:
    standing: HotPathStanding
    artifact: HotPathArtifact | None
    reason: str


def compile_hot_path(
    decision: SelectionDecision,
    *,
    objective: str = "default",
    environment: str = "default",
    hardware: str = "default",
    capability_digest: str,
    policy_digest: str,
    selector_revision: str,
) -> HotPathResult:
    """Compile exactly one mature HOT route into a candidate artifact."""
    if decision.regime is not DecisionRegime.HOT:
        return HotPathResult(
            HotPathStanding.REFUSED_NOT_HOT,
            None,
            "only empirically HOT routes may be compiled",
        )
    if len(decision.candidates) != 1:
        return HotPathResult(
            HotPathStanding.REFUSED_AMBIGUOUS,
            None,
            "a HOT artifact requires exactly one selected planner",
        )
    identity = HotPathIdentity(
        signature_key=decision.signature_key,
        planner_id=decision.candidates[0],
        objective=objective,
        environment=environment,
        hardware=hardware,
        capability_digest=capability_digest,
        policy_digest=policy_digest,
        selector_revision=selector_revision,
    )
    artifact = HotPathArtifact(
        identity=identity, evidence_count=decision.evidence_count
    )
    return HotPathResult(
        HotPathStanding.COMPILED,
        artifact,
        "mature empirical selection compiled into a candidate-only hot path",
    )


def store_hot_path(cache: SQLiteERRCCache, artifact: HotPathArtifact) -> str:
    """Persist one compiled route under its exact content-bound identity."""
    cache.put(
        artifact.identity.digest,
        "planner-hot-path",
        artifact.to_payload(),
    )
    return artifact.identity.digest


def reuse_hot_path(
    cache: SQLiteERRCCache,
    expected: HotPathIdentity,
) -> HotPathResult:
    """Reuse a compiled candidate only when every material identity matches."""
    payload = cache.get(expected.digest)
    if payload is None:
        return HotPathResult(
            HotPathStanding.REFUSED_CACHE_MISS,
            None,
            "no compiled candidate exists for the exact expected identity",
        )
    if payload.get("candidate_only") is not True:
        return HotPathResult(
            HotPathStanding.REFUSED_AUTHORITY_ESCALATION,
            None,
            "cached object attempted to carry authority beyond candidate selection",
        )
    try:
        artifact = HotPathArtifact.from_payload(payload)
    except (KeyError, TypeError, ValueError):
        return HotPathResult(
            HotPathStanding.REFUSED_MALFORMED,
            None,
            "cached hot-path artifact is malformed or incomplete",
        )
    if artifact.identity != expected:
        return HotPathResult(
            HotPathStanding.REFUSED_IDENTITY_DRIFT,
            None,
            "cached candidate identity does not match the expected execution context",
        )
    return HotPathResult(
        HotPathStanding.REUSED,
        artifact,
        "exact identity matched; repeated planner ranking was eliminated",
    )
