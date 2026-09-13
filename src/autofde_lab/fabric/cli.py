# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typer projection of the shared scikit-decide decision fabric."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from autofde_lab.fabric.cache import SQLiteERRCCache
from autofde_lab.fabric.models import DecisionRefusal, DecisionRequest
from autofde_lab.fabric.service import DecisionFabric

# Display name only -- invoked as `python -m autofde_lab.fabric`, and there
# is no [project.scripts] console script, so no installed entry point
# depends on either spelling. LEGACY_APP_NAME is recorded rather than
# deleted so a doc or script still saying `skdecide-fabric` resolves to
# something findable.
APP_NAME = "autofde-lab-fabric"
LEGACY_APP_NAME = "skdecide-fabric"

app = typer.Typer(
    name=APP_NAME,
    help="CLI, MCP, A2A, DSPy, and ERRC cache for AutoFDE Lab.",
    no_args_is_help=True,
)


def get_fabric(cache_path: Path | None = None) -> DecisionFabric:
    """Construct the shared service; isolated for tests and embedding."""
    cache = SQLiteERRCCache(cache_path) if cache_path is not None else None
    return DecisionFabric(cache=cache)


def _object(value: str, name: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise typer.BadParameter(f"{name} must be valid JSON: {error.msg}") from error
    if not isinstance(decoded, dict):
        raise typer.BadParameter(f"{name} must decode to a JSON object")
    return decoded


def _emit(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))


def _refuse(error: DecisionRefusal) -> None:
    _emit(error.as_dict())
    raise typer.Exit(code=3)


@app.command()
def catalog(
    cache_path: Path | None = typer.Option(None, help="SQLite ERRC cache path"),
) -> None:
    """List registered domains and solvers."""
    try:
        _emit(get_fabric(cache_path).catalog().as_dict())
    except DecisionRefusal as error:
        _refuse(error)


@app.command()
def match(
    domain: str = typer.Argument(..., help="Registered domain name"),
    domain_arguments: str = typer.Option("{}", help="Domain arguments as JSON"),
    use_cache: bool = typer.Option(True, "--cache/--no-cache"),
    cache_path: Path | None = typer.Option(None, help="SQLite ERRC cache path"),
) -> None:
    """Match compatible solvers for a domain."""
    try:
        result = get_fabric(cache_path).match(
            domain,
            domain_arguments=_object(domain_arguments, "domain_arguments"),
            use_cache=use_cache,
        )
        _emit(result.as_dict())
    except DecisionRefusal as error:
        _refuse(error)


@app.command()
def solve(
    domain: str = typer.Argument(..., help="Registered domain name"),
    solver: str | None = typer.Option(None, help="Solver; defaults to first match"),
    domain_arguments: str = typer.Option("{}", help="Domain arguments as JSON"),
    solver_arguments: str = typer.Option("{}", help="Solver arguments as JSON"),
    max_steps: int = typer.Option(100, min=1, help="Bounded rollout transitions"),
    subject_digest: str = typer.Option("UNBOUND_SUBJECT"),
    policy_digest: str = typer.Option("UNBOUND_POLICY"),
    environment_digest: str = typer.Option("UNBOUND_ENVIRONMENT"),
    randomness_digest: str = typer.Option("UNBOUND_RANDOMNESS"),
    use_cache: bool = typer.Option(True, "--cache/--no-cache"),
    cache_path: Path | None = typer.Option(None, help="SQLite ERRC cache path"),
) -> None:
    """Solve and emit a receipt-bearing trajectory."""
    try:
        request = DecisionRequest(
            domain=domain,
            solver=solver,
            domain_arguments=_object(domain_arguments, "domain_arguments"),
            solver_arguments=_object(solver_arguments, "solver_arguments"),
            max_steps=max_steps,
            subject_digest=subject_digest,
            policy_digest=policy_digest,
            environment_digest=environment_digest,
            randomness_digest=randomness_digest,
            use_cache=use_cache,
        )
        _emit(get_fabric(cache_path).solve(request).as_dict())
    except DecisionRefusal as error:
        _refuse(error)


@app.command("cache-stats")
def cache_stats(
    cache_path: Path | None = typer.Option(None, help="SQLite ERRC cache path"),
) -> None:
    """Show cache hits, misses, writes, and namespaces."""
    _emit(get_fabric(cache_path).cache_stats())


@app.command("cache-hotset")
def cache_hotset(
    cache_path: Path | None = typer.Option(None, help="SQLite ERRC cache path"),
) -> None:
    """Measure whether 20% of artifacts account for 80% of reuse."""
    _emit(get_fabric(cache_path).cache_hotset())


def _dflss_solve_payoff_outcome_dict(outcome: Any) -> dict[str, Any]:
    return {
        "planner_id": outcome.planner_id,
        "standing": outcome.standing,
        "reason": outcome.reason,
        "plan_length": outcome.plan_length,
    }


@app.command("dmedi-solve-payoff")
def dmedi_solve_payoff(
    left_planner: str = typer.Argument(..., help="Left planner id, e.g. Astar"),
    right_planner: str = typer.Argument(..., help="Right planner id, e.g. LRTAstar"),
    world_id: str = typer.Option("generic_enterprise", help="LeagueMatch world id"),
    role_id: str = typer.Option(
        "plan_constructor", help="LeagueMatch role id for both sides"
    ),
    observation_projection_id: str = typer.Option("full_observation"),
    budget_id: str = typer.Option("balanced"),
    input_payoff_bundle: Path | None = typer.Option(
        None,
        "--input-payoff-bundle",
        help="Read a deterministic payoff-evidence bundle and seed the in-process hypergraph",
    ),
) -> None:
    """Drive two real planners through the DMEDI-curriculum PDDL problem and
    emit one receipt-bearing head-to-head observation plus a portable payoff
    bundle.

    Without ``--input-payoff-bundle`` the hypergraph is fresh, preserving the
    previous behavior. With it, only already-receipted observations that pass
    bundle digest and structural admission are loaded before the new attempt.
    This is evidence transport, not persistence authority or actuation.
    """
    from autofde_lab.planner_league import PayoffHypergraph
    from autofde_lab.reasoning.dflss_solve_payoff_bridge import (
        admit_dflss_solve_payoff,
    )
    from autofde_lab.reasoning.lab_standing import dflss_solve_payoff_production_claim
    from autofde_lab.reasoning.payoff_bundle import (
        decode_payoff_bundle,
        encode_payoff_bundle,
    )

    hypergraph = PayoffHypergraph()
    seeded_observation_count = 0
    if input_payoff_bundle is not None:
        try:
            prior_observations = decode_payoff_bundle(
                input_payoff_bundle.read_text(encoding="utf-8")
            )
        except OSError as exc:
            _emit(
                {
                    "standing": "REFUSED",
                    "reason": f"REFUSED:PAYOFF_BUNDLE_READ:{type(exc).__name__}",
                    "admitted": False,
                    "seeded_observation_count": 0,
                    "hypergraph_observation_count": 0,
                }
            )
            raise typer.Exit(code=3) from exc
        except ValueError as exc:
            _emit(
                {
                    "standing": "REFUSED",
                    "reason": str(exc),
                    "admitted": False,
                    "seeded_observation_count": 0,
                    "hypergraph_observation_count": 0,
                }
            )
            raise typer.Exit(code=3) from exc
        for observation in prior_observations:
            hypergraph.add(observation)
        seeded_observation_count = len(prior_observations)

    result = admit_dflss_solve_payoff(
        left_planner,
        right_planner,
        hypergraph=hypergraph,
        world_id=world_id,
        role_id=role_id,
        observation_projection_id=observation_projection_id,
        budget_id=budget_id,
    )

    payload: dict[str, Any] = {
        "standing": result.standing,
        # `standing` is real, legitimate evidence within the lab domain
        # (`V2030.1.1-PRD-ARD.md` capability 9). `production_claim` is the
        # typed refusal every lab-scoped standing must carry across the
        # lab/production boundary -- see `reasoning.lab_standing`.
        "production_claim": dflss_solve_payoff_production_claim(result),
        "reason": result.reason,
        "admitted": result.admitted,
        "left_outcome": _dflss_solve_payoff_outcome_dict(result.left_outcome),
        "right_outcome": _dflss_solve_payoff_outcome_dict(result.right_outcome),
        "observation": None
        if result.observation is None
        else {
            "left_score": result.observation.left_score,
            "right_score": result.observation.right_score,
            "receipt_id": result.observation.receipt_id,
            "world_id": result.observation.match.world_id,
            "left_role_id": result.observation.match.left_role_id,
            "right_role_id": result.observation.match.right_role_id,
            "left_planner_id": result.observation.match.left_policy.planner_id,
            "right_planner_id": result.observation.match.right_policy.planner_id,
        },
        "seeded_observation_count": seeded_observation_count,
        "hypergraph_observation_count": len(hypergraph.observations),
        "payoff_bundle": json.loads(encode_payoff_bundle(hypergraph.observations)),
    }
    _emit(payload)
    if not result.admitted:
        raise typer.Exit(code=3)


@app.command("serve-mcp")
def serve_mcp(
    dspy_compile: bool = typer.Option(
        False,
        "--dspy-compile",
        help=(
            "Also expose decision_compile, backed by a real "
            "DSPyDecisionCompiler. Off by default: this pulls in dspy and "
            "expects an LM to be configured by the caller (see "
            "autofde_lab.fabric.dspy's module docstring); the base server "
            "should not require that dependency to start."
        ),
    ),
) -> None:
    """Run the FastMCP server over stdio."""
    from autofde_lab.fabric.mcp import create_server

    compiler = None
    if dspy_compile:
        from autofde_lab.fabric.dspy import DSPyDecisionCompiler

        compiler = DSPyDecisionCompiler()

    create_server(compiler=compiler).run()


@app.command("serve-a2a")
def serve_a2a(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(9999, min=1, max=65535),
) -> None:
    """Run the A2A JSON-RPC server."""
    from autofde_lab.fabric.a2a import run

    run(host=host, port=port)
