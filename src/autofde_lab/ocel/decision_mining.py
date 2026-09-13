# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Decision-point mining precursor: is a domain's compatible-solver set
*deterministic* given only the domain identity, or does it vary across
matches?

This is deliberately **not** full guard-condition mining (Rozinat & van der
Aalst 2006 -- correlating case *data attributes* to which XOR branch a case
takes). That requires a per-candidate-solver rejection-reason capture change
in ``utils.py::match_solvers`` -- a materially larger change, out of scope
here. What today's captured data *can* support: ``decision_match`` events
now carry the actual ``compatible_solvers`` name tuple (not just a count --
see ``ocel/mcp_instrumentation.py::_outcome_from_result`` and
``ocel/mcp_session.py::append_tool_call_event``), so we can ask a real,
checkable question -- does the same domain always produce the same
compatible-solver set every time it is matched?

``is_deterministic=False`` for a domain is the actual precursor signal to
guard-condition mining: it is direct evidence that *something* uncaptured
(solver-registry changes between matches, a hidden data attribute, ...) is
driving the branch, since domain identity alone does not explain it.

Like ``ocel/enhancement.py`` and ``ocel/resource_perspective.py``, this only
computes and reports -- no actuation, no admission, no receipt semantics.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

__all__ = ["DomainDecisionStability", "compatible_solver_set_stability"]


@dataclass(frozen=True)
class DomainDecisionStability:
    domain_id: str
    distinct_solver_sets: int
    is_deterministic: bool
    """``True`` only when every observed ``decision_match`` for this domain
    produced the identical ``compatible_solvers`` set."""


def compatible_solver_set_stability(conn: sqlite3.Connection) -> list[DomainDecisionStability]:
    """Real per-domain compatible-solver-set determinism, from every
    ``decision_match`` event that carries a ``compatible_solvers`` attribute.

    A domain with zero such events (e.g. captured before this attribute was
    added, or never matched at all) is absent -- there is nothing to
    classify. Sorted by ``domain_id``.
    """
    rows = conn.execute(
        """
        SELECT o.id AS domain_id, a.value_json
        FROM events e
        JOIN attributes a
            ON a.owner_table = 'event' AND a.owner_id = e.id AND a.key = 'compatible_solvers'
        JOIN event_object_links l ON l.event_id = e.id
        JOIN objects o ON o.id = l.object_id AND o.object_type = 'Domain'
        WHERE e.activity = 'decision_match'
        ORDER BY o.id
        """
    ).fetchall()

    observed_sets: dict[str, set[tuple[str, ...]]] = {}
    for row in rows:
        solver_set = tuple(sorted(json.loads(row["value_json"])))
        observed_sets.setdefault(row["domain_id"], set()).add(solver_set)

    results = [
        DomainDecisionStability(
            domain_id=domain_id,
            distinct_solver_sets=len(sets),
            is_deterministic=len(sets) == 1,
        )
        for domain_id, sets in observed_sets.items()
    ]
    results.sort(key=lambda row: row.domain_id)
    return results
