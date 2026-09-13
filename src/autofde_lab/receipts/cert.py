"""Reduced from mfw-pcp-cert's generic ``Certificate<Body>`` to one dataclass with a
plain ``dict`` body — no generic-type ceremony, same self-digesting-and-validating shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .core import Digest


class CertificateError(ValueError):
    """Raised by ``Certificate.validate`` when the certificate is internally
    inconsistent (digest doesn't match its own body)."""


@dataclass(frozen=True)
class Certificate:
    kind: str
    body: dict = field(default_factory=dict)
    issued_at_ms: int = 0

    def certificate_digest(self) -> Digest:
        return Digest.of_json({"kind": self.kind, "body": self.body})

    def validate(self, *, expected_kind: str | None = None) -> None:
        if expected_kind is not None and self.kind != expected_kind:
            raise CertificateError(
                f"expected certificate kind {expected_kind!r}, got {self.kind!r}"
            )

    def to_record(self) -> dict:
        return {
            "kind": self.kind,
            "body": self.body,
            "issued_at_ms": self.issued_at_ms,
            "digest": str(self.certificate_digest()),
        }
