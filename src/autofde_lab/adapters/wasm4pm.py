"""Optional adapter: ``~/wasm4pm-compat``. Never imported, only probed."""

from __future__ import annotations

from autofde_lab.adapters.base import (
    AdapterProbe,
    AdapterStatus,
    probe_directory,
    resolve_home,
)

__all__ = ["Wasm4pmCompatAdapter"]


class Wasm4pmCompatAdapter:
    """Describes whether a ``wasm4pm-compat`` checkout exists. Authorizes nothing."""

    name = "wasm4pm"
    env_var = "WASM4PM_COMPAT_HOME"
    default_root = "~/wasm4pm-compat"

    def probe(self) -> AdapterProbe:
        try:
            return probe_directory(
                root=resolve_home(self.env_var, self.default_root),
                entrypoint=None,
                absent_detail="wasm4pm-compat not found; the core does not need it.",
                present_detail="wasm4pm-compat checkout located.",
            )
        except Exception as exc:  # pragma: no cover - probes never raise
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"wasm4pm probe failed: {exc!r}",
                searched=(self.default_root,),
            )
