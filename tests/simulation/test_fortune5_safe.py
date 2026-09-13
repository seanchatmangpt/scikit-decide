"""Evidence checkpoints for the Fortune-5 SAFe simulation.

These are repo-local model-execution tests, not evidence that a real enterprise is
faithfully represented or that any plan was admitted/actuated outside AutoFDE-Lab.
"""

from dataclasses import fields

from autofde_lab.simulation.fortune5_safe import (
    SCENARIOS,
    Fortune5Config,
    ScenarioName,
    all_policies,
    build_topology,
    replay,
    run_episode,
    run_full_matrix,
)


def test_fortune5_topology_closes_scale_budget_roles_dependencies_and_cadence():
    config = Fortune5Config()
    topology = build_topology(config)

    assert topology.counts["portfolios"] == 4
    assert topology.counts["value_streams"] == 20
    assert topology.counts["solution_trains"] == 10
    assert topology.counts["arts"] == 60
    assert topology.counts["teams"] == 720
    assert topology.counts["personnel"] == 7_200
    assert topology.counts["strategic_themes"] == 8
    assert topology.counts["epics"] == 40
    assert topology.counts["capabilities"] == 160
    assert topology.counts["features"] == 960
    assert topology.counts["stories"] == 8_640
    assert topology.counts["work_items"] == 9_808
    assert topology.counts["enablers"] > 0
    assert topology.annual_budget_usd == 1_200_000_000.0
    assert topology.counts["role_assignments"] >= 300
    assert topology.counts["dependencies"] >= 700
    assert topology.counts["cadence_events_per_pi"] > 40_000


def test_dfcm_preserves_entire_combinatorial_policy_space_without_winner_field():
    policies = all_policies()
    assert len(policies) == 5 * 4 * 4 * 3 * 3 * 3 == 2_160
    assert len({policy.id for policy in policies}) == len(policies)


def test_all_enterprise_disruption_scenarios_are_present():
    assert {scenario.name for scenario in SCENARIOS} == set(ScenarioName)
    assert len(SCENARIOS) == 10


def test_episode_receipt_replays_exactly_and_scenario_changes_consequence():
    config = Fortune5Config(seed=42)
    topology = build_topology(config)
    policy = all_policies()[0]
    baseline = run_episode(policy, SCENARIOS[0], config, topology)
    disruption = run_episode(policy, SCENARIOS[-1], config, topology)

    assert replay(baseline, config, topology)
    assert baseline.receipt.standing == "MODEL_EXECUTED"
    assert baseline.receipt.authority == "NON_ACTUATING_MODEL_ONLY"
    assert baseline.receipt.output_digest != disruption.receipt.output_digest
    assert baseline.receipt.trace_digest != disruption.receipt.trace_digest


def test_full_matrix_keeps_feasible_set_and_pareto_frontier_not_single_selection():
    result = run_full_matrix()

    assert result.policy_count == 2_160
    assert result.scenario_count == 10
    assert result.episode_count == 21_600
    assert len(result.feasible_policy_ids) > 1
    assert len(result.pareto_policy_ids) > 1
    assert set(result.pareto_policy_ids).issubset(result.feasible_policy_ids)
    assert 0.0 < result.diversity_score <= 1.0
    assert len(result.matrix_digest) == 64
    assert "winner" not in {field.name for field in fields(result)}
    assert "selected_policy" not in {field.name for field in fields(result)}


def test_full_matrix_is_deterministic_for_exact_subject_and_seed():
    sample = all_policies()[:24]
    left = run_full_matrix(Fortune5Config(seed=2030), policies=sample)
    right = run_full_matrix(Fortune5Config(seed=2030), policies=sample)
    changed = run_full_matrix(Fortune5Config(seed=2031), policies=sample)

    assert left.matrix_digest == right.matrix_digest
    assert left.pareto_policy_ids == right.pareto_policy_ids
    assert left.matrix_digest != changed.matrix_digest
