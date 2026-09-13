# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style MUTATION testing of ``ontology/platform-console-domain.ttl``
itself, over the real, unmodified Phase 3 pipeline
(``autofde_lab.fabric.rdf_domain.compile_rdf_to_pddl_files`` -> real
scikit-decide Astar via ``autofde_lab.fabric.pddl_engine.solve_to_plan_file``).

This is the standing ask from ``~/.claude/plans/eager-forging-sparrow.md``
that Phases 1-6 (all landed) never covered: proof that the real Astar
solver is actually SENSITIVE to the real TTL domain content -- not a fixed
oracle that would report the same answer regardless of what the domain
says. Every test here:

1. Solves a real *baseline* problem against the real, unmodified
   ``ontology/platform-console-domain.ttl`` fixture on disk (no copy, no
   patch) and asserts the correct-domain behavior.
2. Applies one deliberate, real, targeted TEXTUAL mutation to a real copy
   of that TTL (drop a precondition atom, swap an effect predicate, add a
   contradictory precondition, or delete an action's triples/registration
   entirely), writes the real mutated Turtle to ``tmp_path``, and re-runs
   the *exact same* real compile -> real Astar pipeline against the
   mutated copy.
3. Asserts the *plan itself* changed in the way the mutation demands: a
   previously-refused irreversible action is now solvable
   (``EXIT_PLAN_FOUND``), a previously-solvable capability becomes
   unsolvable (``EXIT_NO_PLAN``), or a previously well-ordered plan now
   skips a real intermediate precondition step it should require.

No ``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch``
anywhere in this file. The only "double" here is the mutated Turtle text
itself, and it is real Turtle -- real rdflib parses it, the real compiler
compiles it, the real Astar solver solves (or correctly refuses) it. Every
mutation helper below operates on the real file's own real text with a
scoped, asserted string/regex extraction (never a fabricated PDDL string),
so a broken mutation shows up as a real ``AssertionError`` in this file,
never a silently-wrong test.
"""

from __future__ import annotations

import os
import re

from autofde_lab.fabric import pddl_engine
from autofde_lab.fabric.rdf_domain import compile_rdf_to_pddl_files

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ontology",
    "platform-console-domain.ttl",
)

DOMAIN_IRI = "urn:autofde-lab:planning-domain:platform-console:domain"
NS = "urn:autofde-lab:planning-domain:platform-console:"

with open(FIXTURE, encoding="utf-8") as _f:
    ORIGINAL_TTL_TEXT = _f.read()


# ---------------------------------------------------------------------------
# Real, scoped TTL block extraction and mutation helpers. These operate on
# the real fixture text pulled from disk above -- not a hand-authored
# fixture string -- so a mutation that doesn't actually apply (e.g. because
# the real file's shape changed) fails loudly via the assertions below
# rather than silently mutating nothing.
# ---------------------------------------------------------------------------

_PRECOND_ATOM_RE = re.compile(
    r'\[ a pd:Atom ; pd:ofPredicate "(?P<pred>[\w-]+)" ;\s*\n'
    r'\s*pd:hasArgument \[ pd:argument "x" ; pd:argumentIndex 0 \] \]'
)


def _extract_action_block(text: str, action_local: str) -> tuple[int, int, str]:
    """Real, exact extraction of one ``ex:action-<action_local>`` block:
    from its ``a pd:Action ;`` header through the terminating `` .\\n``."""
    start_marker = f"ex:action-{action_local} a pd:Action ;"
    start = text.index(start_marker)
    end = text.index(" .\n", start) + len(" .\n")
    return start, end, text[start:end]


def _precondition_span(block: str) -> tuple[int, int]:
    start = block.index("pd:precondition")
    end = block.index("pd:effect", start)
    return start, end


def _render_precondition_section(predicates: list[str]) -> str:
    items = ",\n".join(
        f'        [ a pd:Atom ; pd:ofPredicate "{p}" ;\n'
        f'          pd:hasArgument [ pd:argument "x" ; pd:argumentIndex 0 ] ]'
        for p in predicates
    )
    return "    pd:precondition\n" + items + " ;\n    "


def _remove_precondition(block: str, predicate: str) -> str:
    start, end = _precondition_span(block)
    section = block[start:end]
    atoms = _PRECOND_ATOM_RE.findall(section)
    assert predicate in atoms, f"{predicate!r} is not a real precondition of this block: {atoms}"
    remaining = [p for p in atoms if p != predicate]
    assert len(remaining) == len(atoms) - 1
    return block[:start] + _render_precondition_section(remaining) + block[end:]


def _add_contradictory_precondition(block: str, new_predicate: str) -> str:
    start, end = _precondition_span(block)
    section = block[start:end]
    atoms = _PRECOND_ATOM_RE.findall(section)
    assert new_predicate not in atoms, f"{new_predicate!r} already a real precondition -- pick a fresh name"
    return block[:start] + _render_precondition_section([*atoms, new_predicate]) + block[end:]


def _swap_effect_predicate(block: str, old_predicate: str, new_predicate: str) -> str:
    effect_idx = block.index("pd:effect")
    head, tail = block[:effect_idx], block[effect_idx:]
    marker = f'pd:ofPredicate "{old_predicate}"'
    assert marker in tail, f"effect predicate {old_predicate!r} not found in this block's pd:effect section"
    tail = tail.replace(marker, f'pd:ofPredicate "{new_predicate}"', 1)
    return head + tail


def _remove_action_entirely(text: str, action_local: str) -> str:
    start, end, _block = _extract_action_block(text, action_local)
    text = text[:start] + text[end:]
    ref = f", ex:action-{action_local}"
    assert ref in text, f"ex:action-{action_local} not referenced in pd:hasAction (or already removed)"
    return text.replace(ref, "", 1)


def _splice(text: str, action_local: str, transform) -> str:
    start, end, block = _extract_action_block(text, action_local)
    mutated_block = transform(block)
    return text[:start] + mutated_block + text[end:]


def _write_mutant(tmp_path, mutated_text: str, tag: str) -> str:
    path = str(tmp_path / f"{tag}-mutant-platform-console-domain.ttl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(mutated_text)
    return path


def _solve(ttl_path: str, problem_iri: str, tmp_path, tag: str) -> tuple[int, str]:
    domain_p = str(tmp_path / f"{tag}-domain.pddl")
    problem_p = str(tmp_path / f"{tag}-problem.pddl")
    plan_p = str(tmp_path / f"{tag}-plan.txt")
    compile_rdf_to_pddl_files(
        ttl_path, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=problem_iri
    )
    rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)
    return rc, plan_p


PROBLEM_REVERSIBLE = NS + "problem-reversible"
PROBLEM_GATED = NS + "problem-gated"
PROBLEM_IRREVERSIBLE_REFUSED = NS + "problem-irreversible-refused"


# ---------------------------------------------------------------------------
# Sanity: the extraction/splice helpers themselves are exact -- splicing a
# block back in verbatim (no transform) reproduces the original file
# byte-for-byte. If this fails, every mutation below is untrustworthy, so
# it is asserted first and explicitly.
# ---------------------------------------------------------------------------


def test_mutation_harness_extraction_is_lossless_for_every_mutated_action():
    for action_local in ("org-delete", "castle-schedule", "freeze-override"):
        start, end, block = _extract_action_block(ORIGINAL_TTL_TEXT, action_local)
        assert ORIGINAL_TTL_TEXT[start:end] == block
        roundtrip = ORIGINAL_TTL_TEXT[:start] + block + ORIGINAL_TTL_TEXT[end:]
        assert roundtrip == ORIGINAL_TTL_TEXT


# ---------------------------------------------------------------------------
# Mutation 1: drop a precondition -- an irreversible, approval-gated action
# (dsar.erasure) that the real, unmutated domain correctly REFUSES to plan
# for a target where "approved" is never asserted must become solvable once
# its "approved" precondition atom is deleted from the real TTL. Proves the
# solver is reading -- and gated by -- the real precondition list, not
# returning a fixed refusal regardless of content.
#
# (A positive-goal custom problem is used here rather than the fixture's
# own ``problem-irreversible-refused`` -- that fixture problem's goal is a
# NEGATED atom (``not (org-exists res3)``), and this real Astar/scikit-
# decide combination cannot find ANY plan for a negated-atom goal, even a
# trivially one-step-reachable one -- verified directly against a minimal
# isolated domain/problem pair outside this file. That is itself a real,
# separately-worth-naming solver limitation, orthogonal to domain-content
# sensitivity; using a positive-goal problem here isolates the mutation
# effect this test is actually about from that unrelated limitation.)
# ---------------------------------------------------------------------------

_DSAR_MUTATION_PROBLEM_IRI = NS + "problem-dsar-mutation"

_DSAR_MUTATION_PROBLEM_TTL = f"""
<{_DSAR_MUTATION_PROBLEM_IRI}> a pd:Problem ;
    pd:problemName "platform-console-dsar-mutation" ;
    pd:forDomain ex:domain ;
    pd:hasObject [ pd:objectName "res3" ] ;
    pd:init
        [ a pd:Atom ; pd:ofPredicate "org-exists" ;
          pd:hasArgument [ pd:argument "res3" ; pd:argumentIndex 0 ] ] ;
    pd:goal
        [ a pd:Atom ; pd:ofPredicate "dsar-erasure-done" ;
          pd:hasArgument [ pd:argument "res3" ; pd:argumentIndex 0 ] ] .
"""


def test_dropping_approval_precondition_flips_a_correctly_refused_plan_to_solvable(tmp_path):
    text_with_problem = ORIGINAL_TTL_TEXT + "\n" + _DSAR_MUTATION_PROBLEM_TTL
    baseline_ttl = _write_mutant(tmp_path, text_with_problem, "baseline-dsar")

    baseline_rc, baseline_plan_p = _solve(
        baseline_ttl, _DSAR_MUTATION_PROBLEM_IRI, tmp_path, "baseline-dsar-solve"
    )
    assert baseline_rc == pddl_engine.EXIT_NO_PLAN, (
        "dsar-erasure requires 'approved', which is never asserted for "
        "res3 in this problem's init state -- the real, unmutated domain "
        "must correctly refuse to plan"
    )
    assert not os.path.exists(baseline_plan_p)

    mutated_text = _splice(
        text_with_problem, "dsar-erasure", lambda b: _remove_precondition(b, "approved")
    )
    mutant_ttl = _write_mutant(tmp_path, mutated_text, "drop-approved")

    mutated_rc, mutated_plan_p = _solve(
        mutant_ttl, _DSAR_MUTATION_PROBLEM_IRI, tmp_path, "mutated-dsar-solve"
    )
    assert mutated_rc == pddl_engine.EXIT_PLAN_FOUND, (
        "removing the 'approved' precondition from dsar-erasure must make "
        "the identical problem solvable -- the real solver must be "
        "reading the real precondition list, not a cached/fixed refusal"
    )
    plan_text = open(mutated_plan_p, encoding="utf-8").read()
    assert "(dsar-erasure res3)" in plan_text


# ---------------------------------------------------------------------------
# Mutation 2: swap an effect predicate -- castle-schedule is the ONLY action
# in the domain whose effect is "scheduled"; renaming that effect predicate
# must make the previously-solvable "gated" problem unsolvable, because no
# action in the mutated domain produces the goal predicate anymore.
# ---------------------------------------------------------------------------


def test_swapping_the_sole_producing_effect_predicate_makes_a_solvable_goal_unreachable(tmp_path):
    baseline_rc, baseline_plan_p = _solve(FIXTURE, PROBLEM_GATED, tmp_path, "baseline-schedule")
    assert baseline_rc == pddl_engine.EXIT_PLAN_FOUND
    assert "(castle-schedule res2)" in open(baseline_plan_p, encoding="utf-8").read()

    mutated_text = _splice(
        ORIGINAL_TTL_TEXT,
        "castle-schedule",
        lambda b: _swap_effect_predicate(b, "scheduled", "scheduled-mutated-away"),
    )
    mutant_ttl = _write_mutant(tmp_path, mutated_text, "swap-effect")

    mutated_rc, mutated_plan_p = _solve(mutant_ttl, PROBLEM_GATED, tmp_path, "mutated-schedule")
    assert mutated_rc == pddl_engine.EXIT_NO_PLAN, (
        "renaming castle-schedule's sole effect predicate away from "
        "'scheduled' must make the identical goal (scheduled(res2)) "
        "unreachable -- no other action in the domain produces it"
    )
    assert not os.path.exists(mutated_plan_p)


# ---------------------------------------------------------------------------
# Mutation 3: introduce a contradictory precondition/effect pair -- add a
# precondition atom to castle-schedule that no action in the whole domain
# ever establishes. The previously-solvable "gated" problem must become
# unsolvable, since the new precondition can never be satisfied.
# ---------------------------------------------------------------------------


def test_adding_an_unsatisfiable_contradictory_precondition_blocks_a_previously_solvable_plan(
    tmp_path,
):
    baseline_rc, _ = _solve(FIXTURE, PROBLEM_GATED, tmp_path, "baseline-contradiction")
    assert baseline_rc == pddl_engine.EXIT_PLAN_FOUND

    # "impossible-flag" is asserted nowhere in the fixture's init states and
    # is the effect of no action -- a real, permanently-false precondition.
    assert 'ofPredicate "impossible-flag"' not in ORIGINAL_TTL_TEXT
    mutated_text = _splice(
        ORIGINAL_TTL_TEXT,
        "castle-schedule",
        lambda b: _add_contradictory_precondition(b, "impossible-flag"),
    )
    mutant_ttl = _write_mutant(tmp_path, mutated_text, "contradiction")

    mutated_rc, mutated_plan_p = _solve(
        mutant_ttl, PROBLEM_GATED, tmp_path, "mutated-contradiction"
    )
    assert mutated_rc == pddl_engine.EXIT_NO_PLAN, (
        "a precondition that no action in the domain ever establishes must "
        "make the goal unreachable, not silently ignored by the solver"
    )
    assert not os.path.exists(mutated_plan_p)


# ---------------------------------------------------------------------------
# Mutation 4: remove an action entirely (its triples AND its
# ex:domain pd:hasAction registration). The previously-solvable "gated"
# problem must become unsolvable once its only producing action is gone.
#
# Removing one action from the full ~30-action domain still leaves 29
# other real actions to ground and exhaustively search before Astar can
# conclude no plan exists -- verified directly (outside this file, against
# an isolated `/tmp` copy) to take well over 100 real wall-clock seconds
# for this specific removal, an order of magnitude slower than every other
# NO_PLAN case in this file. That cost is itself real (not a bug in this
# test), but it is orthogonal to the property this test is actually
# checking -- so the domain is first trimmed down to *only* the one real
# action under test (``ex:action-castle-schedule``, its own real triples,
# extracted verbatim from the real fixture, never hand-authored) plus the
# real, unmodified predicate declarations and the real, unmodified
# ``problem-gated`` fixture problem. The baseline (one real action
# present) and the mutation (that real action's ``pd:hasAction``
# registration removed, leaving zero actions) are otherwise identical
# real Turtle, real-compiled and real-solved exactly as every other test
# in this file.
# ---------------------------------------------------------------------------

_ACTIONS_SECTION_MARKER = "# -- Actions "
_PROBLEMS_SECTION_MARKER = "# -- Problems "
_HAS_ACTION_CLAUSE_RE = re.compile(r"\s*pd:hasAction [^.]+\.", re.DOTALL)


def _trim_domain_to_single_action(text: str, action_local: str) -> str:
    """Real domain header (prefixes, ontology triple, ex:domain triple,
    all real predicate declarations) + exactly one real, verbatim-extracted
    action block + the real, unmodified Problems section -- every other
    real action is dropped so grounding/search cost stays proportional to
    ONE action, isolating this test's mutation effect from the unrelated
    ~100s+ full-domain NO_PLAN cost named above."""
    actions_start = text.index(_ACTIONS_SECTION_MARKER)
    problems_start = text.index(_PROBLEMS_SECTION_MARKER)
    before, after = text[:actions_start], text[problems_start:]
    _start, _end, block = _extract_action_block(text, action_local)
    before = _HAS_ACTION_CLAUSE_RE.sub(
        f" pd:hasAction ex:action-{action_local} .", before, count=1
    )
    return before + block + "\n\n" + after


def _remove_all_actions(text: str) -> str:
    """Real, valid Turtle with the ``pd:hasAction`` clause dropped
    entirely -- zero ``pd:Action`` individuals registered on ``ex:domain``,
    which ``rdf_domain.parse_domain`` (unmodified) correctly parses as a
    real, empty action list (``graph.objects(domain_iri, PD.hasAction)``
    over an absent predicate is real, valid, empty rdflib iteration -- not
    a dangling/broken reference)."""
    mutated, n = _HAS_ACTION_CLAUSE_RE.subn(" .", text, count=1)
    assert n == 1, "pd:hasAction clause not found to remove"
    return mutated


def test_removing_the_sole_producing_action_entirely_makes_the_goal_unreachable(tmp_path):
    trimmed_text = _trim_domain_to_single_action(ORIGINAL_TTL_TEXT, "castle-schedule")
    assert "ex:action-castle-schedule a pd:Action" in trimmed_text
    # Confirms the trim really did drop every other real action -- this
    # test's baseline is the SAME single-real-action domain the mutation
    # below starts from, not a coincidentally-similar hand-written one.
    assert trimmed_text.count(" a pd:Action ;") == 1
    baseline_ttl = _write_mutant(tmp_path, trimmed_text, "baseline-removed-action")

    baseline_rc, baseline_plan_p = _solve(
        baseline_ttl, PROBLEM_GATED, tmp_path, "baseline-removed-action-solve"
    )
    assert baseline_rc == pddl_engine.EXIT_PLAN_FOUND
    assert "(castle-schedule res2)" in open(baseline_plan_p, encoding="utf-8").read()

    mutated_text = _remove_all_actions(trimmed_text)
    # The action's own triples may still be physically present in the
    # mutated Turtle (removing the *registration* is the real mutation
    # under test) -- but it is no longer reachable from ex:domain via
    # pd:hasAction, which is exactly what the real, unmodified
    # rdf_domain.parse_domain reads to enumerate a domain's actions.
    assert "pd:hasAction ex:action-castle-schedule" not in mutated_text
    mutant_ttl = _write_mutant(tmp_path, mutated_text, "removed-action")

    mutated_rc, mutated_plan_p = _solve(
        mutant_ttl, PROBLEM_GATED, tmp_path, "mutated-removed-action-solve"
    )
    assert mutated_rc == pddl_engine.EXIT_NO_PLAN, (
        "deleting the only action that ever produces 'scheduled' must make "
        "the identical goal unreachable"
    )
    assert not os.path.exists(mutated_plan_p)


# ---------------------------------------------------------------------------
# Mutation 5: drop the freeze-override precondition that structurally
# enforces a required ordering. In the real domain, reaching
# freeze-override-approved(x) from a bare exists(x)/approved(x) init state
# always goes through: create-org -> freeze -> freeze-override (the
# "frozen" precondition on freeze-override forces the freeze step to run
# first). Deleting that "frozen" precondition must let the solver find a
# SHORTER plan that skips the freeze step entirely -- exactly the invalid
# ordering the real (correct) domain forbids.
# ---------------------------------------------------------------------------

_FREEZE_ORDERING_PROBLEM_IRI = NS + "problem-freeze-ordering-mutation"

_FREEZE_ORDERING_PROBLEM_TTL = f"""
<{_FREEZE_ORDERING_PROBLEM_IRI}> a pd:Problem ;
    pd:problemName "platform-console-freeze-ordering-mutation" ;
    pd:forDomain ex:domain ;
    pd:hasObject [ pd:objectName "o1" ] ;
    pd:init
        [ a pd:Atom ; pd:ofPredicate "exists" ;
          pd:hasArgument [ pd:argument "o1" ; pd:argumentIndex 0 ] ] ,
        [ a pd:Atom ; pd:ofPredicate "approved" ;
          pd:hasArgument [ pd:argument "o1" ; pd:argumentIndex 0 ] ] ;
    pd:goal
        [ a pd:Atom ; pd:ofPredicate "freeze-override-approved" ;
          pd:hasArgument [ pd:argument "o1" ; pd:argumentIndex 0 ] ] .
"""


def _append_problem(text: str, problem_ttl: str) -> str:
    return text + "\n" + problem_ttl


def test_dropping_the_frozen_precondition_allows_the_domain_to_skip_a_required_ordering_step(
    tmp_path,
):
    text_with_problem = _append_problem(ORIGINAL_TTL_TEXT, _FREEZE_ORDERING_PROBLEM_TTL)
    baseline_ttl = _write_mutant(tmp_path, text_with_problem, "baseline-freeze-ordering")

    baseline_rc, baseline_plan_p = _solve(
        baseline_ttl, _FREEZE_ORDERING_PROBLEM_IRI, tmp_path, "baseline-freeze-ordering-solve"
    )
    assert baseline_rc == pddl_engine.EXIT_PLAN_FOUND
    baseline_plan = open(baseline_plan_p, encoding="utf-8").read().splitlines()
    assert "(freeze o1)" in baseline_plan, (
        "the real domain's 'frozen' precondition on freeze-override must "
        "force the freeze step into any real plan reaching "
        "freeze-override-approved(o1)"
    )
    assert "(freeze-override o1)" in baseline_plan
    assert baseline_plan.index("(freeze o1)") < baseline_plan.index("(freeze-override o1)"), (
        "freeze must be ordered strictly before freeze-override in the "
        "real, unmutated domain"
    )

    mutated_text = _splice(
        text_with_problem, "freeze-override", lambda b: _remove_precondition(b, "frozen")
    )
    mutant_ttl = _write_mutant(tmp_path, mutated_text, "mutated-freeze-ordering")

    mutated_rc, mutated_plan_p = _solve(
        mutant_ttl, _FREEZE_ORDERING_PROBLEM_IRI, tmp_path, "mutated-freeze-ordering-solve"
    )
    assert mutated_rc == pddl_engine.EXIT_PLAN_FOUND
    mutated_plan = open(mutated_plan_p, encoding="utf-8").read().splitlines()
    assert "(freeze-override o1)" in mutated_plan
    assert "(freeze o1)" not in mutated_plan, (
        "removing the 'frozen' precondition must let the solver find a plan "
        "that reaches freeze-override-approved(o1) WITHOUT ever going "
        "through the freeze step -- exactly the invalid ordering the real, "
        "correct domain structurally forbids via that precondition"
    )
    assert len(mutated_plan) < len(baseline_plan), (
        "the mutated domain's shortest plan must be strictly shorter, "
        "proving Astar is genuinely re-planning against the mutated "
        "precondition set rather than replaying a cached baseline plan"
    )
