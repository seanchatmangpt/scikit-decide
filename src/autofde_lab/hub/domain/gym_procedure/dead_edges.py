"""Public surface for refused-probe topology retained by ``discover_procedure``.

V2030.1.1-PRD-ARD.md, DfCM requirement: failed candidates are retained as
topology/evidence so the same dead edges are not repeatedly rediscovered
without a new hypothesis. The types live in ``discovery.py`` so the isolated
stdio worker (which loads that file by path, alone) keeps working; this module
re-exports them and ties the ledger digest to the canonical
``autofde_lab.autofde.hypothesis_ir.digest`` form.

This module selects nothing and actuates nothing; it carries evidence only.
"""

from __future__ import annotations

from autofde_lab.autofde.hypothesis_ir import digest
from autofde_lab.hub.domain.gym_procedure.discovery import (
    UNHYPOTHESIZED,
    DeadEdge,
    DeadEdgeLedger,
)

__all__ = ["UNHYPOTHESIZED", "DeadEdge", "DeadEdgeLedger", "ledger_digest"]


def ledger_digest(ledger: DeadEdgeLedger) -> str:
    """The ledger digest via ``hypothesis_ir.digest`` over the same canonical rows.

    Equal to ``ledger.digest()`` by construction; a test pins that equality so
    the two cannot silently diverge.
    """

    return digest(sorted(edge.canonical() for edge in ledger.edges))
