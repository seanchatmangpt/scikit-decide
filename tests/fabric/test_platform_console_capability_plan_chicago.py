# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style, Phase 6 (final phase) end-to-end suite for
``~/.claude/plans/eager-forging-sparrow.md``: real RDF Turtle ->
real Astar-solved plan -> real live platform-console state snapshot
(when reachable) -> real gymact ontology-driven actuation -> real
before/after diff via wasm4pm-compat's real ``ocel_diff_cli`` Rust
binary, invoked cross-language via ``subprocess`` exactly as that
binary's own module docs describe.

No ``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch``
anywhere in this file. Every collaborator is real:

- ``autofde_lab.fabric.rdf_domain``/``pddl_engine`` (Phase 3, unmodified)
  compile the real ``ontology/platform-console-domain.ttl`` fixture and
  run a real scikit-decide Astar solve.
- The live-infra test performs a real HTTP GET against platform-console's
  real ``/api/internal/capability-state-snapshot`` route (Phase 2), with
  the shared-secret header that route's own source requires, and drives
  real actuation through ``gymact``'s real
  ``PlatformConsoleOntologyDrivenProvider`` (Phase 4,
  ``gymact.gyms.platform_console_ontology_provider``) under a real
  ``GymAct`` kernel with real ``TieredAuthorityResolver`` gates.
- ``ocel_diff_cli`` (Phase 5) is invoked as a real subprocess against the
  actually-built release/debug binary in
  ``wasm4pm-compat/target/{debug,release}/examples/ocel_diff_cli`` --
  never reimplemented in Python.

Matches ``gymact/tests/test_platform_console_provider.py``'s exact named
skip convention: ``pytest.mark.skipif`` on
``PLATFORM_CONSOLE_BASE_URL``/``CAPABILITY_STATE_SNAPSHOT_SECRET`` (this
route's own real env-gated auth, per
``platform-console/app/app/api/internal/capability-state-snapshot/
route.ts``'s ``isCronAuthenticated``) -- skipped, never faked, when no
reachable test-tenant deployment is configured.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest
import rdflib

from autofde_lab.fabric import pddl_engine
from autofde_lab.fabric.rdf_domain import PD, compile_rdf_to_pddl_files

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ontology",
    "platform-console-freeze-override-domain.ttl",
)
# RECONCILIATION NOTE: this is a deliberately separate fixture from the
# committed ontology/platform-console-domain.ttl capability-suite fixture
# -- see ontology/platform-console-freeze-override-domain.ttl's header
# comment and test_platform_console_domain_roundtrip_chicago.py's module
# docstring for the full analysis of why the two shapes cannot share one
# physical Turtle file (compile_rdf_to_pddl's real "exactly one pd:Problem"
# constraint when called with no problem_iri, as this file's tests do).

WASM4PM_COMPAT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "wasm4pm-compat",
)


def _find_ocel_diff_cli() -> str | None:
    """Real lookup of the already-built Phase 5 binary -- prefers
    ``release``, falls back to ``debug`` (both are real `cargo build`
    products, never a stub)."""
    for profile in ("release", "debug"):
        candidate = os.path.join(WASM4PM_COMPAT_DIR, "target", profile, "examples", "ocel_diff_cli")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


OCEL_DIFF_CLI = _find_ocel_diff_cli()

BASE_URL = os.environ.get("PLATFORM_CONSOLE_BASE_URL")
SNAPSHOT_SECRET = os.environ.get("CAPABILITY_STATE_SNAPSHOT_SECRET")
API_KEY = os.environ.get("PLATFORM_CONSOLE_API_KEY")

_live_reachable = bool(BASE_URL and SNAPSHOT_SECRET and API_KEY)

_SKIP_REASON = (
    "PLATFORM_CONSOLE_BASE_URL/CAPABILITY_STATE_SNAPSHOT_SECRET/"
    "PLATFORM_CONSOLE_API_KEY not set -- no reachable test-tenant "
    "platform-console deployment configured. Skipped, not mocked, "
    "matching gymact/tests/test_platform_console_provider.py's own "
    "skip-named-not-mocked convention exactly."
)


def _run_ocel_diff_cli(before: dict, after: dict, expected: dict, tmp_path) -> dict:
    """Real subprocess invocation of the real Rust binary -- writes real
    JSON files to disk, shells out, parses the real stdout JSON. No
    Python-side reimplementation of the diff/match logic."""
    assert OCEL_DIFF_CLI is not None, (
        "ocel_diff_cli binary not found under wasm4pm-compat/target/{debug,release}/"
        "examples/ -- run `cargo build --example ocel_diff_cli` in wasm4pm-compat first."
    )
    before_p = tmp_path / "before.json"
    after_p = tmp_path / "after.json"
    expected_p = tmp_path / "expected.json"
    before_p.write_text(json.dumps({"facts": before}))
    after_p.write_text(json.dumps({"facts": after}))
    expected_p.write_text(json.dumps({"facts": expected}))

    proc = subprocess.run(
        [OCEL_DIFF_CLI, str(before_p), str(after_p), str(expected_p)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode in (0, 2), (
        f"ocel_diff_cli exited {proc.returncode} unexpectedly: stderr={proc.stderr!r}"
    )
    return json.loads(proc.stdout)


def _solve_real_plan(tmp_path) -> list[str]:
    """Reuses Phase 3's pipeline, unmodified: real TTL -> real compiled
    PDDL -> real Astar solve -> real plan lines."""
    domain_p = str(tmp_path / "domain.pddl")
    problem_p = str(tmp_path / "problem.pddl")
    plan_p = str(tmp_path / "plan.txt")

    graph = rdflib.Graph()
    graph.parse(FIXTURE, format="turtle")
    assert list(graph.subjects(rdflib.RDF.type, PD.Domain)), "fixture must declare a pd:Domain"

    compile_rdf_to_pddl_files(FIXTURE, domain_p, problem_p)
    rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)
    assert rc == pddl_engine.EXIT_PLAN_FOUND
    return open(plan_p, encoding="utf-8").read().splitlines()


# ---------------------------------------------------------------------------
# Always-runs test (step 3): fixture-shaped snapshots + real ocel_diff_cli,
# no live infra required. Exercises the full cross-language wiring (Rust
# binary invoked via subprocess from Python) end to end.
# ---------------------------------------------------------------------------


def test_ocel_diff_cli_matches_real_plan_step_effect_against_fixture_snapshots(tmp_path):
    """Two hand-written fixture snapshots, shaped exactly like Phase 2's
    real ``CapabilityStateSnapshot.facts`` response type (``deployedCastle``,
    ``frozenOrg``, ``freezeOverrideApprovedOrg``, ``jobComplete``), plus the
    real solved plan's first step's declared effect
    (``freeze-override-approved(org1)`` from ``action-freeze-override`` in
    ``ontology/platform-console-domain.ttl``). Invokes the real Rust
    ``ocel_diff_cli`` binary and asserts a real match."""
    plan_lines = _solve_real_plan(tmp_path)
    assert plan_lines[0] == "(freeze-override org1)"

    before = {
        "deployedCastle": True,
        "frozenOrg": True,
        "freezeOverrideApprovedOrg": False,
        "jobComplete": {"inventory-components": None, "inventory-goals": None},
    }
    after = {
        "deployedCastle": True,
        "frozenOrg": True,
        "freezeOverrideApprovedOrg": True,
        "jobComplete": {"inventory-components": None, "inventory-goals": None},
    }
    # The plan step's declared effect (pd:effect of action-freeze-override):
    # freeze-override-approved(org1) becomes true. Only that fact is
    # declared -- the others are unchanged and must not appear in the diff.
    expected_effect = {"freezeOverrideApprovedOrg": True}

    result = _run_ocel_diff_cli(before, after, expected_effect, tmp_path)

    assert result["diff"]["changed"] == [
        {"predicate": "freezeOverrideApprovedOrg", "old_value": False, "new_value": True}
    ]
    assert result["diff"]["added"] == {}
    assert result["match_result"]["matches"] is True
    assert result["match_result"]["discrepancies"] == []


def test_ocel_diff_cli_catches_a_deliberately_mismatched_effect(tmp_path):
    """Required negative case (matches Phase 5's own verification
    requirement): declare an effect that did NOT actually happen, and
    assert the real Rust binary reports the real mismatch rather than
    silently passing."""
    before = {"jobComplete": {"inventory-components": None}}
    after = {"jobComplete": {"inventory-components": None}}  # unchanged -- job never ran
    expected_effect = {"jobComplete": {"inventory-components": True}}  # falsely declared as run

    result = _run_ocel_diff_cli(before, after, expected_effect, tmp_path)

    assert result["match_result"]["matches"] is False
    assert result["match_result"]["discrepancies"], "a real mismatch must be reported, not swallowed"
    assert any(
        "jobComplete" in d and "expected fact not present" in d
        for d in result["match_result"]["discrepancies"]
    )


# ---------------------------------------------------------------------------
# Live-infra suite (steps 1-2 + real actuation): named-skip when no
# reachable test-tenant platform-console deployment is configured.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _live_reachable, reason=_SKIP_REASON)
def test_real_plan_pre_snapshot_actuation_post_snapshot_and_diff_end_to_end(tmp_path):
    """The full Phase 6 chain against a real, reachable platform-console
    deployment:

    1. Real Astar-solved plan (Phase 3, unmodified).
    2. Real pre-actuation snapshot GET against the real Phase 2 route.
    3. Real actuation of each plan step via gymact's real
       ``PlatformConsoleOntologyDrivenProvider`` (Phase 4), under a real
       ``GymAct``/``TieredAuthorityResolver`` gate.
    4. Real post-actuation snapshot GET.
    5. Real diff via the real ``ocel_diff_cli`` Rust binary (Phase 5),
       asserting the plan's declared effect against the real observed
       before/after facts.
    """
    import anyio
    import httpx

    from gymact.agent import AllowListCapabilityScope
    from gymact.gyms.ontology_gym import TieredAuthorityResolver
    from gymact.gyms.platform_console_ontology_provider import build_platform_console_ontology_provider
    from gymact.kernel import GymAct
    from gymact.models import ActuationIntent, MaterializationIntent

    plan_lines = _solve_real_plan(tmp_path)
    assert plan_lines[0] == "(freeze-override org1)"
    assert set(plan_lines[1:3]) == {
        "(run-verb castle org1 v-inventory-components)",
        "(run-verb castle org1 v-inventory-goals)",
    }

    org_id = os.environ.get("PLATFORM_CONSOLE_TEST_ORG", "default")

    # The skipif gate above already guarantees these are set at runtime.
    # Rebind to locals (rather than asserting the module-level names) so the
    # narrowed `str` type -- not `str | None` -- is what the closure below
    # actually captures; a static checker cannot assume a module-level name
    # is unreassigned by the time a nested closure it captures is called.
    assert BASE_URL is not None
    assert SNAPSHOT_SECRET is not None
    base_url: str = BASE_URL
    snapshot_secret: str = SNAPSHOT_SECRET

    def fetch_snapshot() -> dict:
        response = httpx.get(
            f"{base_url}/api/internal/capability-state-snapshot",
            headers={
                "x-capability-state-snapshot-secret": snapshot_secret,
                "x-capability-state-org": org_id,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["snapshot"]["facts"]

    pre_facts = fetch_snapshot()

    async def actuate_plan() -> dict:
        provider = build_platform_console_ontology_provider()
        standard_ref = "urn:gymact:authority-decision:phase6-standard"
        elevated_ref = "urn:gymact:authority-decision:phase6-elevated"
        principal = "urn:prov:agent:gymact-eager-forging-sparrow-phase6"

        from gymact.gyms.ontology_gym import capability_iri

        task_iris = {t.identifier: capability_iri(provider_name=provider.name, task=t) for t in provider.tasks()}

        gym = GymAct(
            authority_resolver=TieredAuthorityResolver(
                elevated_capabilities=provider.elevated_capability_iris(),
                standard_ref=standard_ref,
                elevated_ref=elevated_ref,
            ),
            capability_scope=AllowListCapabilityScope({principal: frozenset(task_iris.values())}),
        )
        gym.register_provider(provider)

        materialization = await gym.materialize(
            MaterializationIntent(provider=provider.name, config={}, principal=principal)
        )
        assert materialization.accepted, materialization.receipt.reason
        episode_id = materialization.episode.episode_id

        results = {}
        results["freeze-override"] = await gym.act(
            ActuationIntent(
                episode_id=episode_id,
                capability=task_iris["approval.freeze-override"],
                authority_ref=elevated_ref,
                principal=principal,
            )
        )
        assert results["freeze-override"].accepted, results["freeze-override"].receipt.reason

        for verb_key, identifier in (
            ("v-inventory-components", "castle.verb.inventory-components"),
            ("v-inventory-goals", "castle.verb.inventory-goals"),
        ):
            results[verb_key] = await gym.act(
                ActuationIntent(
                    episode_id=episode_id,
                    capability=task_iris[identifier],
                    authority_ref=standard_ref,
                    principal=principal,
                )
            )
            assert results[verb_key].accepted, results[verb_key].receipt.reason

        assert gym.verify_evidence_chain()
        await gym.teardown(episode_id, authority_ref=elevated_ref)
        return results

    actuation_results = anyio.run(actuate_plan)
    for step_name, result in actuation_results.items():
        assert result.accepted, f"plan step {step_name} did not actuate: {result.receipt.reason}"

    post_facts = fetch_snapshot()

    # The plan's first, gating step's declared effect: the maker-checker
    # freeze override becomes approved for this org (matches
    # action-freeze-override's pd:effect in the Phase-3 TTL fixture).
    expected_effect = {"freezeOverrideApprovedOrg": True}
    diff_result = _run_ocel_diff_cli(pre_facts, post_facts, expected_effect, tmp_path)

    assert diff_result["match_result"]["matches"], diff_result["match_result"]["discrepancies"]
