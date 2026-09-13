"""Canonical Crown court re-export.

The terminal registry lives in :mod:`autofde_lab.fabric.crown_terminal` so every canonical
requirement is either evidence-backed SATISFIED or explicitly BLOCKED.
"""

from autofde_lab.fabric.crown_terminal import (  # noqa: F401
    CrownReport,
    CrownRequirement,
    RequirementStatus,
    crown_report,
)

__all__ = [
    "CrownReport",
    "CrownRequirement",
    "RequirementStatus",
    "crown_report",
]
