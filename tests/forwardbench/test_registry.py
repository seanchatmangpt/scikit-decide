import json
from pathlib import Path

from autofde_lab.forwardbench import ForwardBenchRegistry

REGISTRY = Path("docs/papers/generated/forwardbench/registry.json")


def test_registry_is_broad_and_unique():
    data = json.loads(REGISTRY.read_text())
    rows = data["benchmarks"]
    assert data["authority"] == "SELECT_ONLY"
    assert len(rows) >= 60
    assert len({r["slug"] for r in rows}) == len(rows)


def test_cube_returns_candidate_not_execution():
    plan = ForwardBenchRegistry(REGISTRY).plan("cube-standard")
    assert plan.status == "CANDIDATE"
    assert plan.reason == "SELECT_ONLY:NO_ACTUATION"
    assert plan.commands


def test_live_cloud_goat_requires_authority():
    plan = ForwardBenchRegistry(REGISTRY).plan("cloudgoat")
    assert plan.status == "REFUSED"
    assert plan.reason == "REFUSED:LIVE_AUTHORITY_REQUIRED"


def test_unknown_subject_is_typed_refusal():
    plan = ForwardBenchRegistry(REGISTRY).plan("definitely-not-a-benchmark")
    assert plan.status == "REFUSED"
    assert plan.reason.startswith("REFUSED:")
