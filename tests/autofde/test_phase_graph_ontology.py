# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for ``autofde_lab.autofde.ontology``.

``ontology/autofde-phase-graph.ttl``'s A-Box is hand-authored -- a parallel,
hand-maintained twin of ``AUTOFDE_PHASE_GRAPH`` with no generator and no
drift check, unlike ``autofde-lab-capabilities.ttl``. This file's job: prove
the *generated* A-Box (``ontology/autofde-phase-graph-instances.ttl``, from
``autofde_lab.autofde.ontology``) is logically equivalent to the
hand-authored one, and stays that way -- a real check, not a hope.
"""

from __future__ import annotations

import re
from pathlib import Path

from autofde_lab.autofde.ontology import emit_turtle, generate
from autofde_lab.autofde.phase_graph import AUTOFDE_PHASE_GRAPH

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HAND_AUTHORED = REPO_ROOT / "ontology" / "autofde-phase-graph.ttl"
GENERATED = REPO_ROOT / "ontology" / "autofde-phase-graph-instances.ttl"

_TRIPLE_RE = re.compile(
    r"afde:([\w-]+)\s+afde:(phasePrecedes|precedes|supersedes)\s+afde:([\w-]+)\s*\."
)
_PHASE_BLOCK_RE = re.compile(
    r'afde:([\w-]+) a afde:Phase\s*;\s*'
    r'afde:nodeId "([^"]*)"\s*;\s*'
    r'afde:title "([^"]*)"\s*;\s*'
    r'afde:dueDate "([^"]*)"\s*\.',
)
_ITEM_BLOCK_RE = re.compile(
    r"afde:([\w-]+) a afde:WorkItem\s*;.*?"
    r"afde:hasClassification afde:(\w+)\s*;.*?"
    r"afde:hasStatus afde:(\w+)\s*;.*?"
    r"afde:occurrence (\d+)\s*\.",
    re.DOTALL,
)


def _relation_triples(text: str, predicate: str) -> frozenset[tuple[str, str]]:
    return frozenset(
        (m.group(1), m.group(3))
        for m in _TRIPLE_RE.finditer(text)
        if m.group(2) == predicate
    )


def _phase_facts(text: str) -> frozenset[tuple[str, str, str, str]]:
    return frozenset(m.groups() for m in _PHASE_BLOCK_RE.finditer(text))


def _item_facts(text: str) -> frozenset[tuple[str, str, str, str]]:
    return frozenset(
        (m.group(1), m.group(2), m.group(3), m.group(4))
        for m in _ITEM_BLOCK_RE.finditer(text)
    )


def test_the_committed_generated_file_matches_a_fresh_regeneration():
    """The file in the repo must be exactly what generating it now produces."""
    assert GENERATED.exists(), f"missing {GENERATED} -- run `python -m autofde_lab.autofde.ontology`"
    committed = GENERATED.read_text()
    fresh = emit_turtle(AUTOFDE_PHASE_GRAPH)
    assert committed == fresh, (
        "ontology/autofde-phase-graph-instances.ttl is stale -- regenerate with "
        "`python -m autofde_lab.autofde.ontology`, never hand-edit"
    )


def test_generated_abox_is_logically_equivalent_to_the_hand_authored_one():
    """Real equivalence check: same phases, same items, same relations --
    order and formatting may differ, the facts must not."""
    hand = HAND_AUTHORED.read_text()
    generated = GENERATED.read_text()
    failures: list[str] = []

    hand_phases = _phase_facts(hand)
    gen_phases = _phase_facts(generated)
    if hand_phases != gen_phases:
        failures.append(
            f"phase facts differ: hand-only={hand_phases - gen_phases!r} "
            f"generated-only={gen_phases - hand_phases!r}"
        )

    hand_items = _item_facts(hand)
    gen_items = _item_facts(generated)
    if hand_items != gen_items:
        failures.append(
            f"work-item facts differ: hand-only={hand_items - gen_items!r} "
            f"generated-only={gen_items - hand_items!r}"
        )

    for predicate in ("phasePrecedes", "precedes", "supersedes"):
        hand_rel = _relation_triples(hand, predicate)
        gen_rel = _relation_triples(generated, predicate)
        if hand_rel != gen_rel:
            failures.append(
                f"afde:{predicate} triples differ: "
                f"hand-only={hand_rel - gen_rel!r} generated-only={gen_rel - hand_rel!r}"
            )

    assert not failures, "\n".join(failures)


def test_generate_writes_the_exact_same_content_as_emit_turtle(tmp_path):
    """`generate()` is not a second code path -- confirm it writes emit_turtle's
    own output byte-for-byte, real file I/O, no mocks."""
    out = tmp_path / "phase-graph-instances.ttl"
    generate(str(out))
    assert out.read_text() == emit_turtle(AUTOFDE_PHASE_GRAPH)


def test_every_work_item_kind_is_a_declared_classification():
    """A real, not merely hoped-for, guard: emit_turtle refuses (raises) rather
    than silently emitting an undeclared afde:Classification individual."""
    from dataclasses import replace

    from autofde_lab.autofde.phase_graph import PhaseGraph

    bad_item = replace(AUTOFDE_PHASE_GRAPH.items[0], node_id="zz-test-only", kind="NotARealKind")
    bad_graph = PhaseGraph(
        phases=AUTOFDE_PHASE_GRAPH.phases,
        items=AUTOFDE_PHASE_GRAPH.items + (bad_item,),
    )
    try:
        emit_turtle(bad_graph)
        raised = False
    except ValueError as exc:
        raised = True
        assert "NotARealKind" in str(exc)
    assert raised, "an undeclared classification must be refused, not silently emitted"
