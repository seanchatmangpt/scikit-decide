"""Optional adapter: ``ggen`` manufacture backend. Never imported, only probed."""

from __future__ import annotations

import os
import shutil

from autofde_lab.adapters.base import (
    AdapterProbe,
    AdapterStatus,
    resolve_home,
)

__all__ = ["GgenManufactureAdapter"]


class GgenManufactureAdapter:
    """Describes whether ``ggen`` exists, as a checkout or a ``PATH`` binary.

    Authorizes nothing: locating a generator does not mean anything was generated.
    """

    name = "ggen"
    env_var = "GGEN_HOME"
    default_root = "~/ggen"

    def probe(self) -> AdapterProbe:
        root = self.default_root
        try:
            root = resolve_home(self.env_var, self.default_root)
            which = shutil.which("ggen")
            searched = (root, "PATH:ggen")
            if which:
                return AdapterProbe(
                    status=AdapterStatus.AVAILABLE,
                    detail="ggen binary found on PATH. AVAILABLE, not COMPATIBLE: "
                    "the binary was located but not executed, so its interface is "
                    "UNKNOWN.",
                    located_at=which,
                    searched=searched,
                )
            if os.path.isdir(root):
                return AdapterProbe(
                    status=AdapterStatus.PARTIAL,
                    detail=f"ggen checkout at {root} but no ggen binary on PATH; "
                    "unbuilt or not installed.",
                    located_at=root,
                    searched=searched,
                )
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail="ggen not found; the core does not need it. This absence "
                f"claim covers exactly {searched} and nothing wider.",
                searched=searched,
            )
        except Exception as exc:  # pragma: no cover - probes never raise
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"ggen probe failed: {exc!r}",
                searched=(root, "PATH:ggen"),
            )
