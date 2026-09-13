# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Record a real MCP tool call as a real OCEL 2.0 event.

Generalized from ``notebooks/18_mcp_user_simulation_ocel.ipynb``'s
``log_solve_event``/``log_match_event`` helpers, which had nothing
notebook-specific in their logic -- any future code recording real MCP
session activity as OCEL (a second notebook, a CLI flag, a monitoring hook)
would otherwise re-derive the same attribute shape (``standing``,
``elapsed_s``, ``detail``, receipt-digest passthrough) from scratch.
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import OcelAttributeValue

__all__ = ["append_tool_call_event"]


def append_tool_call_event(
    log: OcelLog,
    *,
    event_id: str,
    activity: str,
    object_ids: Sequence[str],
    outcome: Mapping[str, Any],
    timestamp_ns: int | None = None,
) -> OcelLog:
    """Append one MCP tool-call outcome as a real OCEL event.

    ``outcome`` is expected to carry a ``"standing"`` key (e.g.
    ``SOLVED``/``BOUNDED``/``REFUSED``/``TIMEOUT``/``ERROR``/``MATCHED``); any
    of the following optional keys are carried through as typed OCEL
    attributes when present: ``elapsed_s`` (float), ``steps``/``steps_taken``
    (int), ``receipt_sha256`` (str), ``detail``/``error`` (str, truncated to
    500 chars), ``action_result`` (any value, recorded as its ``str()``,
    truncated to 500 chars -- e.g. a real bound action callable's return
    value, see :func:`autofde_lab.ocel.powl_replay.replay_structural_fires`),
    any other numeric ``*_count`` key, and ``compatible_solvers``
    (list[str], recorded as an OCEL list attribute -- see
    :mod:`autofde_lab.ocel.decision_mining`).

    Does not call :meth:`OcelLog.validate` -- the caller decides when to
    validate (typically once, after the whole session is logged), matching
    ``OcelLog.append_event``'s own contract that objects must already exist.
    """
    attrs: dict[str, OcelAttributeValue] = {
        "standing": OcelAttributeValue.string(str(outcome["standing"])),
    }
    if "elapsed_s" in outcome:
        attrs["elapsed_s"] = OcelAttributeValue.floating(round(float(outcome["elapsed_s"]), 3))
    for steps_key in ("steps_taken", "steps"):
        if steps_key in outcome:
            attrs["steps_taken"] = OcelAttributeValue.integer(int(outcome[steps_key]))
            break
    if outcome.get("receipt_sha256"):
        attrs["receipt_sha256"] = OcelAttributeValue.string(str(outcome["receipt_sha256"]))
    for detail_key in ("detail", "error"):
        if outcome.get(detail_key):
            attrs["detail"] = OcelAttributeValue.string(str(outcome[detail_key])[:500])
            break
    # ``detail`` and ``error`` are independent claims (e.g. a POWL action
    # binding error carries both: ``detail`` the fired Atom's label,
    # ``error`` the real exception type/message) -- when both are present
    # the loop above's first-match-wins only ever wrote ``detail``, silently
    # dropping the real error text. Give ``error`` its own attribute
    # whenever it is present, regardless of whether ``detail`` also is.
    if outcome.get("error"):
        attrs["error"] = OcelAttributeValue.string(str(outcome["error"])[:500])
    if "action_result" in outcome and outcome["action_result"] is not None:
        attrs["action_result"] = OcelAttributeValue.string(
            str(outcome["action_result"])[:500]
        )
    for key, value in outcome.items():
        if key.endswith("_count") and isinstance(value, int):
            attrs[key] = OcelAttributeValue.integer(value)
    if isinstance(outcome.get("compatible_solvers"), (list, tuple)):
        attrs["compatible_solvers"] = OcelAttributeValue.listing(
            OcelAttributeValue.string(str(s)) for s in outcome["compatible_solvers"]
        )

    return log.append_event(
        event_id,
        activity,
        list(object_ids),
        timestamp_ns=timestamp_ns if timestamp_ns is not None else time.time_ns(),
        attributes=attrs,
    )
