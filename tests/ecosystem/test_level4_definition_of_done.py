# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Orthogonal definition-of-done suite for the Level 4 acceptance equation.

This is NOT ``test_level4_crown_chicago.py``. That file exercises component
internals (typed-state projection, causal refinement, planner inventory,
federation agreement). This file pins the **acceptance equation** and the
**anti-cheating law**: one independent property per test, so that a single
regression cannot be masked by a neighbouring test still passing.

Chicago throughout: real GymAct episodes driven through the real
``~/gymact/.venv`` subprocess bridge, real files on disk, real induced
models, assertions on final state only. No mocks anywhere.

The gymact-backed tests skip -- and only skip -- on the named blocker from
``level4_gymact_bridge.skip_reason()`` when the sibling checkout or its venv
is genuinely absent. That is an environment gate, never a substitution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.gym_procedure import Recipe
from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    AdvisoryAuthorityRefused,
    AdvisoryCritique,
    PowlCommitment,
    ValidatedPlan,
    commit,
    commit_and_execute,
    validate_ocel_referential_integrity,
)
from autofde_lab.hub.domain.gym_procedure.level4_crown_runner import (
    CrownAttempt,
    CrownRun,
    freeze_crown,
    load_crown,
    verify_manifest,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    RealBlindEnvironment,
    skip_reason,
)
from autofde_lab.hub.domain.gym_procedure.planner_federation import PlannerAttempt
from autofde_lab.hub.domain.gym_procedure.typed_induction import (
    induce_typed_domain,
    search_plan_typed,
    validate_plan_typed,
)

_SKIP = skip_reason()
requires_gymact = pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")

TARGET = 3


def _counter_goal(state: dict) -> bool:
    """The REAL goal: the metric dimension reaches the target. Evaluated on
    simulated typed values, never on an add-list atom."""
    return state.get("counter") == state.get("target")


# --------------------------------------------------------------------------
# Real probe sequence -- the single shared real-world input for the model
# soundness properties. Three real increments against the live provider.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_probe_records(tmp_path_factory) -> list[dict]:
    if _SKIP is not None:
        pytest.skip(_SKIP)
    evdir = tmp_path_factory.mktemp("dod_probes")
    env = RealBlindEnvironment("cube_counter", {"target": TARGET}, evdir / "discovery")
    return [env.try_action("increment") for _ in range(TARGET)]


@pytest.fixture(scope="module")
def typed_domain(real_probe_records):
    return induce_typed_domain(real_probe_records)


@pytest.fixture(scope="module")
def real_initial(real_probe_records) -> dict:
    return dict(real_probe_records[0]["observed_pre"])


# ==========================================================================
# MODEL SOUNDNESS
# ==========================================================================


@requires_gymact
def test_1_metric_dimension_is_learned_as_a_relative_delta(typed_domain):
    """Property: a metric dimension's transition is learned RELATIVE (+1),
    not as an absolute add-list fact."""
    effect = typed_domain.actions["increment"].effects["counter"]
    assert effect.delta == 1.0, effect.describe()
    assert effect.context_dependent is False
    assert effect.absolute_value is None, "a metric effect must not be an absolute fact"
    assert effect.observations == TARGET


@requires_gymact
def test_2_context_dependent_dimension_is_refused_not_claimed(typed_domain):
    """Property: `solved` is derived from counter==target, so no action may
    claim it unconditionally."""
    solved = typed_domain.actions["increment"].effects["solved"]
    assert solved.context_dependent is True, solved.describe()
    assert solved.absolute_value is None
    assert solved.delta is None
    assert "solved" in typed_domain.derived_dimensions()
    assert "solved" in typed_domain.actions["increment"].context_dependent_dimensions()

    # And it is genuinely NOT applied: one increment from the real initial
    # state leaves `solved` exactly as observed, never flipped to True.
    stepped = typed_domain.actions["increment"].apply({"counter": 0, "target": TARGET, "solved": False})
    assert stepped["counter"] == 1
    assert stepped["solved"] is False


@requires_gymact
def test_3_regression_guard_one_step_plan_is_rejected_three_step_accepted(
    typed_domain, real_initial
):
    """REGRESSION GUARD for the reproduced unsoundness: the old add-list
    union made a single `increment` establish `solved=True`, so a 1-step plan
    validated for a 3-step goal and 30 planners agreed on it."""
    ok, final, reason = validate_plan_typed(
        typed_domain, real_initial, ("increment",), _counter_goal
    )
    assert ok is False
    assert reason == "GOAL_NOT_REACHED_UNDER_TYPED_MODEL", reason
    assert final["counter"] == 1, final

    ok3, final3, reason3 = validate_plan_typed(
        typed_domain, real_initial, ("increment",) * TARGET, _counter_goal
    )
    assert ok3 is True, reason3
    assert reason3 == "VALID"
    assert final3["counter"] == TARGET, final3

    # The typed searcher independently arrives at the same length.
    found = search_plan_typed(typed_domain, real_initial, _counter_goal, max_len=8)
    assert found == ("increment",) * TARGET, found


# ==========================================================================
# DISCOVERY IS BLIND
# ==========================================================================


@requires_gymact
def test_4_discovery_surface_exposes_action_names_only(tmp_path: Path):
    """Property: nothing reachable through the discovery interface carries
    precondition, effect, or cost semantics -- only names and observations."""
    env = RealBlindEnvironment("cube_counter", {"target": TARGET}, tmp_path / "blind")
    actions = env.available_actions()
    assert all(isinstance(a, str) for a in actions), actions
    assert "increment" in actions

    record = env.try_action("increment")
    leaked = [
        k
        for k in record
        if any(t in k.lower() for t in ("precond", "effect", "cost", "goal", "capabilit"))
    ]
    assert leaked == [], f"discovery leaked declared semantics: {leaked}"
    # What IS returned is observation only -- real typed pre/post state.
    assert set(record["observed_pre"]) == {"counter", "target", "reward", "solved"}
    assert record["observed_pre"]["counter"] == 0
    assert record["observed_post"]["counter"] == 1


# ==========================================================================
# EVIDENCE IS INTRINSIC
# ==========================================================================


@requires_gymact
def test_5_every_probe_attempted_is_durably_recorded(tmp_path: Path):
    """Property: the on-disk probe log has exactly one record per attempt,
    in order, matching what was attempted."""
    evdir = tmp_path / "evidence"
    env = RealBlindEnvironment("cube_counter", {"target": TARGET}, evdir)
    attempted = ["increment", "increment", "decrement", "increment"]
    for action in attempted:
        env.try_action(action)

    lines = (evdir / "probes.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(attempted), lines
    recorded = [json.loads(line)["action"] for line in lines]
    assert recorded == attempted


# ==========================================================================
# INDEPENDENT VERIFICATION
# ==========================================================================


@requires_gymact
def test_6_partial_plan_does_not_produce_goal_attainment(tmp_path: Path):
    """Property: the solver cannot self-certify goal attainment. A single
    increment toward target 3 leaves the REAL world short of the goal."""
    validated = ValidatedPlan(plan=("increment",), model_digest="dod-partial")
    commitment = commit(validated, "dod-partial-trial")
    result = commit_and_execute(
        commitment,
        "cube_counter",
        {"target": TARGET},
        {"counter": 1},  # the honest predicted consequence of ONE increment
        tmp_path / "actuation",
    )
    final_state = result["final_state"]
    assert final_state["counter"] == 1, final_state
    assert final_state["solved"] is False, final_state
    # The real goal was NOT attained, whatever the step-level verifier says.
    assert final_state["counter"] != TARGET
    assert not _counter_goal(final_state)


# ==========================================================================
# AUTHORITY
# ==========================================================================


@pytest.mark.parametrize(
    "advisory",
    [
        ("increment", "increment", "increment"),
        PlannerAttempt(
            planner_identity="Astar",
            representation="recipe",
            problem_digest="deadbeef",
            outcome="PLAN_CANDIDATE",
            candidate_plan=("increment",),
        ),
        AdvisoryCritique(
            ranked_candidates=(("Astar", ("increment",), 10.0),),
            disagreement_detected=False,
            information_deficit=None,
            rationale="advisory only",
            source="deterministic",
        ),
    ],
    ids=["raw_tuple", "planner_attempt", "advisory_critique"],
)
def test_7_advisory_output_cannot_actuate(advisory, tmp_path: Path):
    """Property: only a PowlCommitment bears actuation authority."""
    assert not isinstance(advisory, PowlCommitment)
    with pytest.raises(AdvisoryAuthorityRefused) as excinfo:
        commit_and_execute(
            advisory, "cube_counter", {"target": TARGET}, {"counter": TARGET}, tmp_path / "act"
        )
    assert "ADVISORY_AUTHORITY_USED_AS_BEARER" in str(excinfo.value)
    assert not (tmp_path / "act" / "receipts.sqlite3").exists()


# ==========================================================================
# DENOMINATOR INTEGRITY (anti-cheating law)
# ==========================================================================


def _config_for(seed: int, provider: str) -> dict:
    return {"target": 3, "seed": seed, "provider": provider}


def test_8_freeze_refuses_a_denominator_below_ten(tmp_path: Path):
    with pytest.raises(ValueError) as excinfo:
        freeze_crown(9, ["cube_counter"], _config_for, tmp_path / "m.json")
    assert "CROWN_DENOMINATOR_TOO_SMALL" in str(excinfo.value)
    assert not (tmp_path / "m.json").exists()


def test_9_freeze_refuses_to_overwrite_an_existing_manifest(tmp_path: Path):
    manifest = tmp_path / "m.json"
    first = freeze_crown(10, ["cube_counter"], _config_for, manifest)
    with pytest.raises(FileExistsError) as excinfo:
        freeze_crown(10, ["cube_counter"], _config_for, manifest)
    assert "CROWN_MANIFEST_EXISTS" in str(excinfo.value)
    # The original denominator survives the refused re-freeze untouched.
    assert load_crown(manifest).seeds == first.seeds


def test_10_load_detects_a_tampered_manifest(tmp_path: Path):
    manifest = tmp_path / "m.json"
    freeze_crown(10, ["cube_counter"], _config_for, manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["seeds"][0] = 1  # swap in an easier seed, keep the recorded digest
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_crown(manifest)
    assert "CROWN_MANIFEST_TAMPERED" in str(excinfo.value)


def test_11_verify_manifest_flags_suppressed_trials_and_denominator_change(tmp_path: Path):
    crown = freeze_crown(10, ["cube_counter"], _config_for, tmp_path / "m.json")
    assert verify_manifest(crown, list(crown.seeds)) == []

    violations = verify_manifest(crown, list(crown.seeds[:8]))
    assert any(v.startswith("SUPPRESSED_TRIAL:") for v in violations), violations
    assert any(v.startswith("DENOMINATOR_CHANGED:") for v in violations), violations
    assert "frozen=10,executed=8" in " ".join(violations)


def test_12_crown_run_retains_every_attempt_in_order(tmp_path: Path):
    crown = freeze_crown(10, ["cube_counter"], _config_for, tmp_path / "m.json")
    run = CrownRun(crown=crown)

    def _results(n_alive: int) -> list[dict]:
        # A row must carry EVERY factor of the conjunction to score ALIVE.
        # This helper originally set only `independently_verified`, which
        # passed when the scoreboard treated a missing key as satisfied --
        # exactly the absence-equals-success defect `_row_is_alive` now
        # refuses. Rows are therefore built complete, and the alive/dead
        # distinction is carried by `real_goal_attained`, the factor that
        # actually reflects the real world.
        return [
            {
                "seed": s,
                "real_goal_attained": i < n_alive,
                "independently_verified": True,
                "ocel_valid": True,
                "replay_ran": True,
                "replay_valid": True,
                "ocel_ref_violations": [],
                "replay_mismatches": [],
            }
            for i, s in enumerate(crown.seeds)
        ]

    run.record(CrownAttempt(attempt_index=1, results=_results(8), repair_note="typed induction"))
    assert run.is_complete() is False
    run.record(CrownAttempt(attempt_index=2, results=_results(10)))
    assert run.is_complete() is True

    history = run.full_history()
    assert len(history) == 2, history
    assert history[0].startswith("attempt 1: 8/10 ALIVE")
    assert "typed induction" in history[0]
    assert history[1].startswith("attempt 2: 10/10 ALIVE")
    # The 8/10 is not erased by the later success.
    assert run.attempts[0].alive_count() == 8


# ==========================================================================
# EVIDENCE INTEGRITY
# ==========================================================================


def test_13a_dangling_ocel_object_reference_is_flagged():
    log = {
        "objectTypes": [{"name": "episode"}],
        "eventTypes": [{"name": "actuation"}],
        "objects": [{"id": "ep-1", "type": "episode"}],
        "events": [
            {
                "id": "ev-1",
                "type": "actuation",
                "relationships": [{"objectId": "ep-GONE", "qualifier": "subject"}],
            }
        ],
    }
    violations = validate_ocel_referential_integrity(log)
    assert any(v.startswith("DANGLING_OBJECT_REFERENCE:") for v in violations), violations
    assert "ep-GONE" in " ".join(violations)


@requires_gymact
def test_13b_real_ocel_log_has_zero_referential_violations(tmp_path: Path):
    validated = ValidatedPlan(plan=("increment",) * TARGET, model_digest="dod-ocel")
    commitment = commit(validated, "dod-ocel-trial")
    result = commit_and_execute(
        commitment,
        "cube_counter",
        {"target": TARGET},
        {"counter": TARGET, "solved": True},
        tmp_path / "actuation",
    )
    assert result["n_receipts"] > 0
    assert validate_ocel_referential_integrity(result["ocel"]) == []
    # And the log actually hit disk as evidence.
    on_disk = json.loads((tmp_path / "actuation" / "episode.ocel.json").read_text())
    assert validate_ocel_referential_integrity(on_disk) == []


def test_14_zero_step_plan_law(tmp_path: Path):
    """Property: an empty plan is accepted only when the goal already holds."""
    with pytest.raises(ValueError) as excinfo:
        Recipe(
            gym="cube_counter",
            task="empty-unmet",
            source_ref="test",
            initial_facts=frozenset({"counter=0"}),
            goal_facts=frozenset({"counter=3"}),
            steps=(),
        )
    assert "no steps" in str(excinfo.value)

    accepted = Recipe(
        gym="cube_counter",
        task="empty-satisfied",
        source_ref="test",
        initial_facts=frozenset({"counter=0", "solved=True"}),
        goal_facts=frozenset({"solved=True"}),
        steps=(),
    )
    assert accepted.steps == ()
    assert accepted.goal_facts <= accepted.initial_facts


# ---------------------------------------------------------------------------
# Defect 0 falsifiers: REPLAY was scored as satisfied without ever being
# verified. Each test below pins one of the three independent mechanisms that
# let an unverified replay read as green, plus the OCEL gate that was computed
# and then omitted from the verdict entirely.
# ---------------------------------------------------------------------------


def _complete_row(**overrides) -> dict:
    row = {
        "seed": 1,
        "real_goal_attained": True,
        "independently_verified": True,
        "ocel_valid": True,
        "replay_ran": True,
        "replay_valid": True,
        "ocel_ref_violations": [],
        "replay_mismatches": [],
    }
    row.update(overrides)
    return row


def test_f0a_row_missing_replay_evidence_entirely_is_not_alive():
    """A row that never wrote replay fields must NOT score ALIVE.

    Before the fix this row scored ALIVE: `not row.get("replay_mismatches")`
    is true for a missing key, so a trial with no replay evidence at all was
    indistinguishable from one whose replay verified.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_crown_runner import _row_is_alive

    bare = {"seed": 1, "real_goal_attained": True, "independently_verified": True}
    assert _row_is_alive(bare) is False
    assert _row_is_alive(_complete_row()) is True


def test_f0b_replay_that_did_not_run_is_not_alive():
    """An exception in the replay path must be a FAILED factor, not a silent pass."""
    from autofde_lab.hub.domain.gym_procedure.level4_crown_runner import _row_is_alive

    did_not_run = _complete_row(
        replay_ran=False,
        replay_valid=False,
        replay_mismatches=["REPLAY_DID_NOT_RUN:RuntimeError"],
    )
    assert _row_is_alive(did_not_run) is False


def test_f0c_replay_report_invalid_is_not_alive():
    """`ReplayReport.valid is False` must fail even with an empty mismatch tuple.

    The old code read `rep.admitted`, a field that does not exist on gymact's
    ReplayReport, so the real verdict (`rep.valid`) was never consulted at all.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_crown_runner import _row_is_alive

    assert _row_is_alive(_complete_row(replay_valid=False)) is False


def test_f0d_invalid_ocel_is_not_alive_even_with_clean_referential_integrity():
    """`ocel_valid` was computed fail-closed and then left OUT of the verdict."""
    from autofde_lab.hub.domain.gym_procedure.level4_crown_runner import _row_is_alive

    assert _row_is_alive(_complete_row(ocel_valid=False)) is False


def test_f0e_replay_report_has_no_admitted_field_upstream():
    """Pins the upstream fact that made the bug possible, so it cannot silently
    change back: gymact's ReplayReport exposes `valid`, never `admitted`."""
    import subprocess

    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import GYMACT_VENV_PYTHON

    out = subprocess.run(
        [
            str(GYMACT_VENV_PYTHON),
            "-c",
            "from gymact.replay import ReplayReport; "
            "print(sorted(ReplayReport.model_fields))",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    fields = out.stdout.strip()
    assert "'valid'" in fields, fields
    assert "'admitted'" not in fields, (
        f"gymact's ReplayReport now has an `admitted` field ({fields}); the crown "
        f"reads `valid` -- reconcile before trusting either."
    )
