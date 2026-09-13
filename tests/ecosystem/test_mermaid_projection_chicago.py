# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests pinning the honesty of the Mermaid OCEL projection.

The module under test declares that the diagram is a **view, never evidence**:
it may draw only explicit typed object-to-object relationships that are really
in the durable log. These tests are adversarial about exactly that. Every test
builds a real OCEL dict (or a real file on a real temporary directory) and
asserts on the real emitted string -- no mocks, no interaction assertions.

The central test is :func:`test_all_chain_nodes_no_relationships_draws_no_edges`:
a log containing every node of the intended chain and *no* relationships must
produce a diagram with no arrow at all. A projection that draws the intended
chain because the node types exist has stopped being a projection.

Syntactic validity is checked against the real Mermaid parser (``mmdc``, the
``@mermaid-js/mermaid-cli`` package, fetched by ``npx``) when it is reachable,
and is otherwise skipped by name -- never silently replaced by a weaker check.
A structural check (declared-node / well-formed-arrow) runs unconditionally on
every machine.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from autofde_lab.ocel.mermaid_projection import (
    federation_to_mermaid,
    mermaid_for_trial,
    ocel_to_mermaid,
)

# --------------------------------------------------------------------------
# Real OCEL fixtures -- plain dicts, exactly the shape the projection reads.
# --------------------------------------------------------------------------

#: Every node of the intended chain, in the roles the module knows about.
_CHAIN_ROLES = (
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


def _obj(oid: str, otype: str, rels: list[dict] | None = None) -> dict:
    o: dict = {"id": oid, "type": otype}
    if rels is not None:
        o["relationships"] = rels
    return o


def _chain_nodes_only() -> dict:
    """A log with all chain NODES present and not one relationship."""
    return {
        "objects": [_obj(f"urn:test:{r.lower()}:0001", r) for r in _CHAIN_ROLES],
        "events": [],
    }


def _arrow_lines(diagram: str) -> list[str]:
    return [ln.strip() for ln in diagram.splitlines() if "-->" in ln and not ln.strip().startswith("%%")]


def _declared_node_ids(diagram: str) -> set[str]:
    ids = set()
    for line in diagram.splitlines():
        m = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)\[", line)
        if m:
            ids.add(m.group(1))
    return ids


_ARROW_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9_]*)\s+-->(?:\|\"[^\"]*\"\|)?\s+([A-Za-z][A-Za-z0-9_]*)$"
)


# --------------------------------------------------------------------------
# 1. A real edge IS drawn, with its real qualifier as the arrow label.
# --------------------------------------------------------------------------


def test_explicit_relationship_is_drawn_with_its_real_qualifier():
    log = {
        "objects": [
            _obj("urn:test:task:A", "Task", [{"objectId": "urn:test:goal:B", "qualifier": "pursues"}]),
            _obj("urn:test:goal:B", "Goal"),
        ]
    }
    out = ocel_to_mermaid(log)

    arrows = _arrow_lines(out)
    assert len(arrows) == 1, out
    # The qualifier is the REAL one from the log, not a role-derived guess.
    assert "pursues" in arrows[0], arrows[0]
    src, tgt = _ARROW_RE.match(arrows[0]).groups()
    declared = _declared_node_ids(out)
    assert {src, tgt} <= declared
    assert src != tgt
    # The "no edges" honesty comment must NOT appear when an edge exists.
    assert "NO EXPLICIT OBJECT-TO-OBJECT EDGES" not in out


def test_qualifier_is_verbatim_not_normalised():
    """An unusual real qualifier is rendered as-is -- the view does not tidy evidence."""
    log = {
        "objects": [
            _obj("A", "Task", [{"objectId": "B", "qualifier": "hasWeirdQualifier_v2"}]),
            _obj("B", "Goal"),
        ]
    }
    assert "hasWeirdQualifier_v2" in ocel_to_mermaid(log)


# --------------------------------------------------------------------------
# 2. THE CENTRAL TEST -- all chain nodes, no relationships, therefore no arrows.
# --------------------------------------------------------------------------


def test_all_chain_nodes_no_relationships_draws_no_edges():
    """A diagram must not draw the intended chain just because the node types exist."""
    out = ocel_to_mermaid(_chain_nodes_only())

    # All ten nodes really are present...
    for role in _CHAIN_ROLES:
        assert role in out, f"{role} node missing from {out}"
    # ...and not one arrow is drawn between them.
    assert "-->" not in out, f"projection invented edges:\n{out}"
    assert _arrow_lines(out) == []
    # The absence is stated explicitly rather than left to be misread as a bug.
    assert "NO EXPLICIT OBJECT-TO-OBJECT EDGES IN THIS EPISODE." in out


def test_empty_relationship_list_is_still_no_edges():
    log = {"objects": [_obj("A", "Task", []), _obj("B", "Goal", [])]}
    out = ocel_to_mermaid(log)
    assert "-->" not in out
    assert "NO EXPLICIT OBJECT-TO-OBJECT EDGES" in out


def test_partial_chain_draws_only_the_links_that_exist():
    """Two real links out of nine possible: exactly two arrows, no bridging."""
    objs = [_obj(f"urn:test:{r.lower()}", r) for r in _CHAIN_ROLES]
    by = {o["type"]: o for o in objs}
    by["Task"]["relationships"] = [{"objectId": "urn:test:goal", "qualifier": "pursues"}]
    by["Receipt"]["relationships"] = [{"objectId": "urn:test:replay", "qualifier": "replayedBy"}]
    out = ocel_to_mermaid({"objects": objs})

    arrows = _arrow_lines(out)
    assert len(arrows) == 2, out
    # Specifically: no arrow was manufactured across the gap in the middle.
    assert "actuation" not in " ".join(arrows)


# --------------------------------------------------------------------------
# 3. A relationship pointing at a NONEXISTENT object is not drawn, and does
#    not conjure a node for the missing target.
# --------------------------------------------------------------------------


def test_dangling_relationship_target_is_not_drawn_and_invents_no_node():
    log = {
        "objects": [
            _obj("urn:test:task:A", "Task", [{"objectId": "urn:test:ghost:Z", "qualifier": "pursues"}]),
        ]
    }
    out = ocel_to_mermaid(log)

    assert "-->" not in out, out
    assert "ghost" not in out, f"projection invented a node for a dangling target:\n{out}"
    # Exactly one node -- the one object that really exists.
    assert len(_declared_node_ids(out)) == 1
    assert "NO EXPLICIT OBJECT-TO-OBJECT EDGES" in out


def test_relationship_with_missing_objectId_key_is_not_drawn():
    log = {"objects": [_obj("A", "Task", [{"qualifier": "pursues"}]), _obj("B", "Goal")]}
    out = ocel_to_mermaid(log)
    assert "-->" not in out


def test_only_the_resolvable_half_of_a_mixed_pair_is_drawn():
    log = {
        "objects": [
            _obj(
                "A",
                "Task",
                [
                    {"objectId": "B", "qualifier": "real"},
                    {"objectId": "NOPE", "qualifier": "dangling"},
                ],
            ),
            _obj("B", "Goal"),
        ]
    }
    out = ocel_to_mermaid(log)
    arrows = _arrow_lines(out)
    assert len(arrows) == 1
    assert "real" in arrows[0]
    assert "dangling" not in out
    assert "NOPE" not in out


# --------------------------------------------------------------------------
# 4. Event-to-object co-reference is NOT an edge.
# --------------------------------------------------------------------------


def test_event_co_reference_between_two_objects_is_not_an_edge():
    """An event naming two objects does not assert those objects are related."""
    log = {
        "objects": [_obj("urn:test:task:A", "Task"), _obj("urn:test:goal:B", "Goal")],
        "events": [
            {
                "id": "e1",
                "type": "PlanComputed",
                "time": "2026-08-08T00:00:00Z",
                "relationships": [
                    {"objectId": "urn:test:task:A", "qualifier": "input"},
                    {"objectId": "urn:test:goal:B", "qualifier": "output"},
                ],
            }
        ],
    }
    out = ocel_to_mermaid(log)

    assert "-->" not in out, f"event co-reference became an object edge:\n{out}"
    assert "NO EXPLICIT OBJECT-TO-OBJECT EDGES" in out
    # The event's own qualifiers must not leak into the object diagram either.
    assert "input" not in out and "output" not in out


def test_many_events_over_the_full_chain_still_yield_no_edges():
    """Volume of co-reference is not evidence of relation."""
    objs = [_obj(f"urn:test:{r.lower()}", r) for r in _CHAIN_ROLES]
    events = [
        {
            "id": f"e{i}",
            "type": "Step",
            "relationships": [{"objectId": o["id"], "qualifier": "touches"} for o in objs],
        }
        for i in range(20)
    ]
    out = ocel_to_mermaid({"objects": objs, "events": events})
    assert "-->" not in out, out


# --------------------------------------------------------------------------
# 5. Determinism and stable ordering.
# --------------------------------------------------------------------------


def test_projection_is_byte_identical_across_repeated_calls():
    log = _chain_nodes_only()
    log["objects"][0]["relationships"] = [{"objectId": log["objects"][1]["id"], "qualifier": "q"}]
    first = ocel_to_mermaid(log, title="t")
    for _ in range(5):
        assert ocel_to_mermaid(log, title="t") == first


def test_node_order_is_stable_regardless_of_input_object_order():
    forward = _chain_nodes_only()
    reversed_input = {"objects": list(reversed(forward["objects"])), "events": []}
    shuffled = {"objects": [forward["objects"][i] for i in (4, 0, 9, 2, 7, 1, 8, 3, 6, 5)]}

    a = ocel_to_mermaid(forward)
    b = ocel_to_mermaid(reversed_input)
    c = ocel_to_mermaid(shuffled)
    assert a == b == c, "node ordering depends on input order"


def test_edge_order_is_stable_regardless_of_input_object_order():
    objs = [
        _obj("A", "Task", [{"objectId": "B", "qualifier": "q1"}]),
        _obj("B", "Goal", [{"objectId": "C", "qualifier": "q2"}]),
        _obj("C", "Receipt"),
    ]
    assert ocel_to_mermaid({"objects": objs}) == ocel_to_mermaid({"objects": list(reversed(objs))})


def test_distinct_ids_sharing_a_long_prefix_stay_distinct_nodes():
    """Truncation must not merge two real objects into one node.

    URN-shaped ids routinely share more than 48 leading characters. A collision
    here would silently merge two objects and re-point every edge touching
    either of them -- the diagram asserting a relation the log does not contain.
    """
    a = "urn:gymact:resource_flow:capability:burn_catalyst_alpha"
    b = "urn:gymact:resource_flow:capability:burn_catalyst_beta"
    assert a[:48] == b[:48], "fixture no longer exercises the prefix collision"
    out = ocel_to_mermaid({"objects": [_obj(a, "capability"), _obj(b, "capability")]})
    assert len(_declared_node_ids(out)) == 2, f"two distinct objects collapsed into one node:\n{out}"


def test_prefix_colliding_ids_do_not_misroute_an_edge():
    a = "urn:gymact:resource_flow:capability:burn_catalyst_alpha"
    b = "urn:gymact:resource_flow:capability:burn_catalyst_beta"
    out = ocel_to_mermaid(
        {"objects": [_obj(a, "capability", [{"objectId": b, "qualifier": "feeds"}]), _obj(b, "capability")]}
    )
    arrows = _arrow_lines(out)
    assert len(arrows) == 1
    src, tgt = _ARROW_RE.match(arrows[0]).groups()
    assert src != tgt, f"edge became a self-loop through node-id collision:\n{out}"


# --------------------------------------------------------------------------
# 6. federation_to_mermaid shows EVERY planner, refusals included.
# --------------------------------------------------------------------------


def _real_federation() -> list[dict]:
    return [
        {"planner": "lazy_astar", "outcome": "PLAN_CANDIDATE", "plan": ["mine", "refine", "assemble"]},
        {"planner": "rllib_dqn", "outcome": "UNSUPPORTED:REQUIRES_CONFIGURATION"},
        {"planner": "cgp", "outcome": "FAILED"},
    ]


def test_federation_shows_every_planner_including_refusal_and_failure():
    out = federation_to_mermaid(_real_federation(), committed_plan=["mine", "refine", "assemble"])

    for planner in ("lazy_astar", "rllib_dqn", "cgp"):
        assert planner in out, f"{planner} dropped from federation diagram:\n{out}"
    assert "UNSUPPORTED:REQUIRES_CONFIGURATION" in out
    assert "FAILED" in out
    assert "PlanCandidate" in out
    assert "3 steps" in out
    # The committed plan is marked, and marked only where it really matches.
    assert "✓committed" in out
    assert out.count("✓committed") == 1


def test_federation_marks_no_winner_when_nothing_matches_the_commitment():
    out = federation_to_mermaid(_real_federation(), committed_plan=["something", "else"])
    assert "✓committed" not in out
    # Losing candidates are still shown.
    assert "lazy_astar" in out and "PlanCandidate" in out


def test_federation_of_only_refusals_still_renders_all_of_them():
    fed = [
        {"planner": "a", "outcome": "UNSUPPORTED:REQUIRES_CONFIGURATION"},
        {"planner": "b", "outcome": "FAILED"},
    ]
    out = federation_to_mermaid(fed)
    assert "a" in out and "b" in out
    assert "PlanCandidate" not in out


# --------------------------------------------------------------------------
# 7. Absence on disk is stated, not rendered as an empty graph.
# --------------------------------------------------------------------------


def test_trial_dir_with_no_ocel_log_says_nothing_to_project(tmp_path: Path):
    trial = tmp_path / "realtrial_0000_empty"
    (trial / "actuation").mkdir(parents=True)
    out = mermaid_for_trial(trial)

    assert "nothing to project" in out
    assert "Absence is not an empty graph" in out
    # Crucially: it is NOT an empty flowchart, which would read as "no relations".
    assert "flowchart" not in out
    assert "-->" not in out


def test_trial_dir_that_does_not_exist_at_all_says_nothing_to_project(tmp_path: Path):
    out = mermaid_for_trial(tmp_path / "no_such_trial")
    assert "nothing to project" in out
    assert "flowchart" not in out


def test_trial_dir_with_a_real_ocel_file_is_projected_from_that_file(tmp_path: Path):
    trial = tmp_path / "realtrial_0001"
    act = trial / "actuation"
    act.mkdir(parents=True)
    log = {
        "objects": [
            _obj("urn:t:task", "Task", [{"objectId": "urn:t:goal", "qualifier": "pursues"}]),
            _obj("urn:t:goal", "Goal"),
        ]
    }
    (act / "episode.ocel.json").write_text(json.dumps(log))

    out = mermaid_for_trial(trial)
    assert "flowchart LR" in out
    assert "episode.ocel.json" in out  # title names the real source file
    assert len(_arrow_lines(out)) == 1
    assert "pursues" in out


def test_level4_log_is_preferred_over_episode_log(tmp_path: Path):
    trial = tmp_path / "realtrial_0002"
    act = trial / "actuation"
    act.mkdir(parents=True)
    (act / "level4.ocel.json").write_text(json.dumps({"objects": [_obj("L", "Receipt")]}))
    (act / "episode.ocel.json").write_text(json.dumps({"objects": [_obj("E", "Task")]}))

    out = mermaid_for_trial(trial)
    assert "level4.ocel.json" in out
    assert "Receipt" in out and "Task" not in out


# --------------------------------------------------------------------------
# The real, on-disk episode this projection was written against.
# --------------------------------------------------------------------------

_REAL_TRIAL_GLOB = (
    "/private/tmp/claude-501/-Users-sac-autofde-lab/"
    "a420c968-955c-43ee-8074-b768d3016a7e/scratchpad/ev_a5/realtrial_3979297810_*"
)


def _real_trial_dir() -> Path | None:
    import glob

    hits = sorted(glob.glob(_REAL_TRIAL_GLOB))
    return Path(hits[0]) if hits else None


@pytest.mark.skipif(_real_trial_dir() is None, reason="real ev_a5 trial dir not on this machine")
def test_real_gymact_episode_projects_to_disconnected_nodes():
    """The real episode really does have no O2O relationships -- so no arrows."""
    out = mermaid_for_trial(_real_trial_dir())
    assert "flowchart LR" in out
    assert _declared_node_ids(out), "real episode produced no nodes at all"
    assert "-->" not in out, f"real episode gained edges it does not have:\n{out}"
    assert "NO EXPLICIT OBJECT-TO-OBJECT EDGES IN THIS EPISODE." in out


# --------------------------------------------------------------------------
# Syntactic validity.
# --------------------------------------------------------------------------


def _structurally_valid(diagram: str) -> None:
    """Every referenced node id is declared, and every arrow is well formed."""
    assert diagram.splitlines(), "empty diagram"
    declared = _declared_node_ids(diagram)
    for arrow in _arrow_lines(diagram):
        m = _ARROW_RE.match(arrow)
        assert m is not None, f"malformed arrow line: {arrow!r}"
        src, tgt = m.groups()
        assert src in declared, f"arrow source {src} never declared: {arrow!r}"
        assert tgt in declared, f"arrow target {tgt} never declared: {arrow!r}"
    for line in diagram.splitlines():
        s = line.strip()
        if s.startswith("%%") or not s:
            continue
        # Labels must be balanced -- an unescaped quote would break the parser.
        if "[" in s:
            assert s.count('"') % 2 == 0, f"unbalanced quotes in label: {s!r}"


def _diagram_cases() -> list[tuple[str, str]]:
    chain = _chain_nodes_only()
    linked = json.loads(json.dumps(chain))
    linked["objects"][0]["relationships"] = [
        {"objectId": linked["objects"][1]["id"], "qualifier": "pursues"}
    ]
    hostile = {
        "objects": [
            _obj('id"with:quote', 'Ty"pe [bracket]', [{"objectId": "b<tag>", "qualifier": 'q"|x'}]),
            _obj("b<tag>", "Goal"),
        ]
    }
    cases = [
        ("chain_no_edges", ocel_to_mermaid(chain)),
        ("chain_one_edge", ocel_to_mermaid(linked, title="titled")),
        ("hostile_labels", ocel_to_mermaid(hostile)),
        ("federation", federation_to_mermaid(_real_federation(), ["mine", "refine", "assemble"])),
    ]
    real = _real_trial_dir()
    if real is not None:
        cases.append(("real_episode", mermaid_for_trial(real)))
    return cases


@pytest.mark.parametrize("name,diagram", _diagram_cases())
def test_diagram_is_structurally_valid(name, diagram):
    _structurally_valid(diagram)


def _mmdc_available() -> bool:
    if not shutil.which("npx"):
        return False
    try:
        r = subprocess.run(
            ["npx", "--yes", "@mermaid-js/mermaid-cli@11.16.0", "--version"],
            capture_output=True,
            timeout=600,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


_MMDC = _mmdc_available()


@pytest.mark.skipif(
    not _MMDC,
    reason="real mermaid parser (npx @mermaid-js/mermaid-cli) unreachable; "
    "structural validation still runs in test_diagram_is_structurally_valid",
)
@pytest.mark.parametrize("name,diagram", _diagram_cases())
def test_diagram_parses_with_the_real_mermaid_parser(name, diagram, tmp_path):
    """Hand the emitted string to the actual Mermaid CLI and require a render."""
    src = tmp_path / f"{name}.mmd"
    src.write_text(diagram)
    out = tmp_path / f"{name}.svg"
    env = dict(os.environ, PUPPETEER_DISABLE_HEADLESS_WARNING="true")
    conf = tmp_path / "pc.json"
    conf.write_text(json.dumps({"args": ["--no-sandbox"]}))
    r = subprocess.run(
        [
            "npx",
            "--yes",
            "@mermaid-js/mermaid-cli@11.16.0",
            "-i",
            str(src),
            "-o",
            str(out),
            "-p",
            str(conf),
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert r.returncode == 0, f"mmdc rejected {name}:\n{diagram}\n\nSTDERR:\n{r.stderr}"
    assert out.is_file() and out.stat().st_size > 0
