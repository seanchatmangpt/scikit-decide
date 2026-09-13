"""DfCM exploration of portable protocol implementation space.

This module SELECTs candidates. It cannot authorize or actuate them.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable


@dataclass(frozen=True, order=True)
class ProtocolCandidate:
    language: str
    transport: str
    digest: str
    persistence: str
    authority_provider: str
    receipt_capable: bool
    ambient_authority: bool = False
    custom_semantic_mass: int = 0
    central_dependencies: int = 0

    @property
    def identity(self) -> str:
        return ":".join(
            (
                self.language,
                self.transport,
                self.digest,
                self.persistence,
                self.authority_provider,
            )
        )


@dataclass(frozen=True)
class ProtocolConstraints:
    allowed_languages: tuple[str, ...]
    allowed_transports: tuple[str, ...]
    allowed_digests: tuple[str, ...]
    allowed_persistence: tuple[str, ...]
    authority_providers: tuple[str, ...]
    require_receiptability: bool = True
    forbid_ambient_authority: bool = True
    max_custom_semantic_mass: int = 0
    max_central_dependencies: int = 0


def enumerate_candidates(c: ProtocolConstraints) -> tuple[ProtocolCandidate, ...]:
    return tuple(
        ProtocolCandidate(*values, receipt_capable=True)
        for values in product(
            c.allowed_languages,
            c.allowed_transports,
            c.allowed_digests,
            c.allowed_persistence,
            c.authority_providers,
        )
    )


def admit(candidate: ProtocolCandidate, c: ProtocolConstraints) -> tuple[bool, str]:
    if c.forbid_ambient_authority and candidate.ambient_authority:
        return False, "REFUSED:AMBIENT_AUTHORITY"
    if c.require_receiptability and not candidate.receipt_capable:
        return False, "REFUSED:RECEIPT_CAPABILITY_REQUIRED"
    if candidate.custom_semantic_mass > c.max_custom_semantic_mass:
        return False, "REFUSED:CUSTOM_SEMANTIC_MASS"
    if candidate.central_dependencies > c.max_central_dependencies:
        return False, "REFUSED:CENTRAL_DEPENDENCY"
    return True, "ADMITTED"


def maximal_admissible_space(
    c: ProtocolConstraints, extra: Iterable[ProtocolCandidate] = ()
) -> tuple[ProtocolCandidate, ...]:
    candidates = enumerate_candidates(c) + tuple(extra)
    return tuple(
        sorted((x for x in candidates if admit(x, c)[0]), key=lambda x: x.identity)
    )
