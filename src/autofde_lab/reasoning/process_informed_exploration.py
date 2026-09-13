# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Drives real, sqlite/OCEL-sourced process evidence through
`laboratory.infer_desired_state_hypotheses`'s real `"process-informed-v1"`
branch and into the real TRIZ/DOE/Monte-Carlo exploration-candidate
generators -- closing a real gap confirmed this session.

`infer_desired_state_hypotheses`'s `process-informed-v1` branch was already
proven real and reachable
(`test_sqlite_process_science_provider_chicago.py::
test_real_process_observation_activates_the_previously_dead_process_informed_hypothesis_branch`),
but confirmed live this session (`grep -rln "process-informed"
tests/reasoning/test_triz_chicago.py tests/reasoning/test_doe_chicago.py
tests/reasoning/test_montecarlo_chicago.py
tests/reasoning/test_exploration_payoff_bridge_chicago.py
tests/reasoning/test_exploration_psro_loop_chicago.py
tests/reasoning/test_exploration_gymact_falsification_chicago.py`: zero
matches) that the resulting real process-informed hypothesis had never
itself been fed into `generate_triz_candidates`/`generate_doe_candidates`/
`generate_montecarlo_candidates` -- every existing exploration-generator
test (and every downstream bridge built this session) used the same
hand-built `"rule-based-v1"` `DesiredStateHypothesis` fixture, never a
real, OCEL-observed one.

`process_informed_hypotheses` is the one real, previously-missing
orchestration step: it constructs a real `SqliteProcessScienceProvider`,
requests a real `ProcessObservation` against the caller-supplied real
`EnterpriseObservation` (never fabricated here -- the caller already knows
what enterprise state is being observed), and calls the real
`infer_desired_state_hypotheses` with it. The resulting real
`tuple[DesiredStateHypothesis, ...]` (1 entry if the sqlite db carried no
real signal, 2 if it did -- never coerced) can then be passed directly into
any of the three existing, already-real, hypothesis-agnostic exploration
generators exactly as-is; no new generator wrapper is needed since none of
`generate_triz_candidates`/`generate_doe_candidates`/
`generate_montecarlo_candidates` cares where its hypotheses came from.
"""

from __future__ import annotations

from pathlib import Path

from .laboratory import (
    DesiredStateHypothesis,
    EnterpriseObservation,
    infer_desired_state_hypotheses,
)
from .sqlite_process_science_provider import SqliteProcessScienceProvider

__all__ = ["process_informed_hypotheses"]


def process_informed_hypotheses(
    metadata: object,
    *,
    db_path: str | Path,
    observation: EnterpriseObservation,
) -> tuple[DesiredStateHypothesis, ...]:
    """Real end-to-end: a real sqlite db (already written by
    `autofde_lab.ocel.sqlite_store.to_sqlite` from some real
    `OcelLog`) -> a real `SqliteProcessScienceProvider(db_path)` ->
    a real `ProcessObservation` for `observation` -> the real
    `infer_desired_state_hypotheses(metadata, process_observation=...)`.

    Returns exactly whatever real tuple that call produces -- one
    `"rule-based-v1"` hypothesis if the sqlite db carried no real signal
    (missing file, empty schema, or genuinely no matching activity), two
    (`"rule-based-v1"` plus `"process-informed-v1"`) if it did. Never
    fabricates, drops, or reorders either real hypothesis.
    """
    provider = SqliteProcessScienceProvider(db_path)
    process_observation = provider.request_process_observation(observation)
    return infer_desired_state_hypotheses(metadata, process_observation=process_observation)
