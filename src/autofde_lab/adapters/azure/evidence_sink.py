"""Evidence sink surface — noting evidence produced ELSEWHERE.

This module does not issue receipts. It could, at most, record that some other
system claims to have produced evidence, and name where that claim came from.
The distinction is the same one drawn in ``src/autofde_lab/CLAUDE.md`` about the
call-integrity digests in ``openclaw_bridge.py``: recording what was asked and
answered authorizes nothing.
"""

from __future__ import annotations

from autofde_lab.adapters.azure.base import AzureProbe, AzureSurface
from autofde_lab.adapters.azure.probe import probe_surface
from autofde_lab.adapters.azure.refusals import Refusal, RefusalCode

__all__ = ["AzureEvidenceSink", "SURFACE"]

SURFACES = ("Azure Confidential Ledger", "Azure Blob immutable storage")

SURFACE = AzureSurface(
    name="azure.evidence_sink",
    surfaces=SURFACES,
    purpose="Note that evidence was produced elsewhere. Never to issue a receipt.",
    required_prerequisites=(
        "a Confidential Ledger instance URI",
        "an append-only collection configured for the caller",
    ),
)


class AzureEvidenceSink:
    """Declares evidence noting. Issues no receipt, admits nothing."""

    name = "azure.evidence_sink"
    surface = SURFACE

    def probe(self) -> AzureProbe:
        return probe_surface(
            surface_name="evidence sink",
            surfaces=SURFACES,
            absent_detail="Azure Confidential Ledger is a deployment-time surface.",
        )

    def record_execution_evidence(
        self, *, correlation_id: str, described_by: str
    ) -> Refusal:
        """Request that externally-produced evidence be noted. Typed refusal.

        Args:
            correlation_id: Correlates with an earlier observation.
            described_by: The external system claiming to have produced evidence.
                This operation records the CLAIM's provenance, not a verdict on it.
        """
        probe = self.probe()
        return Refusal(
            code=RefusalCode.NO_EVIDENCE_SINK,
            operation="record_execution_evidence",
            missing_prerequisite=(
                "an Azure Confidential Ledger instance URI and append-only "
                "collection (none is configured in this environment)"
            ),
            detail=(
                f"Refused for correlation_id={correlation_id!r} "
                f"described_by={described_by!r}. Nothing was written. Even on "
                "success this notes an external system's claim; it issues no "
                "receipt and admits nothing. " + probe.detail
            ),
            surfaces_searched=SURFACES,
            methods_used=probe.methods_used,
        )
