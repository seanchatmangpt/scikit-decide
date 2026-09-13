"""Optional adapter: Ferroplan (``~/ferroplan``). Never imported, only probed."""

from __future__ import annotations

from autofde_lab.adapters.base import (
    AdapterProbe,
    AdapterStatus,
    probe_directory,
    resolve_home,
)

__all__ = ["FerroplanAdapter"]


class FerroplanAdapter:
    """Describes whether a Ferroplan checkout exists. Authorizes nothing."""

    name = "ferroplan"
    env_var = "FERROPLAN_HOME"
    default_root = "~/ferroplan"

    def probe(self) -> AdapterProbe:
        try:
            return probe_directory(
                root=resolve_home(self.env_var, self.default_root),
                entrypoint=None,
                absent_detail="Ferroplan not found; the core does not need it.",
                present_detail="Ferroplan checkout located.",
            )
        except Exception as exc:  # pragma: no cover - probes never raise
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"ferroplan probe failed: {exc!r}",
                searched=(self.default_root,),
            )
