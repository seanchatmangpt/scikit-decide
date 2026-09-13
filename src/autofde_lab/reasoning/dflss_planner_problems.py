# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real manifest binding each real registered planner name (the real
`PRIMARY_PLANNERS` + `NOVELTY_ORACLES` tuples in
`autofde_lab.planner_league.catalog` -- 56 primary planners plus the
`DSPyPolicy` novelty oracle, 57 total) to its real, on-disk per-planner PDDL
problem file under `docs/planning/dflss-dmedi-curriculum/problems/`.

Every file in that directory targets the same real
`docs/planning/dflss-dmedi-curriculum/domain.pddl` (the real DFLSS DMEDI
curriculum domain), the same empty `:init`, and the same
`dmedi-capstone-complete` goal -- the only thing that varies across the 57
files is which real planner is named to attempt the identical problem
instance, matching this repo's own real `EXPERIMENT_DIMENSIONS` vocabulary
(catalog.py) which already names "planner" as a real experiment dimension.

This module only resolves a real planner id to its real, already-generated
problem-file path. It does not construct a `PDDLDomain`, does not invoke a
solver, and per `CLAUDE.md`'s "It computes candidate plans. It does not
actuate.", carries no actuation semantics of its own.
"""

from __future__ import annotations

from pathlib import Path

from autofde_lab.planner_league.catalog import NOVELTY_ORACLES, PRIMARY_PLANNERS

# repo_root/src/autofde_lab/reasoning/dflss_planner_problems.py
# parents[0] = reasoning, [1] = autofde_lab, [2] = src, [3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]

PROBLEMS_DIR = (
    _REPO_ROOT / "docs" / "planning" / "dflss-dmedi-curriculum" / "problems"
)

# The real, canonical 57 planner names this manifest covers -- exactly
# PRIMARY_PLANNERS + NOVELTY_ORACLES, in that order, no more and no fewer.
ALL_PLANNERS: tuple[str, ...] = PRIMARY_PLANNERS + NOVELTY_ORACLES

_PLANNER_TO_PROBLEM_FILE: dict[str, Path] = {
    planner: PROBLEMS_DIR / f"{planner}.pddl" for planner in ALL_PLANNERS
}


def problem_file_for_planner(planner_id: str) -> Path:
    """Return the real, existing PDDL problem-file `Path` for `planner_id`.

    `planner_id` must be one of the real 57 names in `ALL_PLANNERS`
    (`PRIMARY_PLANNERS + NOVELTY_ORACLES` from
    `autofde_lab.planner_league.catalog`). Any other value raises a real,
    honest `KeyError` naming the offending id -- never a silent `None`.
    """
    try:
        return _PLANNER_TO_PROBLEM_FILE[planner_id]
    except KeyError:
        raise KeyError(
            f"{planner_id!r} is not one of the 57 real registered planners "
            "(PRIMARY_PLANNERS + NOVELTY_ORACLES in "
            "autofde_lab.planner_league.catalog); no DFLSS DMEDI curriculum "
            "problem file exists for it."
        ) from None
