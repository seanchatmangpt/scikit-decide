# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Machine-readable refusals for the persistent agent runtime.

Extends the pattern of :mod:`autofde_lab.fabric.models` (``RefusalCode`` /
``DecisionRefusal``) with an ``SKD-AGENT-NNN`` namespace. Nothing here admits,
brokers, actuates, or issues a receipt with authority: a refusal says a
*candidate plan computation* declined to proceed, and names why.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

__all__ = [
    "AgentRefusalCode",
    "AgentRefusal",
    "BLOCKED_ACTION_NODE_UNRESOLVED",
    "BLOCKED_LEDGER_UNRESUMABLE",
    "CLAIM_CEILING",
]

#: What an ``AgentOutcome`` is allowed to be read as. Stated on every receipt so
#: a consumer cannot silently promote a candidate plan into an admission.
CLAIM_CEILING = (
    "CANDIDATE_PLAN_ONLY: this runtime computes candidate plans. "
    "It does not actuate, admit, broker, or issue authoritative receipts."
)

#: Standing string used when the action->node correspondence cannot be resolved.
BLOCKED_ACTION_NODE_UNRESOLVED = "BLOCKED:ACTION_NODE_UNRESOLVED"

#: Standing string used when a ledger has an INTENDED record with no COMMITTED.
BLOCKED_LEDGER_UNRESUMABLE = "BLOCKED:LEDGER_UNRESUMABLE"


class AgentRefusalCode(StrEnum):
    """Stable refusal identifiers for the agent runtime."""

    SESSION_CLOSED = "SKD-AGENT-001"
    NO_OPEN_EPOCH = "SKD-AGENT-002"
    UNKNOWN_SUPERSEDED_EPOCH = "SKD-AGENT-003"
    PRESERVATION_VIOLATED = "SKD-AGENT-004"
    UNKNOWN_INTENT_TOKEN = "SKD-AGENT-005"
    LEDGER_UNRESUMABLE = "SKD-AGENT-006"
    ACTION_NODE_UNRESOLVED = "SKD-AGENT-007"
    INTENT_ALREADY_OUTSTANDING = "SKD-AGENT-008"
    EPOCH_MODEL_INVALID = "SKD-AGENT-009"
    BOUND_EXHAUSTED = "SKD-AGENT-010"


class AgentRefusal(ValueError):
    """A fail-closed, machine-readable agent refusal."""

    def __init__(
        self,
        code: AgentRefusalCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(f"{code.value}: {message}")

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible refusal payload."""
        return {
            "standing": "REFUSED",
            "code": self.code.value,
            "message": str(self),
            "details": self.details,
            "claim_ceiling": CLAIM_CEILING,
        }
