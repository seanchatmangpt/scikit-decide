"""Bounded Sony Pictures EIP Principal FDE acceptance surface.

The public names are loaded lazily so ``python -m autofde_lab.sony.crown``
executes the crown module exactly once rather than pre-importing it through the
package initializer.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "SONY_ARCHITECTURE_CHOICES",
    "SONY_ECOSYSTEM_PINS",
    "SONY_REQUIREMENTS",
    "SonyCrownEvidence",
    "run_sony_crown",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from . import crown

    return getattr(crown, name)
