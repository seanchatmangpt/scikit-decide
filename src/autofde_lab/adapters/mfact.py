"""Optional adapter: ``~/mfact`` proof backend. Never imported, only probed."""

from __future__ import annotations

from autofde_lab.adapters.base import (
    AdapterProbe,
    AdapterStatus,
    probe_directory,
    resolve_home,
)

__all__ = ["MfactProofAdapter"]


class MfactProofAdapter:
    """Describes whether an ``mfact`` checkout exists. Authorizes nothing.

    A located proof corpus is not a proof. This adapter reports presence only.
    """

    name = "mfact"
    env_var = "MFACT_HOME"
    default_root = "~/mfact"

    def probe(self) -> AdapterProbe:
        try:
            return probe_directory(
                root=resolve_home(self.env_var, self.default_root),
                entrypoint=None,
                absent_detail="mfact proof backend not found; the core does not need it.",
                present_detail="mfact checkout located.",
            )
        except Exception as exc:  # pragma: no cover - probes never raise
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"mfact probe failed: {exc!r}",
                searched=(self.default_root,),
            )
