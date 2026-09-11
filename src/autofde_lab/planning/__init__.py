"""Declarative external-solver/validator configuration and shell-free invocation.

Ported pattern (not source) from mfw-planner's ``engines.toml`` +
``src/{config.rs,runner.rs}`` (see /Users/sac/mfw/mfw-planner). The port target is the
*wrapper discipline*: external planning tools (fast-downward, VAL, optic-clp, or any
other CLI-shaped solver/validator) are declared once, invoked without a shell, and every
invocation is receipted with a bounded, typed outcome instead of a bare exception.

FOND policy checks remain candidate-only: they validate finite policy-graph properties
but do not admit, authorize, execute, or promote a policy. FOND↔HDDL frontier checks
retain HDDL task-network progress as a separate state dimension and carry the same
candidate-only authority ceiling.

Public surface: ``EngineConfig``, ``EnginesConfig``, ``probe_engine``, ``run_engine``,
``FONDProblem``, ``CandidatePolicy``, ``PolicySemantics``, ``PolicyCheck``,
``check_candidate_policy``, ``HDDLProgressWitness``, ``FONDHDDLFrontierCheck``, and
``check_fond_hddl_frontier_closure``.
"""

from .config import EngineConfig, EnginesConfig, OutputMode
from .fond_hddl import (
    FONDHDDLFrontierCheck,
    HDDLProgressWitness,
    check_fond_hddl_frontier_closure,
)
from .fond_policy import (
    CandidatePolicy,
    FONDProblem,
    PolicyCheck,
    PolicySemantics,
    check_candidate_policy,
)
from .runner import EngineOutcome, EngineRunReceipt, probe_engine, run_engine

__all__ = [
    "CandidatePolicy",
    "EngineConfig",
    "EngineOutcome",
    "EngineRunReceipt",
    "EnginesConfig",
    "FONDHDDLFrontierCheck",
    "FONDProblem",
    "HDDLProgressWitness",
    "OutputMode",
    "PolicyCheck",
    "PolicySemantics",
    "check_candidate_policy",
    "check_fond_hddl_frontier_closure",
    "probe_engine",
    "run_engine",
]
