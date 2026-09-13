from __future__ import annotations

import json

import pytest

from autofde_lab.planner_league import LeagueMatch, PayoffObservation, PolicySpec
from autofde_lab.reasoning.payoff_bundle import encode_payoff_bundle

typer_testing = pytest.importorskip("typer.testing")
app = __import__("autofde_lab.fabric.cli", fromlist=["app"]).app
runner = typer_testing.CliRunner()


def _seed_bundle() -> str:
    role_id = "plan_constructor"
    observation = PayoffObservation(
        match=LeagueMatch(
            world_id="generic_enterprise",
            left_role_id=role_id,
            left_policy=PolicySpec.for_role("Astar", role_id),
            right_role_id=role_id,
            right_policy=PolicySpec.for_role("BFWS", role_id),
        ),
        left_score=1.0,
        right_score=0.0,
        receipt_id="receipt-seed-a-b",
    )
    return encode_payoff_bundle((observation,))


def test_cli_without_bundle_preserves_fresh_hypergraph_refusal() -> None:
    result = runner.invoke(app, ["dmedi-solve-payoff", "DSPyPolicy", "Astar"])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["reason"] == "REFUSED:LLM_NOVELTY_BOUNDARY:DSPyPolicy"
    assert payload["seeded_observation_count"] == 0
    assert payload["hypergraph_observation_count"] == 0
    assert payload["payoff_bundle"]["observations"] == []


def test_cli_loads_real_bundle_before_existing_novelty_refusal(tmp_path) -> None:
    bundle_path = tmp_path / "payoffs.json"
    bundle_path.write_text(_seed_bundle(), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "dmedi-solve-payoff",
            "DSPyPolicy",
            "Astar",
            "--input-payoff-bundle",
            str(bundle_path),
        ],
    )

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["reason"] == "REFUSED:LLM_NOVELTY_BOUNDARY:DSPyPolicy"
    assert payload["seeded_observation_count"] == 1
    assert payload["hypergraph_observation_count"] == 1
    assert len(payload["payoff_bundle"]["observations"]) == 1


def test_cli_refuses_tampered_bundle_before_planner_execution(tmp_path) -> None:
    bundle = json.loads(_seed_bundle())
    bundle["observations"][0]["left_score"] = 0.0
    bundle_path = tmp_path / "tampered.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "dmedi-solve-payoff",
            "Astar",
            "BFWS",
            "--input-payoff-bundle",
            str(bundle_path),
        ],
    )

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["reason"] == "REFUSED:PAYOFF_BUNDLE_DIGEST_MISMATCH"
    assert payload["hypergraph_observation_count"] == 0
