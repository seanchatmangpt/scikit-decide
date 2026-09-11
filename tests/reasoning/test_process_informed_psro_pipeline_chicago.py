# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `process_informed_psro_pipeline` -- the real,
generic four-stage pipeline from sqlite/OCEL-sourced process evidence,
through a real exploration-candidate generator, a real gymact-mediated
experiment, and into a real PSRO step.

Real collaborators throughout: a real, in-memory-built `OcelLog` written to
a real sqlite file, a real `Maze` domain, a real `PlannerLeague` calling
the real, installed `Astar`/`MCTS` solver entry points, a real
`GymActWorldExperimentProvider` (materialize/act/verify/teardown via a
real `gymact.runtime.GymAct` instance), and a real
`PolicySpaceResponseOracle`. No `unittest.mock` / `Mock` / `MagicMock` /
`patch` / `monkeypatch` anywhere in this file.

Every value asserted below was confirmed live before being written, not
assumed. Two real, distinct outcome shapes are exercised, proving this
pipeline is genuinely generic over which exploration generator supplies
`candidate_generator`, not merely re-running the same TRIZ path twice:

- TRIZ candidates carry a real, non-empty `migration_actions` entry (their
  own TRIZ-principle prescription text) and empty `expected_effects` --
  with the default fail-closed `GymActWorldExperimentProvider`, the real
  `act()` call for that action is refused at real `verify()` time -> real
  `FALSIFIED` -> real `(0.0, 1.0)` scores.
- Monte Carlo candidates carry empty `migration_actions` *and* empty
  `expected_effects` -- zero real `act()` calls are made, `verify()` is
  called with an empty expectation set (vacuously `postconditions_violated
  == ()` but also `postconditions_observed == ()`, which is falsy) -> real
  `laboratory.falsify_candidate`'s own `all_confirmed = all(r.
  postconditions_observed for r in usable_receipts)` evaluates `False` on
  that empty tuple -> real `PARTIAL` -> real `(0.5, 0.5)` scores.

In both cases PSRO still advances: the sole real candidate planner has
complete real coverage against the single real opponent, and
`empirical_best_response` only requires that coverage, never a winning
score, when there is no competing candidate.
"""

from __future__ import annotations

from autofde_lab.hub.domain.maze import Maze
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.ocel.sqlite_store import to_sqlite
from autofde_lab.planner_league import PlannerLeague
from autofde_lab.reasoning.exploration_psro_loop import ExplorationPsroRoundOutcome
from autofde_lab.reasoning.laboratory import (
    EnterpriseObservation,
    MonteCarloCostModel,
    MonteCarloDistribution,
    TRIZContradiction,
    TRIZParameter,
    generate_montecarlo_candidates,
    generate_triz_candidates,
)
from autofde_lab.reasoning.process_informed_psro_pipeline import (
    run_process_informed_exploration_psro_round,
)


def _build_real_log() -> OcelLog:
    """Same real construction pattern reused across this session's
    `SqliteProcessScienceProvider`/`process_informed_exploration` tests."""
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


def _real_observation(ref: str) -> EnterpriseObservation:
    return EnterpriseObservation(ontology_graph_ref=ref, source_provenance_ref="test", enterprise_world_ref="test-world")


def _real_metadata():
    from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
        ScenarioMetadata_checkout_latency_scenario_v_1,
    )

    return ScenarioMetadata_checkout_latency_scenario_v_1()


def test_full_real_triz_pipeline_from_ocel_evidence_to_a_real_psro_advance(tmp_path) -> None:
    log = _build_real_log()
    db_path = tmp_path / "pipeline_triz.sqlite"
    to_sqlite(log, db_path)

    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST, worsening_parameter=TRIZParameter.AUTHORITY_NEEDS
    )

    result = run_process_informed_exploration_psro_round(
        _real_metadata(),
        db_path=str(db_path),
        observation=_real_observation("ontology:pipeline-triz-test"),
        candidate_generator=lambda hyps: generate_triz_candidates(hyps, contradiction),
        league=PlannerLeague(),
        domain=Maze(),
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )

    assert isinstance(result, ExplorationPsroRoundOutcome)
    # 2 real hypotheses (rule-based + process-informed) * 4 real matched
    # TRIZ principles = 8 real candidates, each admitted as one real
    # payoff observation.
    assert len(result.admissions) == 8
    assert result.admitted_count == 8
    assert all(a.admitted for a in result.admissions)
    assert len(result.hypergraph.observations) == 8

    for obs in result.hypergraph.observations:
        assert obs.left_score == 0.0
        assert obs.right_score == 1.0
        assert obs.match.left_policy.planner_id == "Astar"
        assert obs.match.right_policy.planner_id == "MCTS"

    assert result.psro_step.advanced
    assert result.psro_step.standing == "ALIVE"
    assert result.psro_step.receipt is not None
    assert result.psro_step.receipt.selected_best_response == "Astar"


def test_pipeline_falsifications_trace_back_to_real_candidates(tmp_path) -> None:
    log = _build_real_log()
    db_path = tmp_path / "pipeline_identity.sqlite"
    to_sqlite(log, db_path)

    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST, worsening_parameter=TRIZParameter.AUTHORITY_NEEDS
    )

    result = run_process_informed_exploration_psro_round(
        _real_metadata(),
        db_path=str(db_path),
        observation=_real_observation("ontology:pipeline-identity-test"),
        candidate_generator=lambda hyps: generate_triz_candidates(hyps, contradiction),
        league=PlannerLeague(),
        domain=Maze(),
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )

    for admission in result.admissions:
        assert admission.observation is not None
        assert admission.observation.receipt_id
        assert admission.standing == "ALIVE"

    receipt_ids = {a.observation.receipt_id for a in result.admissions}
    assert len(receipt_ids) == 8


def test_full_real_montecarlo_pipeline_reaches_a_real_partial_falsification(tmp_path) -> None:
    """Closes the real gap this pass's own investigation found: Monte
    Carlo candidates had real coverage only in `exploration_payoff_bridge.
    py`'s own unit test (hand-built `ExperimentReceipt` fixtures) -- never
    through a real gymact-mediated experiment, never through a real PSRO
    step, and never through this pipeline (confirmed via `grep -rln
    "generate_montecarlo_candidates"
    tests/reasoning/test_exploration_gymact_falsification_chicago.py
    tests/reasoning/test_exploration_psro_loop_chicago.py`: zero matches
    before this test). Also proves this refactored pipeline is genuinely
    generic, not TRIZ-specific: Monte Carlo's empty `migration_actions`/
    `expected_effects` drive a real, structurally different falsification
    outcome (`PARTIAL`, not TRIZ's `FALSIFIED`) through the exact same
    real pipeline code."""
    log = _build_real_log()
    db_path = tmp_path / "pipeline_montecarlo.sqlite"
    to_sqlite(log, db_path)

    cost_model = MonteCarloCostModel(distribution=MonteCarloDistribution.UNIFORM, low=10.0, high=50.0)

    result = run_process_informed_exploration_psro_round(
        _real_metadata(),
        db_path=str(db_path),
        observation=_real_observation("ontology:pipeline-montecarlo-test"),
        candidate_generator=lambda hyps: generate_montecarlo_candidates(hyps, cost_model, n=3),
        league=PlannerLeague(),
        domain=Maze(),
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )

    # 2 real hypotheses (rule-based + process-informed) * 3 real Monte
    # Carlo samples each = 6 real candidates.
    assert len(result.admissions) == 6
    assert result.admitted_count == 6
    assert len(result.hypergraph.observations) == 6

    for obs in result.hypergraph.observations:
        assert obs.left_score == 0.5
        assert obs.right_score == 0.5
        assert obs.match.left_policy.planner_id == "Astar"
        assert obs.match.right_policy.planner_id == "MCTS"

    assert result.psro_step.advanced
    assert result.psro_step.standing == "ALIVE"
    assert result.psro_step.receipt is not None
    assert result.psro_step.receipt.selected_best_response == "Astar"


def test_montecarlo_and_triz_pipelines_produce_distinct_real_falsification_standings(tmp_path) -> None:
    """Direct, single-test proof that this generic pipeline is not
    secretly TRIZ-shaped: the exact same real infrastructure (log, db,
    league, domain, planners) produces a real `FALSIFIED` outcome for TRIZ
    and a real `PARTIAL` outcome for Monte Carlo, driven purely by each
    generator's own real candidate field shape."""
    log = _build_real_log()

    triz_db_path = tmp_path / "compare_triz.sqlite"
    to_sqlite(log, triz_db_path)
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST, worsening_parameter=TRIZParameter.AUTHORITY_NEEDS
    )
    triz_result = run_process_informed_exploration_psro_round(
        _real_metadata(),
        db_path=str(triz_db_path),
        observation=_real_observation("ontology:compare-triz"),
        candidate_generator=lambda hyps: generate_triz_candidates(hyps, contradiction),
        league=PlannerLeague(),
        domain=Maze(),
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )

    mc_db_path = tmp_path / "compare_mc.sqlite"
    to_sqlite(log, mc_db_path)
    cost_model = MonteCarloCostModel(distribution=MonteCarloDistribution.UNIFORM, low=10.0, high=50.0)
    mc_result = run_process_informed_exploration_psro_round(
        _real_metadata(),
        db_path=str(mc_db_path),
        observation=_real_observation("ontology:compare-mc"),
        candidate_generator=lambda hyps: generate_montecarlo_candidates(hyps, cost_model, n=3),
        league=PlannerLeague(),
        domain=Maze(),
        constructor_planner_ids=["Astar"],
        falsifier_planner_id="MCTS",
    )

    triz_scores = {(o.left_score, o.right_score) for o in triz_result.hypergraph.observations}
    mc_scores = {(o.left_score, o.right_score) for o in mc_result.hypergraph.observations}
    assert triz_scores == {(0.0, 1.0)}
    assert mc_scores == {(0.5, 0.5)}
    assert triz_scores != mc_scores
