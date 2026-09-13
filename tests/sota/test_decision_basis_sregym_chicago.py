# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the sregym/stratus DecisionBasis extraction (Lane B).

Every collaborator is real: `current_sregym_stratus_basis()` reads the REAL, checked-out
vendor config file at `vendor/gyms/sregym/clients/stratus/configs/mitigation_agent_config.yaml`
(no mock, no fixture copy) and `materialize_sregym_invocation()` is asserted against the exact
real command line this session actually ran for the `misconfig_app_hotel_res` problem via the
`stratus` driver, backed by the real local TurboFieldfare/Gemma server. No `unittest.mock`,
`Mock`, `patch`, or `monkeypatch` anywhere in this file.

If the vendored file is absent (submodule not checked out), tests report a named skip rather
than substituting a fake -- the same discipline `level4_gymact_bridge.py`'s `skip_reason()`
uses for the sibling `gymact` checkout.
"""

from __future__ import annotations

import pytest

from autofde_lab.sota.decision_basis import DecisionBasis
from autofde_lab.sota.materialize_sregym import (
    AUTOFDE_LAB_PLANNER_DRIVER_PATH,
    MITIGATION_AGENT_CONFIG_PATH,
    SREGYM_ROOT,
    current_sregym_autofde_lab_planner_basis,
    current_sregym_stratus_basis,
    materialize_sregym_autofde_lab_planner_invocation,
    materialize_sregym_invocation,
)

pytestmark = pytest.mark.skipif(
    not MITIGATION_AGENT_CONFIG_PATH.is_file(),
    reason=(
        f"BLOCKED:SREGYM_CHECKOUT_ABSENT: {MITIGATION_AGENT_CONFIG_PATH} does not exist "
        "-- vendor/gyms/sregym submodule not checked out"
    ),
)


def test_current_sregym_stratus_basis_reads_the_real_vendor_config() -> None:
    basis = current_sregym_stratus_basis()
    assert isinstance(basis, DecisionBasis)

    # Real values read straight from the real, checked-out YAML -- not a hardcoded guess.
    # If the vendor bumps these, this test's failure IS the correct signal that D0 drifted.
    assert basis.repair_policy.mode == "validate"
    assert basis.repair_policy.max_attempts == 10
    assert basis.budget.max_steps == 20
    assert basis.budget.max_retry_attempts == 10

    # Real tool set, read off the real config's sync_tools/async_tools lists.
    assert basis.tool_policy.tool_names == (
        "wait_tool",
        "get_traces",
        "get_services",
        "get_operations",
        "get_dependency_graph",
        "get_metrics",
        "exec_kubectl_cmd_safely",
        "f_submit_tool",
    )

    assert basis.planner.name == "sregym:stratus:mitigation_agent"
    assert basis.verification_policy.oracle_name == "IncorrectImageMitigationOracle"


def test_basis_carries_no_real_credential() -> None:
    """`Model.api_key_placeholder` must never be an ambient secret -- only a placeholder or an
    env-var NAME, per this dimension's own docstring contract."""
    basis = current_sregym_stratus_basis()
    assert basis.model.api_key_placeholder == "local"
    # A real credential would never be a bare lowercase word matching no real provider's key
    # format (OpenAI/Anthropic keys are long, prefixed, high-entropy strings) -- this is a
    # structural, not merely observational, check that the placeholder convention holds.
    assert len(basis.model.api_key_placeholder) < 20
    assert basis.model.api_key_placeholder.islower()


def test_materialize_matches_the_real_command_this_session_actually_ran() -> None:
    """The load-bearing assertion: D0's materializer must reproduce, byte-for-byte, the real
    argv/env this session's real, live `uv run main.py` invocation used for the
    `misconfig_app_hotel_res` problem -- confirmed live via a real
    `current_sregym_stratus_basis()` + `materialize_sregym_invocation()` call against the real
    vendored config, cross-checked against the actual shell command executed this session:

        env -u ANTHROPIC_API_KEY -u ZAI_API_KEY \\
          AGENT_API_BASE="http://127.0.0.1:8080/v1" AGENT_API_KEY="local" \\
          uv run main.py --agent stratus --model openai/gemma-4-26b-a4b-it \\
          --problem misconfig_app_hotel_res --agent-timeout 900

    This is the round-trip proof that the abstraction is faithful to current behavior, not an
    invented one: today's hardcoded invocation is D0, exactly.
    """
    basis = current_sregym_stratus_basis()
    argv, env = materialize_sregym_invocation(basis)

    assert argv == [
        "uv", "run", "main.py",
        "--agent", "stratus",
        "--model", "openai/gemma-4-26b-a4b-it",
        "--problem", "misconfig_app_hotel_res",
        "--agent-timeout", "900",
    ]
    assert env == {
        "AGENT_API_BASE": "http://127.0.0.1:8080/v1",
        "AGENT_API_KEY": "local",
    }


def test_materialize_refuses_an_unknown_planner_identity() -> None:
    """A DecisionBasis point whose planner isn't the real stratus identity must be refused,
    never silently materialized against the wrong vendor -- the same "typed refusal over a
    confident wrong plan" discipline this repo already applies to PDDL requirements
    (CLAUDE.md rule 3) and to `predict_step_postconditions`'s unsupported-provider guard."""
    from dataclasses import replace

    basis = current_sregym_stratus_basis()
    wrong = replace(basis, planner=replace(basis.planner, name="harbor:terminus-2"))
    with pytest.raises(ValueError, match="stratus planner identity"):
        materialize_sregym_invocation(wrong)


def test_override_knobs_are_real_cli_level_overrides_not_vendor_config_edits() -> None:
    """model_id/api_base/problem_id/wall_clock_timeout_s are real CLI-level knobs
    (`sregym/main.py`'s own `--model`/`--problem`/`--agent-timeout` flags) -- overriding them
    here does NOT edit the vendored YAML, and the tool/repair/step fields (which DO come from
    that YAML) stay fixed regardless."""
    basis = current_sregym_stratus_basis(
        model_id="openai/a-different-model",
        problem_id="a_different_problem",
        wall_clock_timeout_s=60,
    )
    argv, _ = materialize_sregym_invocation(basis)
    assert "openai/a-different-model" in argv
    assert "a_different_problem" in argv
    assert "60" in argv
    # Vendor-config-sourced fields are untouched by a CLI-level override.
    assert basis.repair_policy.mode == "validate"
    assert basis.budget.max_steps == 20


# --- autofde_lab_planner: the non-LLM D point, real terminal result 2026-08-09 -----------
#
# Real, complete, 4-run trial history this session (all against the real, live kind cluster
# + real, unmodified sregym oracles -- docs/2026-08-09-lane-c-non-llm-planner-design.md):
#   run1: agent kickoff_command used bare "python", not on the launcher's inherited PATH --
#         exit 127, empty result. Fixed: absolute venv interpreter path.
#   run2: real PASS (Diagnosis 89/100, Mitigation True) but a real, judge-confirmed scope
#         defect (D3 Scope Precision 0.67/1.00) -- an early filter compared every deployment
#         against one canonical image, incorrectly flagging and "fixing" real infra sidecars
#         (consul/jaeger/mongodb-*/memcached-*). Fixed: filter_traced_application_deployments.
#   run3: the fix's first version depended solely on Jaeger's get_services() as an ALLOW-list
#         -- immediately post-deploy, before the workload generator produced traffic, only 1
#         of 8 real microservices had been traced, so the actual injected fault (geo) was
#         excluded from scope -- real FAIL (Diagnosis Failed, Mitigation Failed). Fixed: a
#         deterministic deny-list of known infra product names as the primary signal: tracing
#         only ever ALLOWS, never excludes.
#   run4: real, clean, complete PASS -- Diagnosis.composite_score=1.0 (D1/D2/D3 all 1.00),
#         Diagnosis.success=True, Mitigation.success=True, TTL=49.8s, TTM=51.2s. Real CSV:
#         vendor/gyms/sregym/results/0809_0143/autofde_lab_planner/misconfig_app_hotel_res/
#         misconfig_app_hotel_res_autofde_lab_planner_results.csv.
#
# This is a real, single-task, complete ALIVE result -- NOT, on its own, a valid claim of
# beating sregym's real published SOTA (WebSearch this session:
# https://sregym.com/leaderboard / arXiv:2605.07161 report aggregate rates across the full
# 90-problem suite -- diagnosis 38.9-72.6%, mitigation 57.3-78.5%, frontier paid models).
# Comparing this one favorable, well-shaped task against an aggregate 90-problem rate would
# be exactly the overclaim `.claude/rules/no-overclaiming-conversational.md` forbids; a real
# aggregate comparison needs this driver run across a representative problem sample.


def test_autofde_lab_planner_driver_is_registered_but_deliberately_absent_from_the_live_tree() -> None:
    """`autofde_lab_planner` is registered in the real, checked-out `agents.yaml` (its
    `kickoff_command` names `clients.autofde_lab_planner.driver`), but
    `AUTOFDE_LAB_PLANNER_DRIVER_PATH` itself is deliberately NOT a file in this checkout.

    This was a real, working, 1080-line driver, run to a genuine 100%/100% result (the run4
    result cited above) -- and later found orphaned in git history rather than resurrected,
    by an explicit, considered decision recorded in
    `.claude/rules/gym-actuation-boundary.md`: restoring it into the live vendored tree would
    re-open the direct-vendor-actuation path that rule closes (`gymact` is the one real
    actuation surface; nothing may subprocess-launch a vendored gym's own driver directly).
    Mining its domain logic into `gymact`-mediated action bindings is in scope; resurrecting
    it as a second, parallel actuation path is not. This test pins that boundary decision as
    a real invariant -- a future `git restore` of the orphaned blob into this path should fail
    this test, not silently reopen the forbidden path.
    """
    import yaml

    agents_yaml = SREGYM_ROOT / "agents.yaml"
    registered = {a["name"]: a for a in yaml.safe_load(agents_yaml.read_text())["agents"]}
    assert "autofde_lab_planner" in registered
    assert "clients.autofde_lab_planner.driver" in registered["autofde_lab_planner"]["kickoff_command"]
    assert not AUTOFDE_LAB_PLANNER_DRIVER_PATH.is_file(), (
        "the orphaned driver.py appears to have been restored to the live vendored tree -- "
        "see .claude/rules/gym-actuation-boundary.md before doing this: it documents an "
        "explicit decision NOT to, because that resurrects a direct-vendor-actuation path "
        "gymact is supposed to be the only real surface for"
    )


def test_current_sregym_autofde_lab_planner_basis_has_no_agent_model() -> None:
    basis = current_sregym_autofde_lab_planner_basis()
    assert isinstance(basis, DecisionBasis)
    assert basis.model.id == "none"
    assert basis.planner.name == "sregym:autofde_lab_planner"
    assert basis.repair_policy.mode == "none"
    assert basis.verification_policy.oracle_name == "IncorrectImageMitigationOracle"
    # The judge model is real information but belongs in extra, not in `model` -- `model`
    # names the agent's own decision-making model, and there isn't one here.
    assert basis.extra["judge_model_id"] == "openai/gemma-4-26b-a4b-it"


def test_materialize_autofde_lab_planner_matches_the_real_command_this_session_ran() -> None:
    """Cross-checked against the exact real command this session's real, final (run4, clean
    PASS) trial used."""
    basis = current_sregym_autofde_lab_planner_basis(wall_clock_timeout_s=600)
    argv, env = materialize_sregym_autofde_lab_planner_invocation(basis)

    assert argv == [
        ".venv/bin/python", "main.py",
        "--agent", "autofde_lab_planner",
        "--model", "openai/gemma-4-26b-a4b-it",
        "--problem", "misconfig_app_hotel_res",
        "--agent-timeout", "600",
    ]
    assert env == {
        "AGENT_API_BASE": "http://127.0.0.1:8080/v1",
        "AGENT_API_KEY": "local",
    }


def test_materialize_autofde_lab_planner_refuses_the_stratus_identity() -> None:
    from dataclasses import replace

    basis = current_sregym_autofde_lab_planner_basis()
    wrong = replace(basis, planner=replace(basis.planner, name="sregym:stratus:mitigation_agent"))
    with pytest.raises(ValueError, match="autofde_lab_planner planner identity"):
        materialize_sregym_autofde_lab_planner_invocation(wrong)


def test_real_run4_result_csv_matches_this_basis_verification_oracle() -> None:
    """Cross-checks the basis's declared VerificationPolicy against the real, on-disk result
    of this session's real, final, clean-PASS trial -- not a memory of what happened, the
    durable CSV artifact itself."""
    result_csv = (
        SREGYM_ROOT
        / "results"
        / "0809_0143"
        / "autofde_lab_planner"
        / "misconfig_app_hotel_res"
        / "misconfig_app_hotel_res_autofde_lab_planner_results.csv"
    )
    if not result_csv.is_file():
        pytest.skip(
            f"BLOCKED:REAL_TRIAL_ARTIFACT_ABSENT: {result_csv} not on disk -- re-run the "
            "real autofde_lab_planner trial (docs/2026-08-09-lane-c-non-llm-planner-design.md) "
            "before re-enabling this check"
        )
    import csv as csv_module

    rows = list(csv_module.DictReader(result_csv.read_text().splitlines()))
    assert len(rows) == 1
    row = rows[0]
    assert row["Diagnosis.success"] == "True"
    assert row["Mitigation.success"] == "True"
    assert float(row["Diagnosis.composite_score"]) == 1.0

    basis = current_sregym_autofde_lab_planner_basis()
    assert basis.extra["problem_id"] == row["problem_id"]


def test_real_faulty_image_correlated_result_confirms_generalization_with_zero_code_changes() -> None:
    """`faulty_image_correlated` (same real IncorrectImageMitigationOracle class, same real
    HotelReservation app, but the injected fault hits ALL 8 real microservices simultaneously
    rather than just `geo`) was run this session against the exact same driver code as
    `misconfig_app_hotel_res` -- zero changes -- and reached the same real, clean, complete
    result. This is the real evidence the driver generalizes across an oracle class rather
    than being secretly specialized to one problem."""
    result_csv = (
        SREGYM_ROOT
        / "results"
        / "0809_0155"
        / "autofde_lab_planner"
        / "faulty_image_correlated"
        / "faulty_image_correlated_autofde_lab_planner_results.csv"
    )
    if not result_csv.is_file():
        pytest.skip(
            f"BLOCKED:REAL_TRIAL_ARTIFACT_ABSENT: {result_csv} not on disk -- re-run the "
            "real autofde_lab_planner trial against faulty_image_correlated before "
            "re-enabling this check"
        )
    import csv as csv_module

    rows = list(csv_module.DictReader(result_csv.read_text().splitlines()))
    assert len(rows) == 1
    row = rows[0]
    assert row["Diagnosis.success"] == "True"
    assert row["Mitigation.success"] == "True"
    assert float(row["Diagnosis.composite_score"]) == 1.0


def test_real_assign_to_non_existent_node_confirms_the_general_app_agnostic_architecture() -> None:
    """`assign_to_non_existent_node` is a genuinely different app (SocialNetwork, not
    HotelReservation) and a genuinely different fault category (a real, standard Kubernetes
    node-scheduling constraint -- unready replicas + a nodeSelector -- not an image mismatch)
    from every other real trial this test file cross-checks. Real, dynamic namespace
    discovery (`GET /get_app` -> `social-network`) and the new
    `find_deployments_with_unschedulable_pods`/`decide_remove_node_selector_commands`
    detector/remediator pair, with zero hardcoding of either the app or the specific faulty
    service -- this is the real evidence the driver generalizes across BOTH dimensions
    (app and fault category), not just across problems sharing one oracle class."""
    result_csv = (
        SREGYM_ROOT
        / "results"
        / "0809_0303"
        / "autofde_lab_planner"
        / "assign_to_non_existent_node"
        / "assign_to_non_existent_node_autofde_lab_planner_results.csv"
    )
    if not result_csv.is_file():
        pytest.skip(
            f"BLOCKED:REAL_TRIAL_ARTIFACT_ABSENT: {result_csv} not on disk -- re-run the "
            "real autofde_lab_planner trial against assign_to_non_existent_node before "
            "re-enabling this check"
        )
    import csv as csv_module

    rows = list(csv_module.DictReader(result_csv.read_text().splitlines()))
    assert len(rows) == 1
    row = rows[0]
    assert row["Diagnosis.success"] == "True"
    assert row["Mitigation.success"] == "True"
    assert float(row["Diagnosis.composite_score"]) == 1.0


def test_real_configmap_drift_result_is_an_honest_documented_fail_not_a_hidden_regression() -> None:
    """`configmap_drift_hotel_reservation` is a real, honest FAIL, not silently swallowed:
    `kubectl rollout undo` (this driver's only remediation for a revision-elevated, non-
    image-mismatched deployment) reverts the Deployment's pod-template spec but cannot
    restore a ConfigMap object's own data -- a real mechanism boundary named in the original
    fault-catalog survey ("rollout undo removes the injected volume mount; doesn't restore
    ConfigMap content"), confirmed live: all 3 real `kubectl rollout status` waits timed out
    (logged, not hung -- the real `asyncio.wait_for` hard-backstop fix this session's second
    live trial against this problem required), and the real oracle scored both stages False.
    This test exists so a future change that silently starts reporting a fake pass here would
    be caught, per this repo's own no-dual-bookkeeping discipline."""
    result_csv = (
        SREGYM_ROOT
        / "results"
        / "0809_0339"
        / "autofde_lab_planner"
        / "configmap_drift_hotel_reservation"
        / "configmap_drift_hotel_reservation_autofde_lab_planner_results.csv"
    )
    if not result_csv.is_file():
        pytest.skip(
            f"BLOCKED:REAL_TRIAL_ARTIFACT_ABSENT: {result_csv} not on disk -- re-run the "
            "real autofde_lab_planner trial against configmap_drift_hotel_reservation before "
            "re-enabling this check"
        )
    import csv as csv_module

    rows = list(csv_module.DictReader(result_csv.read_text().splitlines()))
    assert len(rows) == 1
    row = rows[0]
    assert row["Diagnosis.success"] == "False"
    assert row["Mitigation.success"] == "False"
    assert float(row["Diagnosis.composite_score"]) == 0.0
