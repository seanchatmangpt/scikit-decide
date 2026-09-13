# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: real, on-disk PDDL problem files under
docs/planning/dflss-dmedi-curriculum/problems/, the real manifest module
(`autofde_lab.reasoning.dflss_planner_problems`), and the real, already-built
C++-backed `PDDLReader` this repo uses for PDDL parsing (per
`tests/domains/python/test_pddl_parser.py`'s own pattern -- the "nearest
working example" for classical PDDL parsing, per `.claude/rules/architecture.md`).

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in
this file: every assertion below is against real files on disk and real
parsed PDDL structures, never an interaction with a stand-in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.planner_league.catalog import NOVELTY_ORACLES, PRIMARY_PLANNERS
from autofde_lab.reasoning.dflss_planner_problems import (
    ALL_PLANNERS,
    PROBLEMS_DIR,
    problem_file_for_planner,
)

DOMAIN_PATH = PROBLEMS_DIR.parent / "domain.pddl"

EXPECTED_PLANNERS = PRIMARY_PLANNERS + NOVELTY_ORACLES


def test_exactly_57_real_planners_are_named() -> None:
    """Sanity on the real catalog this whole test targets: 56 primary
    planners + 1 novelty oracle, 57 total, matching the manifest's own
    ALL_PLANNERS."""
    assert len(PRIMARY_PLANNERS) == 56
    assert len(NOVELTY_ORACLES) == 1
    assert len(EXPECTED_PLANNERS) == 57
    assert ALL_PLANNERS == EXPECTED_PLANNERS


def test_exactly_57_real_pddl_files_exist_on_disk() -> None:
    """(a) Really confirms exactly 57 real .pddl files exist on disk under
    problems/ -- not fewer (missing planners) and not more (stray files)."""
    assert PROBLEMS_DIR.is_dir(), f"missing problems directory: {PROBLEMS_DIR}"
    pddl_files = sorted(PROBLEMS_DIR.glob("*.pddl"))
    assert len(pddl_files) == 57, (
        f"expected exactly 57 .pddl files, found {len(pddl_files)}: "
        f"{[f.name for f in pddl_files]}"
    )


def test_every_primary_and_novelty_planner_has_a_real_problem_file() -> None:
    """(b) Really confirms every one of PRIMARY_PLANNERS + NOVELTY_ORACLES has
    a real file via problem_file_for_planner -- resolved through the real
    manifest function, not a hand-built path."""
    for planner in EXPECTED_PLANNERS:
        path = problem_file_for_planner(planner)
        assert isinstance(path, Path)
        assert path.is_file(), f"no real file for planner {planner!r}: {path}"
        assert path.name == f"{planner}.pddl"
        assert path.parent == PROBLEMS_DIR


def test_no_orphaned_files_beyond_the_real_57_planner_names() -> None:
    """(c) Really confirms no extra/orphaned files exist beyond the real 57
    planner names -- every .pddl file's stem must be a real planner id, and
    every real planner id must have exactly one file."""
    on_disk_stems = {f.stem for f in PROBLEMS_DIR.glob("*.pddl")}
    expected_stems = set(EXPECTED_PLANNERS)

    orphaned = on_disk_stems - expected_stems
    missing = expected_stems - on_disk_stems

    assert not orphaned, f"orphaned problem file(s) with no matching planner: {orphaned}"
    assert not missing, f"real planner(s) missing a problem file: {missing}"

    # Also catch any non-.pddl stray file living in the same directory.
    all_entries = {f.name for f in PROBLEMS_DIR.iterdir() if f.is_file()}
    non_pddl = {name for name in all_entries if not name.endswith(".pddl")}
    assert not non_pddl, f"unexpected non-.pddl file(s) in problems/: {non_pddl}"


def test_problem_file_for_unknown_planner_raises_real_keyerror() -> None:
    """The manifest's own contract: a planner_id outside the real 57 raises a
    real, honest KeyError -- never a silent None."""
    with pytest.raises(KeyError, match="NotARealPlanner"):
        problem_file_for_planner("NotARealPlanner")

    with pytest.raises(KeyError):
        problem_file_for_planner("")

    with pytest.raises(KeyError):
        # Case matters -- the real catalog is exact-case ("Astar", not
        # "astar"); a near-miss must not silently resolve.
        problem_file_for_planner("astar")


@pytest.mark.parametrize("planner", ["Astar", "MCTS", "DSPyPolicy"])
def test_sample_problem_files_are_real_valid_pddl(planner: str) -> None:
    """(d) Really parses at least 3 real sample files (Astar, MCTS,
    DSPyPolicy -- one PRIMARY_PLANNERS entry from each broad planner family
    plus the one NOVELTY_ORACLES entry) with the real PDDL parser this repo
    already uses (`PDDLReader`, C++-backed), confirming they're real, valid
    PDDL -- not just present on disk.

    A file that merely existed but contained garbage would fail this parse;
    a file with the wrong domain reference or the wrong goal predicate would
    fail the structural assertions below even if it parsed.
    """
    from autofde_lab.hub.domain.pddl.pddl import PDDLReader

    problem_path = problem_file_for_planner(planner)
    reader = PDDLReader(str(DOMAIN_PATH), str(problem_path))

    assert len(reader.domains) == 1
    assert len(reader.problems) == 1

    domain = reader.domains[0]
    problem = reader.problems[0]

    # Real domain identity: every per-planner problem targets the same real
    # dflss-dmedi-curriculum domain.
    assert domain.get_name().lower() == "dflss-dmedi-curriculum"
    reqs = domain.get_requirements()
    assert reqs is not None
    assert reqs.has_strips()

    # Real, substantial action set parsed from the real domain (52 real
    # curriculum-module + tollgate actions) -- confirms the domain side of
    # the pair parsed completely, not just the problem side.
    assert len(domain.get_actions()) == 52

    # Real problem identity: file identity and problem identity are in
    # lockstep, per this session's task specification.
    assert problem.get_name().lower() == f"dflss-dmedi-curriculum-for-{planner.lower()}"
    assert problem.get_domain().get_name().lower() == "dflss-dmedi-curriculum"

    # Real, empty :init -- no module is asserted complete without evidence.
    init = problem.get_initial_effect()
    assert init is not None
    assert len(init.get_effects()) == 0

    # Real goal: the program's real closing deliverable.
    goal = problem.get_goal()
    assert goal is not None
    assert goal.get_name().lower() == "dmedi-capstone-complete"
    assert len(goal.get_terms()) == 0
