"""Executable Design Science (EDS) primitives for this repository.

See ``docs/2026-09-12-executable-design-science.md`` for the paper this
module implements a first, scoped slice of. This package does not attempt
the full research program (object-centric experiment logging, process
conformance, the comparative DSR-vs-EDS evaluation framework) -- it
implements the one piece that is directly executable and testable inside a
single repository: the **Executable Research Claim (ERC)** data model, its
evidence-state vocabulary, and a receipt-binding/verification procedure that
enforces the paper's central state-collapse prohibitions:

    IMPLEMENTED != EXECUTED != OBSERVED != VERIFIED != REPRODUCED

Everything else the paper proposes (OCEL-style object-centric logs,
protocol-conformance checking against a declared research process, the
comparative C_DSR vs C_EDS evaluation) is real, scoped, future work, named
explicitly rather than silently assumed done -- see the module docstring in
``model.py`` for the exact boundary.
"""

from .model import (
    EvidenceState,
    ExecutableResearchClaim,
    Falsifier,
    FalsifierResult,
    Receipt,
    git_commit_identity,
    run_falsifiers,
    run_shell_receipt,
    verify_claim,
)

__all__ = [
    "EvidenceState",
    "ExecutableResearchClaim",
    "Falsifier",
    "FalsifierResult",
    "Receipt",
    "git_commit_identity",
    "run_falsifiers",
    "run_shell_receipt",
    "verify_claim",
]
