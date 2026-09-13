"""Pure-Python, throwaway-but-faithful prototype of mfw's admit/broker/receipt/replay
discipline (see /Users/sac/mfw AGENTS.md: "plan -> authorization -> broker ->
actuation -> receipt -> replay"), scoped per the 80/20 ERRC grid in
~/.claude/plans/launch-5-lumen-explore-calm-acorn.md.

This package is explicitly not the final form -- autofde-lab's end state is pure
Rust. Its job is to let the broker/receipt/replay *shape* be iterated on fast in
Python, with an API surface (method names, field names, check order) chosen to
translate mechanically when it is later rewritten in Rust against
mfw's crates/pcp/{mfw-pcp-core,mfw-pcp-cert,mfw-pcp-broker,mfw-pcp-replay}.

Public surface: ``Digest``, ``Certificate``, ``Broker``, ``Actuator``,
``PostconditionVerifier``, ``ReceiptLedger``, ``replay_verify``, ``admit``.
"""

from .admission import AdmissionResult, admit, admit_typed
from .broker import (
    ActionToken,
    Actuator,
    Broker,
    BrokerError,
    ClosedAction,
    OpenedAction,
    PostconditionVerifier,
)
from .cert import Certificate
from .core import Digest
from .llm_agent import LLMOptimizationAgent, is_server_available
from .ocel_adapter import trajectory_to_ocel_log
from .optimization_agent import (
    OcelPerformanceScore,
    OptimizationDecision,
    PlanPerformanceAgent,
    score_log,
)
from .planning_types import PlanStepOutcome
from .receipt_store import ReceiptLedger
from .replay import ReplayReport, verify as replay_verify

__all__ = [
    "Digest",
    "Certificate",
    "PlanStepOutcome",
    "trajectory_to_ocel_log",
    "OcelPerformanceScore",
    "OptimizationDecision",
    "PlanPerformanceAgent",
    "score_log",
    "LLMOptimizationAgent",
    "is_server_available",
    "Broker",
    "BrokerError",
    "Actuator",
    "PostconditionVerifier",
    "ActionToken",
    "OpenedAction",
    "ClosedAction",
    "ReceiptLedger",
    "replay_verify",
    "ReplayReport",
    "admit",
    "admit_typed",
    "AdmissionResult",
]
