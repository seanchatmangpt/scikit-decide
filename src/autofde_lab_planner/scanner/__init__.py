"""Generalized structural-anomaly scanner. See docs/autofde-lab-planner-generalized-architecture.md."""

from autofde_lab_planner.scanner.models import Anomaly, RelationClass
from autofde_lab_planner.scanner.registry import ANALYZERS, scan

__all__ = ["Anomaly", "RelationClass", "ANALYZERS", "scan"]
