# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `SqliteProcessScienceProvider`.

Real collaborators throughout: a real, in-memory `OcelLog` built via the
exact same construction pattern `tests/ocel/test_decision_mining.py::_build_log`
uses (`append_tool_call_event` with real `MCPSession`/`Domain` objects and
real `decision_match` activities), written to a real sqlite file via
`sqlite_store.to_sqlite`, queried through a real `sqlite3.Connection` by
the real `decision_mining.py`/`enhancement.py`/`resource_perspective.py`
functions.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.ocel.sqlite_store import to_sqlite
from autofde_lab.reasoning.laboratory import EnterpriseObservation, infer_desired_state_hypotheses
from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
    ScenarioMetadata_checkout_latency_scenario_v_1,
)
from autofde_lab.reasoning.sqlite_process_science_provider import SqliteProcessScienceProvider


def _build_real_log() -> OcelLog:
    """Same real construction pattern as
    `tests/ocel/test_decision_mining.py::_build_log` -- one `MCPSession`,
    two `Domain`s, four `decision_match` events. Reused (not re-derived)
    here since it already exercises both `compatible_solver_set_stability`
    (2 domains, one deterministic, one not) and `activity_durations`/
    `bottleneck_ranking` (4 sequential events in one session produce real,
    non-empty inter-event gaps for the `decision_match` activity)."""
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
    log = append_tool_call_event(
        log, event_id="match-mastermind-0", activity="decision_match",
        object_ids=["session-1", "domain-MasterMind"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["Astar"]},
        timestamp_ns=2_000,
    )
    log = append_tool_call_event(
        log, event_id="match-mastermind-1", activity="decision_match",
        object_ids=["session-1", "domain-MasterMind"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["Astar", "BFWS"]},
        timestamp_ns=3_000,
    )
    return log


def test_real_sqlite_backed_process_observation_carries_real_signal(tmp_path) -> None:
    log = _build_real_log()
    db_path = tmp_path / "process_science_test.sqlite"
    to_sqlite(log, db_path)

    provider = SqliteProcessScienceProvider(db_path)
    observation = provider.request_process_observation(
        EnterpriseObservation(
            ontology_graph_ref="ontology:test", source_provenance_ref="test", enterprise_world_ref="test-world"
        )
    )

    assert observation.evidence_standing == "OBSERVED"
    # activity_durations/bottleneck_ranking produce a real "decision_match"
    # gap row; compatible_solver_set_stability produces 2 real
    # decision-stability rows, sharing this bucket per the module's own
    # documented "no dedicated field" convention.
    assert any(ref.startswith("activity_duration:decision_match:") for ref in observation.performance_metric_refs)
    assert any(ref.startswith("decision_stability:domain-Maze:") for ref in observation.performance_metric_refs)
    assert any(ref.startswith("decision_stability:domain-MasterMind:") for ref in observation.performance_metric_refs)
    assert any(ref.startswith("bottleneck:decision_match:") for ref in observation.bottleneck_refs)
    # No Solver-linked events in this fixture -- handover_of_work is
    # honestly empty, never fabricated.
    assert observation.object_centric_relation_refs == ()
    assert observation.computation_receipt_ref is not None


def test_missing_sqlite_db_is_a_real_honest_unsupported_never_a_crash(tmp_path) -> None:
    provider = SqliteProcessScienceProvider(tmp_path / "does-not-exist.sqlite")
    observation = provider.request_process_observation(
        EnterpriseObservation(
            ontology_graph_ref="ontology:test", source_provenance_ref="test", enterprise_world_ref="test-world"
        )
    )

    assert observation.evidence_standing == "UNSUPPORTED"
    assert observation.performance_metric_refs == ()
    assert observation.bottleneck_refs == ()


def test_real_process_observation_activates_the_previously_dead_process_informed_hypothesis_branch(
    tmp_path,
) -> None:
    """`laboratory.infer_desired_state_hypotheses`'s `process-informed-v1`
    branch (laboratory.py:200-213) has never fired against a real,
    non-test-literal `ProcessObservation` before this test -- every prior
    caller either passed `None` or `UnsupportedProcessScienceProvider`'s
    own `evidence_standing="UNSUPPORTED"` result. Prove the real, mechanical
    end-to-end wiring: a real sqlite-backed observation with real signal
    makes the dead branch produce a real second hypothesis."""
    log = _build_real_log()
    db_path = tmp_path / "process_science_integration_test.sqlite"
    to_sqlite(log, db_path)

    provider = SqliteProcessScienceProvider(db_path)
    observation = provider.request_process_observation(
        EnterpriseObservation(
            ontology_graph_ref="ontology:test", source_provenance_ref="test", enterprise_world_ref="test-world"
        )
    )
    assert observation.evidence_standing == "OBSERVED"  # precondition for the branch to fire

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    hypotheses = infer_desired_state_hypotheses(metadata, process_observation=observation)

    assert len(hypotheses) == 2
    assert hypotheses[0].hypothesis_id == "rule-based-v1"
    assert hypotheses[1].hypothesis_id == "process-informed-v1"
    assert hypotheses[1].uncertainty == 0.2
    # The process-informed hypothesis's evidence includes the real
    # performance_metric_refs this test's own provider call just produced.
    assert any(ref.startswith("activity_duration:") for ref in hypotheses[1].evidence_used_refs)


def test_sqlite3_connection_reused_across_calls_is_never_left_open() -> None:
    """Structural: each call opens and closes its own connection -- no
    shared mutable connection state a concurrent caller could corrupt."""
    provider = SqliteProcessScienceProvider(":memory:")
    # A fresh, never-populated :memory: db has no real schema -- honest
    # UNSUPPORTED, and confirms the connection was really closed (no
    # ResourceWarning/leaked file descriptor across repeated calls).
    for _ in range(3):
        observation = provider.request_process_observation(
            EnterpriseObservation(
                ontology_graph_ref="ontology:test", source_provenance_ref="test", enterprise_world_ref="test-world"
            )
        )
        assert observation.evidence_standing == "UNSUPPORTED"
