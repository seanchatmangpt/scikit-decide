# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Persistent agent runtime over POWL 2.0 candidate plans.

Computes candidate plans across epochs and records a two-phase occurrence
ledger. It never actuates, admits, brokers, or issues an authoritative receipt.
"""

from __future__ import annotations

from autofde_lab.agent.bridge import (
    IntentRegisteringPolicies,
    SessionRolloutCallback,
    action_labels,
    resolve_enabled_node,
)
from autofde_lab.agent.epoch import DecisionEpoch, atom_labels
from autofde_lab.agent.ledger import (
    IntentToken,
    LedgerPhase,
    LedgerRecord,
    OccurrenceLedger,
)
from autofde_lab.agent.models import AgentOutcome, EpochReceipt, EpochStanding
from autofde_lab.agent.refusals import (
    BLOCKED_ACTION_NODE_UNRESOLVED,
    BLOCKED_LEDGER_UNRESUMABLE,
    CLAIM_CEILING,
    AgentRefusal,
    AgentRefusalCode,
)
from autofde_lab.agent.session import AgentSession

__all__ = [
    "AgentOutcome",
    "AgentRefusal",
    "AgentRefusalCode",
    "AgentSession",
    "BLOCKED_ACTION_NODE_UNRESOLVED",
    "BLOCKED_LEDGER_UNRESUMABLE",
    "CLAIM_CEILING",
    "DecisionEpoch",
    "EpochReceipt",
    "EpochStanding",
    "IntentRegisteringPolicies",
    "IntentToken",
    "LedgerPhase",
    "LedgerRecord",
    "OccurrenceLedger",
    "SessionRolloutCallback",
    "action_labels",
    "atom_labels",
    "resolve_enabled_node",
]
