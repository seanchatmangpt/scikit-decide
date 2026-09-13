# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Mermaid as a deterministic projection of the OCEL graph — never hand-authored.

The diagram is a **view for a human**, not evidence. It is therefore generated
by querying the durable OCEL 2.0 log, so it can only ever show relations that
are actually in the graph:

    durable OCEL 2.0 -> query -> Mermaid

Two rules make it a projection rather than an illustration:

1. **Only explicit typed object-to-object edges are drawn.** Event-to-object
   co-reference is not an edge (an event naming two objects does not assert
   those objects are related), and no edge is ever inferred from ordering,
   timestamps, labels or counts.
2. **An absent edge is absent from the diagram.** The temptation to draw the
   intended chain and mark missing links differently is exactly how a diagram
   starts asserting more than the evidence does. What is missing shows up as a
   node with no incoming arrow, which is the honest rendering.

Consequence worth stating: a diagram produced from an incomplete episode looks
sparse and disconnected. That is the correct output, not a rendering bug.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

#: Chain roles, in the order a reader should scan them. Used only for stable
#: node ordering -- membership here never causes a node or edge to be drawn.
_ROLE_ORDER: tuple[str, ...] = (
    "Task",
    "Goal",
    "PlanCandidate",
    "POWLCommitment",
    "AuthorityEnvelope",
    "Actuation",
    "PostconditionObservation",
    "IndependentVerifier",
    "Receipt",
    "Replay",
)


def _short(identity: str, keep: int = 12) -> str:
    """Shorten an identity for display while keeping it recognisable."""
    if len(identity) <= keep * 2 + 1:
        return identity
    return f"{identity[:keep]}…{identity[-6:]}"


def _node_id(raw: str) -> str:
    """A mermaid-safe, **injective** node id derived from the real object id.

    The digest suffix is not decoration. Sanitising and truncating alone is not
    injective -- two distinct object ids sharing a 48-character prefix (routine
    for URN-shaped ids such as ``urn:gymact:resource_flow:capability:...``)
    would collapse into one node, silently merging two objects and re-pointing
    every edge that touched either of them. That is the diagram asserting a
    relation the log does not contain, which rule 1 in this module forbids.
    """
    slug = "".join(c if c.isalnum() else "_" for c in raw)[:48]
    return "n" + slug + "_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def _label(text: str) -> str:
    """Escape text for a Mermaid quoted node label.

    A raw ``"`` in an object id or type terminates the label early and yields a
    diagram that will not parse; ``<`` would open a stray tag. Both are escaped
    to Mermaid/HTML entities so the projection of a hostile-but-legal OCEL log
    is still syntactically valid Mermaid.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace('"', "#quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def ocel_to_mermaid(log: dict, title: str = "") -> str:
    """Project an OCEL 2.0 log into a Mermaid flowchart.

    Draws one node per object and one arrow per **explicit** object-to-object
    relationship, labelled with the real qualifier. Nothing else.
    """
    objects = log.get("objects", []) or []
    by_id = {o.get("id"): o for o in objects if o.get("id")}

    def sort_key(obj: dict) -> tuple[int, str]:
        otype = obj.get("type", "")
        rank = _ROLE_ORDER.index(otype) if otype in _ROLE_ORDER else len(_ROLE_ORDER)
        return (rank, str(obj.get("id", "")))

    lines: list[str] = ["flowchart LR"]
    if title:
        lines.insert(0, f"%% {title}")

    for obj in sorted(objects, key=sort_key):
        oid = obj.get("id", "")
        otype = obj.get("type", "?")
        lines.append(f'    {_node_id(oid)}["{_label(otype)}<br/>{_label(_short(oid))}"]')

    edge_count = 0
    for obj in sorted(objects, key=sort_key):
        src = obj.get("id", "")
        for rel in obj.get("relationships", []) or []:
            tgt = rel.get("objectId")
            if not tgt or tgt not in by_id:
                # A dangling target is NOT drawn. Drawing it would invent a
                # node the evidence does not contain.
                continue
            qual = rel.get("qualifier", "")
            # ``|`` would terminate the arrow label early; the qualifier is real
            # log content and is escaped, never dropped.
            label = f'|"{_label(qual).replace("|", "&#124;")}"|' if qual else ""
            lines.append(f"    {_node_id(src)} -->{label} {_node_id(tgt)}")
            edge_count += 1

    if edge_count == 0:
        lines.append("    %% NO EXPLICIT OBJECT-TO-OBJECT EDGES IN THIS EPISODE.")
        lines.append("    %% Disconnected nodes are the honest rendering of a graph")
        lines.append("    %% whose producer did not emit typed relationships.")
    return "\n".join(lines)


def federation_to_mermaid(federation: list[dict], committed_plan: list[str] | None = None) -> str:
    """Project a real federation.json into a Mermaid flowchart.

    Shows every planner that actually ran and its real typed outcome -- the
    refusals and non-candidates included, because a federation diagram that
    shows only the winners misrepresents what happened.
    """
    lines = ["flowchart TD", '    D["DiscoveredDomain"]']
    committed = tuple(committed_plan or ())
    for i, attempt in enumerate(federation):
        planner = attempt.get("planner") or attempt.get("planner_identity") or f"planner{i}"
        outcome = attempt.get("outcome", "UNKNOWN")
        plan = tuple(attempt.get("plan") or attempt.get("candidate_plan") or ())
        pid = _node_id(f"p{planner}")
        oid = _node_id(f"o{planner}")
        lines.append(f'    {pid}["{_label(planner)}"]')
        lines.append(f"    D --> {pid}")
        if outcome == "PLAN_CANDIDATE":
            marker = " ✓committed" if committed and plan == committed else ""
            lines.append(f'    {oid}["PlanCandidate<br/>{len(plan)} steps{marker}"]')
        else:
            lines.append(f'    {oid}["{_label(outcome)}"]')
        lines.append(f"    {pid} --> {oid}")
    return "\n".join(lines)


def mermaid_for_trial(trial_dir: Path) -> str:
    """Read a trial's durable OCEL and project it. Files only."""
    act = trial_dir / "actuation"
    for name in ("level4.ocel.json", "episode.ocel.json"):
        path = act / name
        if path.is_file():
            return ocel_to_mermaid(json.loads(path.read_text()), title=f"{trial_dir.name} ({name})")
    return (
        "%% NO OCEL LOG ON DISK for "
        f"{trial_dir.name} -- nothing to project. Absence is not an empty graph;\n"
        "%% it is an unanswerable question."
    )


def main(argv: list[str]) -> int:
    import sys

    if len(argv) != 2:
        print("usage: mermaid_projection.py <trial_dir>", file=sys.stderr)
        return 2
    print(mermaid_for_trial(Path(argv[1])))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv))
