# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Schema identifiers for persisted and externally consumed artifacts.

These strings are the `VERSIONED_MIGRATION` category of
`docs/migration/AUTOFDE_LAB_RENAME.md`: they are written into receipts,
ledger rows, cache records and MCP payloads that outlive the process that
wrote them. They therefore **cannot be renamed by substitution**. A
substitution rename compiles, passes every test that only round-trips
in-process, and silently orphans every artifact already on disk -- the
reader stops recognising its own history and there is no error anywhere.

The discipline is **dual-read, single-write**:

- the writer emits exactly one identifier, the current one;
- the reader accepts the current one *and* every superseded one.

A rename is therefore expressed as a version bump under the new namespace
(`skdecide.agent.outcome/1` -> `autofde_lab.agent.outcome/2`), never as an
edit of the existing string. The old identifier stays in `LEGACY_*` for as
long as artifacts bearing it may still be read; deleting it is a separate,
deliberate act with its own evidence, not a side effect of a rename.

Not covered here, on purpose: the `urn:skdecide:*` IRI scheme in
`fabric/ontology.py`, which is a stable semantic identifier rather than a
versioned envelope and is not versioned at all.
"""

from __future__ import annotations

__all__ = [
    "EPOCH_RECEIPT_SCHEMA",
    "LEGACY_EPOCH_RECEIPT_SCHEMA",
    "ACCEPTED_EPOCH_RECEIPT_SCHEMAS",
    "AGENT_OUTCOME_SCHEMA",
    "LEGACY_AGENT_OUTCOME_SCHEMA",
    "ACCEPTED_AGENT_OUTCOME_SCHEMAS",
    "DECISION_RESULT_SCHEMA",
    "LEGACY_DECISION_RESULT_SCHEMA",
    "ACCEPTED_DECISION_RESULT_SCHEMAS",
    "FABRIC_SCHEMA",
    "LEGACY_FABRIC_SCHEMAS",
    "ACCEPTED_FABRIC_SCHEMAS",
    "CACHE_SCHEMA",
    "LEGACY_CACHE_SCHEMAS",
    "ACCEPTED_CACHE_SCHEMAS",
    "accepts",
]

# -- agent receipts -------------------------------------------------------

EPOCH_RECEIPT_SCHEMA = "autofde_lab.agent.epoch_receipt/2"
LEGACY_EPOCH_RECEIPT_SCHEMA = "skdecide.agent.epoch_receipt/1"
ACCEPTED_EPOCH_RECEIPT_SCHEMAS = frozenset(
    {EPOCH_RECEIPT_SCHEMA, LEGACY_EPOCH_RECEIPT_SCHEMA}
)

AGENT_OUTCOME_SCHEMA = "autofde_lab.agent.outcome/2"
LEGACY_AGENT_OUTCOME_SCHEMA = "skdecide.agent.outcome/1"
ACCEPTED_AGENT_OUTCOME_SCHEMAS = frozenset(
    {AGENT_OUTCOME_SCHEMA, LEGACY_AGENT_OUTCOME_SCHEMA}
)

DECISION_RESULT_SCHEMA = "autofde_lab.fabric.decision_result/2"
LEGACY_DECISION_RESULT_SCHEMA = "skdecide.fabric.decision_result/1"
ACCEPTED_DECISION_RESULT_SCHEMAS = frozenset(
    {DECISION_RESULT_SCHEMA, LEGACY_DECISION_RESULT_SCHEMA}
)

# -- decision fabric ------------------------------------------------------
#
# `skdecide.decision-fabric/2` was rewritten in place to
# `autofde_lab.decision-fabric/2` by the Phase 3 module-prefix pass -- a
# substitution rename of a persisted identifier, which is exactly what this
# module exists to prevent. It is corrected here rather than left: the write
# identifier moves to /3, and BOTH prior spellings are accepted on read, so
# artifacts written by either earlier build are still recognised.

FABRIC_SCHEMA = "autofde_lab.decision-fabric/3"
LEGACY_FABRIC_SCHEMAS = frozenset(
    {"skdecide.decision-fabric/2", "autofde_lab.decision-fabric/2"}
)
ACCEPTED_FABRIC_SCHEMAS = frozenset({FABRIC_SCHEMA}) | LEGACY_FABRIC_SCHEMAS

# -- ERRC cache -----------------------------------------------------------
#
# Same history as the fabric schema above: `skdecide.fabric.errc-cache/1`
# was substituted in place. Both prior spellings stay readable.

CACHE_SCHEMA = "autofde_lab.fabric.errc-cache/2"
LEGACY_CACHE_SCHEMAS = frozenset(
    {"skdecide.fabric.errc-cache/1", "autofde_lab.fabric.errc-cache/1"}
)
ACCEPTED_CACHE_SCHEMAS = frozenset({CACHE_SCHEMA}) | LEGACY_CACHE_SCHEMAS


def accepts(schema: str | None, accepted: frozenset[str]) -> bool:
    """Whether `schema` is a recognised spelling from `accepted`.

    Exists so a reader never compares against a single literal. A `==`
    against the current identifier is the bug this module documents: it
    rejects the reader's own history without saying so.
    """
    return schema in accepted
