"""Optional adapter: ``~/mfw`` execution backend. Never imported, only probed."""

from __future__ import annotations

from autofde_lab.adapters.base import (
    AdapterProbe,
    AdapterStatus,
    probe_directory,
    resolve_home,
)

__all__ = ["MfwExecutionAdapter"]


class MfwExecutionAdapter:
    """Describes whether an ``mfw`` checkout exists. Authorizes nothing.

    ``mfw`` is optional. Its absence is a fact about ``mfw``, not a defect of the
    self-contained core.
    """

    name = "mfw"
    env_var = "MFW_HOME"
    default_root = "~/mfw"
    entrypoint = "target/debug/mfw-planner"

    def probe(self) -> AdapterProbe:
        try:
            return probe_directory(
                root=resolve_home(self.env_var, self.default_root),
                entrypoint=self.entrypoint,
                absent_detail="mfw execution backend not found; the core does not need it.",
                present_detail="mfw checkout located.",
            )
        except Exception as exc:  # pragma: no cover - probes never raise
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"mfw probe failed: {exc!r}",
                searched=(self.default_root,),
            )
