"""Optional adapter: ``~/bcinr`` scheduling backend. Never imported, only probed."""

from __future__ import annotations

from autofde_lab.adapters.base import (
    AdapterProbe,
    AdapterStatus,
    probe_directory,
    resolve_home,
)

__all__ = ["BcinrSchedulerAdapter"]


class BcinrSchedulerAdapter:
    """Describes whether a ``bcinr`` checkout exists. Authorizes nothing."""

    name = "bcinr"
    env_var = "BCINR_HOME"
    default_root = "~/bcinr"

    def probe(self) -> AdapterProbe:
        try:
            return probe_directory(
                root=resolve_home(self.env_var, self.default_root),
                entrypoint=None,
                absent_detail="bcinr scheduling backend not found; the core does not need it.",
                present_detail="bcinr checkout located.",
            )
        except Exception as exc:  # pragma: no cover - probes never raise
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"bcinr probe failed: {exc!r}",
                searched=(self.default_root,),
            )
