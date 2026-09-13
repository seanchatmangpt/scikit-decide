# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `psro_informed_exploration_round` -- the real
join between a converged `PsroTrajectory` (from the cross-play cluster)
and the next real round of exploration-candidate falsification (via
`process_informed_psro_pipeline`).

Real collaborators throughout: a real `BreachClockDomain`-backed cross-play
trajectory (the same real scenario `psro_trajectory.py`'s own tests
established), a real, in-memory-built `OcelLog` written to a real sqlite
file, a real `Maze` domain, a real `PlannerLeague`, and the real
`GymActWorldExperimentProvider`. No `unittest.mock` / `Mock` / `MagicMock`
/ `patch` / `monkeypatch` anywhere in this file.

Every value asserted below was confirmed live before being written, not
assumed: the real cross-play trajectory converges with
`dominant_response(trajectory.final_state) == "Astar"`; feeding `"Astar"`
as the derived `falsifier_planner_id` into a real TRIZ round against the
real `Maze()`/OCEL fixture produces the identical real 8-candidate,
`FALSIFIED`/`(0.0, 1.0)`-scored, PSRO-advancing outcome
`process_informed_psro_pipeline.py`'s own tests already established for a
hardcoded `"MCTS"` opponent -- the derived opponent is treated exactly
like any other real, registered planner.
"""

from __future__ import annotations

from autofde_lab.hub.domain.breach_clock import BreachClockDomain
from autofde_lab.hub.domain.maze import Maze
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.ocel.sqlite_store import to_sqlite
from autofde_lab.planner_league import PayoffHypergraph, PlannerLeague
from autofde_lab.planner_league.cross_play_world_schedule import schedule_cross_play_for_world
from autofde_lab.planner_league.psro import PolicySpaceResponseOracle, PsroState
from autofde_lab.planner_league.psro_trajectory import dominant_response, run_psro_trajectory
from autofde_lab.reasoning.cross_play_schedule_payoff import admit_cross_play_schedule_payoffs
from autofde_lab.reasoning.exploration_psro_loop import ExplorationPsroRoundOutcome
from autofde_lab.reasoning.laboratory import EnterpriseObservation, TRIZContradiction, TRIZParameter
from autofde_lab.reasoning.laboratory import generate_triz_candidates
from autofde_lab.reasoning.psro_informed_exploration_round import run_psro_informed_next_round


def _real_converged_trajectory():
    league = PlannerLeague()
    schedule = schedule_cross_play_for_world(
        league, "cyber_incident", left_role_id="plan_constructor", right_role_id="plan_falsifier"
    )
    domain = BreachClockDomain()
    hypergraph = PayoffHypergraph()
    admit_cross_play_schedule_payoffs(schedule, domain, hypergraph=hypergraph, limit=6)
    oracle = PolicySpaceResponseOracle(
        hypergraph, role_id="plan_constructor", opponent_role_id="plan_falsifier", world_id="cyber_incident"
    )
    initial_state = PsroState.seed(("Astar", "BFWS"))
    return run_psro_trajectory(oracle, initial_state, candidates=("AOstar", "Astar"), max_rounds=4)


def _build_real_log() -> OcelLog:
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
        log, event_id="m0", activity="decision_match", object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["Astar", "MCTS"]}, timestamp_ns=0,
    )
    log = append_tool_call_event(
        log, event_id="m1", activity="decision_match", object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["MCTS", "Astar"]}, timestamp_ns=1_000,
    )
    return log


def test_trajectory_converges_to_the_real_expected_dominant_response() -> None:
    trajectory = _real_converged_trajectory()
    assert dominant_response(trajectory.final_state) == "Astar"


def test_dominant_response_flows_unmodified_into_a_real_next_round(tmp_path) -> None:
    trajectory = _real_converged_trajectory()

    log = _build_real_log()
    db_path = tmp_path / "psro_informed.sqlite"
    to_sqlite(log, db_path)

    from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
        ScenarioMetadata_checkout_latency_scenario_v_1,
    )

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    observation = EnterpriseObservation(
        ontology_graph_ref="ontology:psro-informed-test", source_provenance_ref="test", enterprise_world_ref="test-world"
    )
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST, worsening_parameter=TRIZParameter.AUTHORITY_NEEDS
    )

    result = run_psro_informed_next_round(
        trajectory,
        metadata,
        db_path=str(db_path),
        observation=observation,
        candidate_generator=lambda hyps: generate_triz_candidates(hyps, contradiction),
        league=PlannerLeague(),
        domain=Maze(),
        constructor_planner_ids=["Astar"],
    )

    assert isinstance(result, ExplorationPsroRoundOutcome)
    assert len(result.admissions) == 8
    assert result.admitted_count == 8
    # The derived falsifier is the real trajectory's own dominant
    # response, never a hardcoded string.
    assert all(
        o.observation.match.right_policy.planner_id == "Astar" for o in result.admissions if o.observation
    )
    for obs in result.hypergraph.observations:
        assert obs.left_score == 0.0
        assert obs.right_score == 1.0
    assert result.psro_step.advanced
    assert result.psro_step.standing == "ALIVE"
    assert result.psro_step.receipt.selected_best_response == "Astar"
