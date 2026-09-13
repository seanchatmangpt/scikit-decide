# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Compatibility facade for the two admitted POWL runner surfaces.

``pipeline_runner`` is the current AutoFDE pipeline integration runner.
``concurrent_runner`` is the enterprise POWL 2.0 concurrent execution runner.
They are intentionally separate implementations: neither is allowed to erase
the other's API merely because both historically occupied ``powl.runner``.

This module preserves the historical import path while making the split
explicit.  Public and compatibility names from both implementations are
re-exported; if a future name collision maps to different objects, import is
refused instead of silently choosing one implementation.
"""

from __future__ import annotations

from . import concurrent_runner as _concurrent_runner
from . import pipeline_runner as _pipeline_runner


def _export(source: object) -> None:
    for name, value in vars(source).items():
        if name.startswith("__"):
            continue
        current = globals().get(name)
        if current is not None and current is not value and not name.startswith("_"):
            raise ImportError(f"REFUSED:POWL_RUNNER_EXPORT_COLLISION:{name}")
        globals()[name] = value


_export(_pipeline_runner)
_export(_concurrent_runner)

del _export
