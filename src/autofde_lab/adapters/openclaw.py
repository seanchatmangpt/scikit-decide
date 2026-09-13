"""Optional adapter: OpenClaw. Never imported, only probed.

OpenClaw is the portfolio's actuation surface. This adapter does NOT actuate, and
locating OpenClaw grants this repository no authority to call it. Presence only.
"""

from __future__ import annotations

import os
import shutil

from autofde_lab.adapters.base import (
    AdapterProbe,
    AdapterStatus,
    resolve_home,
)

__all__ = ["OpenclawAdapter"]


class OpenclawAdapter:
    """Describes whether an OpenClaw install exists. Authorizes nothing."""

    name = "openclaw"
    env_var = "OPENCLAW_HOME"
    default_root = "~/openclaw"

    def probe(self) -> AdapterProbe:
        root = self.default_root
        try:
            root = resolve_home(self.env_var, self.default_root)
            searched = (root, "PATH:openclaw")
            which = shutil.which("openclaw")
            if which:
                return AdapterProbe(
                    status=AdapterStatus.AVAILABLE,
                    detail="openclaw binary found on PATH. AVAILABLE, not "
                    "COMPATIBLE: not executed, interface UNKNOWN. Presence confers "
                    "no actuation authority.",
                    located_at=which,
                    searched=searched,
                )
            if os.path.isdir(root):
                return AdapterProbe(
                    status=AdapterStatus.PARTIAL,
                    detail=f"OpenClaw checkout at {root} but no binary on PATH.",
                    located_at=root,
                    searched=searched,
                )
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail="OpenClaw not found; the core does not need it. This absence "
                f"claim covers exactly {searched} and nothing wider.",
                searched=searched,
            )
        except Exception as exc:  # pragma: no cover - probes never raise
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"openclaw probe failed: {exc!r}",
                searched=(root, "PATH:openclaw"),
            )
