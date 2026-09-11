# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `process_informed_exploration` -- the real,
previously-missing link from real, sqlite/OCEL-sourced process evidence
through `laboratory.infer_desired_state_hypotheses`'s real
`"process-informed-v1"` branch into the real TRIZ/DOE/Monte-Carlo
exploration-candidate generators.

Real collaborators throughout: a real, in-memory-built `OcelLog` (same
construction pattern
`test_sqlite_process_science_provider_chicago.py::_build_real_log` uses),
written to a real sqlite file via `sqlite_store.to_sqlite`, queried
through a real `SqliteProcessScienceProvider`, feeding the real
`infer_desired_state_hypotheses` and the real `generate_triz_candidates`/
`generate_doe_candidates`/`generate_montecarlo_candidates`. No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.ocel.sqlite_store import to_sqlite
from autofde_lab.reasoning.laboratory import (
    EnterpriseObservation,
    MonteCarloCostModel,
    MonteCarloDistribution,
    TRIZContradiction,
    TRIZParameter,
    generate_doe_candidates,
    generate_montecarlo_candidates,
    generate_triz_candidates,
)
from autofde_lab.reasoning.process_informed_exploration import process_informed_hypotheses
from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
    ScenarioMetadata_checkout_latency_scenario_v_1,
)


def _build_real_log() -> OcelLog:
    """Same real construction pattern as
    `test_sqlite_process_science_provider_chicago.py::_build_real_log` --
    reused, not re-derived, since it already produces real signal for all
    three real process-science functions
    `SqliteProcessScienceProvider` wraps."""
    log = OcelLog.new(
        objects=[
            OcelObject(
                "session-1", "MCPSession",
                (OcelAttribute("server", OcelAttributeValue.string("scikit-decide-fabric")),),
            ),
            OcelObject("domain-Maze", "Domain", (OcelAttribute("name", OcelAttributeValue.string("Maze")),)),
            OcelObject(
                "domain-MasterMind", "Domain",
                (OcelAttribute("name", OcelAttributeValue.string("MasterMind")),),
            ),
        ]
    )
    log = append_tool_call_event(
        log, event_id="match-maze-0", activity="decision_match",
        object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["Astar", "MCTS"]},
        timestamp_ns=0,
    )
    log = append_tool_call_event(
        log, event_id="match-maze-1", activity="decision_match",
        object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["MCTS", "Astar"]},
        timestamp_ns=1_000,
    )
    return log


def _real_observation() -> EnterpriseObservation:
    return EnterpriseObservation(
        ontology_graph_ref="ontology:process-informed-exploration-test",
        source_provenance_ref="test",
        enterprise_world_ref="test-world",
    )


def test_process_informed_hypotheses_returns_two_real_hypotheses_from_real_signal(tmp_path) -> None:
    log = _build_real_log()
    db_path = tmp_path / "process_informed.sqlite"
    to_sqlite(log, db_path)

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    hypotheses = process_informed_hypotheses(metadata, db_path=db_path, observation=_real_observation())

    assert len(hypotheses) == 2
    assert hypotheses[0].hypothesis_id == "rule-based-v1"
    assert hypotheses[1].hypothesis_id == "process-informed-v1"
    assert any(ref.startswith("activity_duration:") for ref in hypotheses[1].evidence_used_refs)


def test_process_informed_hypotheses_falls_back_to_one_when_no_real_signal(tmp_path) -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    hypotheses = process_informed_hypotheses(
        metadata, db_path=tmp_path / "does-not-exist.sqlite", observation=_real_observation()
    )
    assert len(hypotheses) == 1
    assert hypotheses[0].hypothesis_id == "rule-based-v1"


def test_real_process_informed_hypothesis_produces_its_own_real_triz_candidates(tmp_path) -> None:
    """The real gap this file closes: before this test, no exploration
    generator had ever been called with a real, sqlite/OCEL-sourced
    `"process-informed-v1"` hypothesis (confirmed via grep across every
    existing TRIZ/DOE/Monte-Carlo test file). With 2 real hypotheses
    (rule-based + process-informed) instead of 1, `generate_triz_candidates`
    -- for-each-hypothesis by its own real, documented contract -- must
    produce exactly double the candidates of a single-hypothesis call."""
    log = _build_real_log()
    db_path = tmp_path / "process_informed_triz.sqlite"
    to_sqlite(log, db_path)

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    two_hypotheses = process_informed_hypotheses(metadata, db_path=db_path, observation=_real_observation())
    one_hypothesis = two_hypotheses[:1]
    assert len(two_hypotheses) == 2

    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST, worsening_parameter=TRIZParameter.AUTHORITY_NEEDS
    )
    candidates_from_one = generate_triz_candidates(one_hypothesis, contradiction)
    candidates_from_two = generate_triz_candidates(two_hypotheses, contradiction)

    assert len(candidates_from_one) > 0
    assert len(candidates_from_two) == 2 * len(candidates_from_one)
    assert all(c.provenance == "triz-v1" for c in candidates_from_two)


def test_real_process_informed_hypothesis_produces_its_own_real_doe_candidates(tmp_path) -> None:
    log = _build_real_log()
    db_path = tmp_path / "process_informed_doe.sqlite"
    to_sqlite(log, db_path)

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    two_hypotheses = process_informed_hypotheses(metadata, db_path=db_path, observation=_real_observation())
    assert len(two_hypotheses) == 2

    candidates = generate_doe_candidates(
        two_hypotheses,
        cost_levels=(10.0, 100.0),
        authority_levels=(("read_only",), ("read_write", "delete")),
    )
    # 2 hypotheses * 4 real design points each.
    assert len(candidates) == 8
    assert all(c.provenance == "doe-v1" for c in candidates)


def test_real_process_informed_hypothesis_produces_its_own_real_montecarlo_candidates(tmp_path) -> None:
    log = _build_real_log()
    db_path = tmp_path / "process_informed_mc.sqlite"
    to_sqlite(log, db_path)

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    two_hypotheses = process_informed_hypotheses(metadata, db_path=db_path, observation=_real_observation())
    assert len(two_hypotheses) == 2

    cost_model = MonteCarloCostModel(distribution=MonteCarloDistribution.UNIFORM, low=10.0, high=50.0)
    candidates = generate_montecarlo_candidates(two_hypotheses, cost_model, n=3)

    # 2 hypotheses * 3 real samples each.
    assert len(candidates) == 6
    assert all(c.provenance == "montecarlo-v1" for c in candidates)
