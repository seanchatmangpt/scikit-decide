"""Versioned domain-pack contract shared by world, reasoning, manufacture, and runtime projections.

The contract carries provenance and projection identities only. It does not import
or execute projection implementations and therefore cannot acquire ambient
authority from them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


def _digest(value: Any) -> str:
    raw = json.dumps(value, default=asdict, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SourceProvenance:
    source_uri: str
    revision: str
    license_id: str
    content_digest: str

    def __post_init__(self) -> None:
        if any(not x.strip() for x in (self.source_uri, self.revision, self.license_id, self.content_digest)):
            raise ValueError("INCOMPLETE_SOURCE_PROVENANCE_REFUSED")


@dataclass(frozen=True)
class ProjectionContract:
    projection_id: str
    role: str
    schema_ref: str
    generator_ref: str

    def __post_init__(self) -> None:
        if self.role not in {"world", "reasoning", "manufacture", "runtime"}:
            raise ValueError("UNKNOWN_PROJECTION_ROLE_REFUSED")
        if any(not x.strip() for x in (self.projection_id, self.schema_ref, self.generator_ref)):
            raise ValueError("INCOMPLETE_PROJECTION_CONTRACT_REFUSED")


@dataclass(frozen=True)
class DomainPack:
    pack_id: str
    version: str
    provenance: SourceProvenance
    ontology_ref: str
    ontology_digest: str
    taxonomy_axes: tuple[str, ...]
    state_model_ref: str
    desired_state_laws: tuple[str, ...]
    violation_modes: tuple[str, ...]
    observation_contracts: tuple[str, ...]
    authority_contracts: tuple[str, ...]
    planner_compatibility: tuple[str, ...]
    remediation_morphologies: tuple[str, ...]
    verification_rules: tuple[str, ...]
    projections: tuple[ProjectionContract, ...]

    def __post_init__(self) -> None:
        if any(not x.strip() for x in (self.pack_id, self.version, self.ontology_ref, self.ontology_digest, self.state_model_ref)):
            raise ValueError("INCOMPLETE_DOMAIN_PACK_REFUSED")
        roles = [p.role for p in self.projections]
        if set(roles) != {"world", "reasoning", "manufacture", "runtime"} or len(roles) != 4:
            raise ValueError("DOMAIN_PACK_PROJECTION_CLOSURE_REFUSED")
        required_collections = (
            self.taxonomy_axes,
            self.desired_state_laws,
            self.violation_modes,
            self.observation_contracts,
            self.authority_contracts,
            self.planner_compatibility,
            self.remediation_morphologies,
            self.verification_rules,
        )
        if any(not values for values in required_collections):
            raise ValueError("DOMAIN_PACK_SEMANTIC_CLOSURE_REFUSED")

    @property
    def digest(self) -> str:
        return _digest(self)

    def projection(self, role: str) -> ProjectionContract:
        for projection in self.projections:
            if projection.role == role:
                return projection
        raise ValueError("UNKNOWN_PROJECTION_ROLE_REFUSED")
