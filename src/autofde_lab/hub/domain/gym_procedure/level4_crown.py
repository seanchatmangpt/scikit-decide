# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The Level 4 crown loop, end to end.

The full architecture, not a collapse back to discover->Recipe->A*->act:

    probe
    -> DiscoveredDomain_n (typed dimensions preserved)
    -> representation projections (each may return UNREPRESENTABLE)
    -> planner federation (every AVAILABLE+SUPPORTED planner, bounded)
    -> candidate/disagreement set
    -> advisory critique (DSPy where configured; deterministic fallback)
    -> information deficit
    -> discriminating probe
    -> DiscoveredDomain_n+1
    -> independently valid plan
    -> POWL commitment
    -> execute_verified (real GymAct, real independent postcondition)
    -> independent consequence observation
    -> OCEL + receipt + replay
    -> standing

Authority law enforced by construction here: nothing in the advisory layer
(DSPy, planner candidates, ranking) can reach actuation. Actuation is
reached only via `commit_and_execute`, which requires a `PowlCommitment`
that can only be produced by `commit()` after `independently_validate()`
passed. Passing a raw planner candidate to `commit_and_execute` is a typed
refusal: ADVISORY_AUTHORITY_USED_AS_BEARER.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass, field
from dataclasses import fields as dataclasses_fields
from pathlib import Path
from typing import Any, Optional

from autofde_lab.hub.domain.gym_procedure.crown_evidence import (
    GOAL_CONSEQUENCE_EVENT_TYPE,
    BlockedEvidence,
    ConformantButGoalUnmetEvidence,
    Level4AliveEvidence,
    RefusedEvidence,
    Standing,
    UnknownEvidence,
    UnsupportedEvidence,
    standing_from_episode,
    standing_to_dict,
)
from autofde_lab.hub.domain.gym_procedure.discovered_domain import (
    DiscoveredDomain,
    DiscoveredProblem,
    induce_discovered_domain,
    project_to_recipe,
    propose_discriminating_probe,
)
from autofde_lab.hub.domain.gym_procedure.gym_procedure import Recipe, Step
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    GYMACT,
    GYMACT_VENV_PYTHON,
    RealBlindEnvironment,
    skip_reason,
)
from autofde_lab.hub.domain.gym_procedure.planner_federation import (
    CommonCandidateSet,
    PlannerAttempt,
    UngovernedCandidateRefused,
    classify_registered_solvers,
    recipe_problem_digest,
    run_federation,
    run_typed_search_attempt,
    select_governed_candidate,
)
from autofde_lab.hub.domain.gym_procedure.state_typing import (
    ProjectionResult,
    classify_observation,
    propositionalize,
)
from autofde_lab.hub.domain.gym_procedure.typed_induction import (
    TypedDomain,
    induce_typed_domain,
    validate_plan_typed,
)


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _standing_from_bridge_result(result: dict, replay_rec: dict, expected_list: list) -> Standing:
    """The real construction point for a live `Standing`, on the parent-
    process side of the `_EXECUTE_SCRIPT` subprocess boundary.

    `result` carries the real OCEL log and the real receipts/replay report,
    round-tripped as their own real pydantic JSON by the subprocess (see
    `_EXECUTE_SCRIPT`'s `receipts_json`/`operations_json`/`replay` keys).
    Reconstructs real `Receipt` and `ReplayReport` objects via
    `model_validate` -- never re-derived or approximated -- and calls the
    ONE real constructor, `standing_from_episode`, with them.
    """
    from gymact.models import Operation, Receipt
    from gymact.replay import ReplayMode, ReplayReport

    receipts = [Receipt.model_validate(r) for r in result["receipts_json"]]
    operations = [Operation(o) for o in result["operations_json"]]
    replay_payload = dict(replay_rec)
    replay_mode = ReplayMode(replay_payload.pop("mode"))
    replay = ReplayReport(
        mode=replay_mode,
        valid=bool(replay_payload["valid"]),
        record_count=int(replay_payload["record_count"] or 0),
        head_digest=replay_payload["head_digest"],
        mismatches=tuple(str(m) for m in (replay_payload["mismatches"] or [])),
    )
    postcondition_ref = f"final_expected_postcondition:{json.dumps(expected_list, sort_keys=True)}"
    return standing_from_episode(
        result["ocel"],
        operations,
        receipts,
        replay=replay,
        postcondition_ref=postcondition_ref,
    )


# --------------------------------------------------------------------------
# Advisory layer -- SELECT/CONSTRUCT only, never DO
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvisoryCritique:
    """Advisory output. Carries NO authority. Consumed only by validation."""

    ranked_candidates: tuple[tuple[str, tuple[str, ...], float], ...]  # (planner, plan, score)
    disagreement_detected: bool
    information_deficit: Optional[str]
    rationale: str
    source: str  # "dspy" | "deterministic"


def _dspy_preferred_plan(
    lm: Any, candidates: list[tuple[str, tuple[str, ...]]]
) -> Optional[tuple[str, ...]]:
    """Make ONE real LM call and return the plan it picked, or None.

    Returns None -- and the caller then reports ``source="deterministic"`` --
    on any of: dspy missing, the call raising, an unparseable reply, or a
    reply that does not name a plan present in the REAL candidate set. The
    last case is the load-bearing one: a model that hallucinates a plan has
    contributed nothing, and labelling the output "dspy" because a call was
    attempted is the same absence-equals-success error this module keeps
    finding elsewhere.
    """
    if lm is None or not candidates:
        return None
    try:
        import dspy
    except Exception:  # noqa: BLE001
        return None

    numbered = {str(i + 1): plan for i, (_, plan) in enumerate(candidates)}
    listing = "\n".join(f"{i}. {' -> '.join(p) or '(empty plan)'}" for i, p in numbered.items())

    class _RankPlans(dspy.Signature):
        """Choose the single most plausible plan from a numbered list of
        candidate plans produced by independent planners. Reply with only
        the number of the chosen plan."""

        candidate_plans: str = dspy.InputField(desc="numbered candidate plans, one per line")
        choice: str = dspy.OutputField(desc="the number of the chosen plan, digits only")

    try:
        with dspy.context(lm=lm):
            prediction = dspy.Predict(_RankPlans)(candidate_plans=listing)
        raw = str(getattr(prediction, "choice", "")).strip()
    except Exception:  # noqa: BLE001
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    chosen = numbered.get(digits)
    if chosen is None:
        return None
    # VALIDATE AGAINST THE REAL CANDIDATE SET, not just against the index.
    if chosen not in {plan for _, plan in candidates}:
        return None
    return chosen


def critique_candidates(
    attempts: list[PlannerAttempt],
    domain: DiscoveredDomain,
    lm: Any = None,
) -> AdvisoryCritique:
    """Rank candidate plans and detect disagreement.

    `lm` is an EXPLICIT dependency, defaulting to None (deterministic).
    It previously sniffed ``dspy.settings.lm`` and set ``source="dspy"``
    whenever anything anywhere in the process had configured a global LM --
    then ranked deterministically regardless, making zero LM calls. Every
    trial in all three frozen attempts carried ``source="dspy"`` on the
    strength of an import, not a call. The label now follows a real call
    whose output validated against the real candidate set; anything else is
    ``"deterministic"``.

    Either way the output is advisory -- the distinction changes ranking
    quality, never authority.
    """
    candidates = [(a.planner_identity, a.candidate_plan) for a in attempts if a.outcome == "PLAN_CANDIDATE"]
    distinct_plans = {tuple(p) for _, p in candidates}
    disagreement = len(distinct_plans) > 1

    preferred = _dspy_preferred_plan(lm, [(p, tuple(c)) for p, c in candidates])
    source = "dspy" if preferred is not None else "deterministic"

    # Ranking signal: shorter plans, corroborated by more independent
    # planners, over a model with fewer unresolved actions.
    plan_votes: dict[tuple[str, ...], int] = {}
    for _, plan in candidates:
        plan_votes[tuple(plan)] = plan_votes.get(tuple(plan), 0) + 1
    ranked = []
    for planner, plan in candidates:
        votes = plan_votes[tuple(plan)]
        score = votes * 10.0 - len(plan)
        if preferred is not None and tuple(plan) == preferred:
            score += 100.0  # advisory preference: ranking only, never authority
        ranked.append((planner, tuple(plan), score))
    ranked.sort(key=lambda t: -t[2])

    deficit = None
    if disagreement:
        unresolved = [a.id for a in domain.actions.values() if a.unresolved_semantics]
        if unresolved:
            deficit = f"planner disagreement over {len(distinct_plans)} distinct plans; unresolved action semantics: {sorted(unresolved)}"
        else:
            deficit = f"planner disagreement over {len(distinct_plans)} distinct plans with no unresolved action semantics (likely cost-tie, not a model gap)"

    return AdvisoryCritique(
        ranked_candidates=tuple(ranked),
        disagreement_detected=disagreement,
        information_deficit=deficit,
        rationale=f"{len(candidates)} candidates from {len({p for p,_ in candidates})} planners; {len(distinct_plans)} distinct plans",
        source=source,
    )


# --------------------------------------------------------------------------
# Independent validation + commitment boundary
# --------------------------------------------------------------------------


class AdvisoryAuthorityRefused(Exception):
    """Raised when advisory output is used where a bearer commitment is required."""


class ActuationMaterializeRefused(Exception):
    """Raised when `_EXECUTE_SCRIPT`'s `gym.materialize()` call is refused at
    the actuation stage -- distinct from a genuine subprocess crash.

    Named the exact real condition this repairs: a real trial against
    `cube_container_counter` reached commitment (discovery and typed search
    both succeeded), then the actuation subprocess crashed with
    `AttributeError: 'NoneType' object has no attribute 'episode_id'` because
    `_EXECUTE_SCRIPT` accessed `m.episode.episode_id` without checking
    `m.accepted` first -- unlike `_BRIDGE_SCRIPT`'s discovery-side
    materialize call, which does check. Root cause was a real, external
    condition (the local colima Docker daemon became unreachable between an
    earlier `docker info` check and this actuation attempt), but the bridge
    should surface a typed refusal for that either way, never crash while
    reporting it: `ProviderRefusal != BridgeCrash`.
    """


@dataclass(frozen=True)
class ValidatedPlan:
    """Only producible by `independently_validate`. Not enough to actuate."""

    plan: tuple[str, ...]
    model_digest: str
    validated_against: str = "DiscoveredDomain"


@dataclass(frozen=True)
class PowlCommitment:
    """The bearer object. Only producible by `commit()` from a ValidatedPlan."""

    plan: tuple[str, ...]
    model_digest: str
    plan_digest: str
    trial_id: str
    turtle: str


def independently_validate(plan: tuple[str, ...], domain: DiscoveredDomain, problem: DiscoveredProblem) -> Optional[ValidatedPlan]:
    """Re-execute the candidate against the DISCOVERED model's own transition
    rule -- not the solver's internal search, and not the solver's claim.
    Catches representation loss inside a projection."""
    state = set(problem.initial_state)
    for action_id in plan:
        act = domain.actions.get(action_id)
        if act is None:
            return None
        if not act.preconditions <= state:
            return None
        state = (state - set(act.negative_effects)) | set(act.positive_effects)
    if not problem.goal <= state:
        return None
    return ValidatedPlan(plan=tuple(plan), model_digest=_digest({k: sorted(v.preconditions) for k, v in domain.actions.items()}))


def commit(validated: ValidatedPlan, trial_id: str) -> PowlCommitment:
    """Cross the commitment boundary. Bounded POWL: a real Turtle record
    binding plan digest + model digest + trial identity. This is NOT a
    claim that anything executes POWL workflow semantics -- it is the
    commitment edge only."""
    plan_digest = _digest(list(validated.plan))
    turtle = (
        "@prefix powl: <urn:powl:> .\n"
        f"<urn:trial:{trial_id}> a powl:Commitment ;\n"
        f'    powl:planDigest "{plan_digest}" ;\n'
        f'    powl:modelDigest "{validated.model_digest}" ;\n'
        f'    powl:planLength {len(validated.plan)} ;\n'
        f'    powl:sequence ({" ".join(chr(34) + a + chr(34) for a in validated.plan)}) .\n'
    )
    return PowlCommitment(
        plan=validated.plan,
        model_digest=validated.model_digest,
        plan_digest=plan_digest,
        trial_id=trial_id,
        turtle=turtle,
    )


# --------------------------------------------------------------------------
# Actuation -- ONLY reachable with a PowlCommitment
# --------------------------------------------------------------------------

_EXECUTE_SCRIPT = '''
_AUTHORITY_REF = "urn:autofde-lab:level4-crown-authority"
_GOAL_CONSEQUENCE_EVENT_TYPE = "verify_goal_consequence"
import asyncio, datetime, hashlib, importlib, inspect, json, sys


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _construct_provider(provider_cls, provider_name):
    # See level4_gymact_bridge.py's _BRIDGE_SCRIPT copy of this same helper
    # (kept identical in both scripts deliberately -- the discovery and
    # actuation bridges construct providers the same way): generic
    # introspection of the real constructor signature, never a
    # per-provider-name branch, so a provider needing one real required
    # argument matching its own registered name (e.g.
    # VendorBenchmarkProvider's `name: str`) constructs correctly alongside
    # every zero-arg provider without editing this bridge again.
    required = [
        p for n, p in inspect.signature(provider_cls.__init__).parameters.items()
        if n != "self"
        and p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.KEYWORD_ONLY)
    ]
    if not required:
        return provider_cls()
    return provider_cls(provider_name)


async def main(module_path, class_name, provider_name, config, plan, expected_list, payloads, ledger_path):
    from gymact import AllowListAuthorityResolver, GymAct, MaterializationIntent
    from gymact.models import ActuationIntent
    from gymact.crown_runtime import execute_verified
    from gymact.sqlite_ledger import SQLiteReceiptLedger
    from gymact.ocel import receipts_to_ocel, validate_ocel_log, digest_ocel_log
    from gymact.replay import replay_ledger, ReplayExpectation, ReplayMode

    provider_cls = getattr(importlib.import_module(module_path), class_name)
    ledger = SQLiteReceiptLedger(ledger_path)
    # Authority must be exercised on the ACTUATION path, not only during
    # discovery. Measured defect: the resolver was wired into the discovery
    # bridge alone, and discovery writes no ledger while actuation writes the
    # ledger but passed no authority_ref -- so `authority_ref` and
    # `authority_evidence_ref` were NULL in 100% of receipts across every
    # ledger on disk. The receipt schema already has both columns; nothing
    # was populating them, so the authority factor had no durable evidence
    # behind it at all.
    gym = GymAct(
        receipt_ledger=ledger,
        authority_resolver=AllowListAuthorityResolver({_AUTHORITY_REF}),
    )
    gym.register_provider(_construct_provider(provider_cls, provider_name))

    # See _BRIDGE_SCRIPT's identical fix (level4_gymact_bridge.py): every
    # MaterializationIntent, not only every ActuationIntent, needs a real
    # admitted authority_ref -- providers whose materialization_requires_
    # authority is True refuse before capabilities() is ever reached
    # otherwise. Same real bounded resolver, same real ref, exercised at
    # both transitions.
    m = await gym.materialize(
        MaterializationIntent(provider=provider_name, config=config, authority_ref=_AUTHORITY_REF)
    )
    if not m.accepted or m.episode is None:
        # A refused actuation-time materialize is a typed answer, never a
        # crash while reporting it -- the same convention the discovery
        # bridge (`_BRIDGE_SCRIPT`) already uses for the identical case.
        # `commit_and_execute` interprets this key and raises
        # `ActuationMaterializeRefused` rather than letting the caller see a
        # bare non-zero exit / `AttributeError`.
        return {
            "materialize_failed": True,
            "reason": m.receipt.reason if m.receipt else "UNKNOWN_MATERIALIZE_REFUSAL",
        }
    episode_id = m.episode.episode_id

    probe_provider = _construct_provider(provider_cls, provider_name)
    probe_env = await probe_provider.materialize(scenario=None, config=config)
    caps = {c.binding: c for c in probe_env.capabilities()}
    await probe_env.teardown()

    transitions = []
    for i, binding in enumerate(plan):
        cap = caps[binding]
        step_expected = expected_list[i]
        intent = ActuationIntent(episode_id=episode_id, capability=cap.iri, payload=payloads[i], authority_ref=_AUTHORITY_REF)
        vt = await execute_verified(gym, intent, step_expected)
        receipt_standing = (
            vt.receipt.standing.value
            if hasattr(vt.receipt.standing, "value")
            else str(vt.receipt.standing)
        )
        reason = vt.receipt.reason

        # PROVIDER APPLICABILITY IS PART OF THE REAL OUTCOME.
        #
        # gymact's kernel never reads the `applicable` flag the provider
        # returns from `actuate()` (grep: `applicable` appears nowhere in
        # src/gymact/kernel.py). An inapplicable actuation therefore comes
        # back accepted=True, standing=ALIVE, with the world unchanged --
        # and if the model's expectation for that step happens to have
        # dropped the very dimension the action failed to move, verification
        # passes too. Measured: resource-flow recorded ["ALIVE","ALIVE"] for
        # a plan whose SECOND `burn_catalyst` was really refused by the
        # provider ("catalyst already burned", output stayed 2), because
        # `_predict_resource_flow` drops `output` after the first burn.
        #
        # The provider's own verdict is the ground truth about whether the
        # step did anything, so it is read here and it OVERRIDES a green
        # receipt. This can only ever turn a green red, never the reverse.
        effect = vt.actuation.effect if vt.actuation is not None else None
        applicable = None
        if isinstance(effect, dict) and "applicable" in effect:
            applicable = bool(effect["applicable"])
        standing = receipt_standing
        if applicable is False:
            standing = "REFUSED"
            reason = "PROVIDER_REPORTED_INAPPLICABLE:" + str(
                (effect or {}).get("result_text", "")
            )[:160]

        transitions.append({
            "action": binding,
            "step_index": i,
            "expected": step_expected,
            "standing": standing,
            "receipt_standing": receipt_standing,
            "provider_applicable": applicable,
            "world_changed": bool(getattr(vt.receipt, "world_changed", False)),
            "verified": vt.receipt.verified,
            "reason": reason,
        })

    final_expected = expected_list[-1] if expected_list else {}
    final = await gym.observe(episode_id)
    final_state = dict(final.state)
    verification = await gym.verify(episode_id, final_expected)
    receipts = gym.episode_receipts(episode_id)
    ocel = receipts_to_ocel(receipts)

    # Project the real, independent final-goal verification into the OCEL
    # graph as a first-class event. `gymact.ocel.receipts_to_ocel` cannot
    # carry this itself: `kernel.verify()` (called above as
    # `gym.verify(episode_id, final_expected)`) returns a real
    # `VerificationResult` but writes no `Receipt` -- only `execute_verified`
    # (used for the PER-STEP checks above, via `crown_runtime._verification_receipt`)
    # threads a verification through a receipt. The independent check of the
    # task's exact admitted goal is therefore built here, by hand, from the
    # real `verification` object already in memory -- never fabricated, never
    # a locally re-derived `final_state == expected` comparison -- so that
    # `crown_evidence.standing_from_episode`'s `_goal_consequence_from_log`
    # has a real object to find on the far side of the subprocess boundary.
    goal_event = {
        "id": "goal-verification:" + str(verification.verification_id),
        "type": _GOAL_CONSEQUENCE_EVENT_TYPE,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "attributes": [
            # OCEL 2.0's schema requires every event attribute `value` to be
            # a JSON string (see the vendored schema's `events.items
            # .properties.attributes.items.properties.value`), so `passed`
            # is carried as the real boolean's string form -- the same
            # convention `receipts_to_ocel` already uses for
            # `receipt.standing.value` -- not a native JSON boolean.
            {"name": "passed", "value": str(bool(verification.passed))},
            {"name": "verification_id", "value": str(verification.verification_id)},
            {"name": "state_digest", "value": str(verification.state_digest)},
            {"name": "expected_digest", "value": _digest(verification.expected)},
            {"name": "observed_digest", "value": _digest(verification.observed)},
        ],
        "relationships": [{"objectId": episode_id, "qualifier": "episode"}],
    }
    ocel["events"].append(goal_event)
    if not any(et["name"] == _GOAL_CONSEQUENCE_EVENT_TYPE for et in ocel["eventTypes"]):
        ocel["eventTypes"].append({
            "name": _GOAL_CONSEQUENCE_EVENT_TYPE,
            "attributes": [{"name": "passed", "type": "string"}],
        })

    try:
        validate_ocel_log(ocel)
        ocel_valid = True
        ocel_error = None
    except Exception as exc:
        ocel_valid = False
        ocel_error = str(exc)[:300]

    # REPLAY verification. Three real defects were found here by an adversarial
    # audit and are fixed below -- read the comments before simplifying any of
    # this, because every one of them made an unverified replay look green:
    #
    #  1. The verdict field was read as `rep.admitted`, which does NOT EXIST on
    #     gymact's ReplayReport (its fields are mode/valid/record_count/
    #     head_digest/mismatches/live_reexecution_admitted). getattr(...) with a
    #     default therefore returned None unconditionally, so the actual
    #     pass/fail verdict was never read by anything.
    #  2. On an exception the report carried only {"error": ...} with no
    #     "mismatches" key, so the caller's .get("mismatches", []) produced []
    #     and the ALIVE conjunction passed. A replay that never ran was
    #     indistinguishable from one that passed, and the error string was
    #     dropped before it could reach the durable record.
    #  3. `valid` is now an explicit part of the verdict: a replay that runs
    #     and reports valid=False must not pass merely because its mismatch
    #     tuple happens to be empty.
    replay_report: dict
    try:
        rep = replay_ledger(
            ledger,
            mode=ReplayMode.EVIDENCE_REPLAY,
            expected=ReplayExpectation(subject_ref=m.episode.environment_id),
        )
        mismatches = list(rep.mismatches or [])
        if not rep.valid:
            # Surface an invalid verdict THROUGH the mismatch channel so the
            # ALIVE conjunction sees it even if gymact reported no per-record
            # mismatch string.
            mismatches.append("REPLAY_REPORT_INVALID")
        replay_report = {
            "mode": rep.mode.value if hasattr(rep.mode, "value") else str(rep.mode),
            "ran": True,
            "valid": bool(rep.valid),
            "record_count": int(rep.record_count),
            "head_digest": rep.head_digest,
            "mismatches": mismatches,
            "error": None,
        }
    except Exception as exc:
        # Fail CLOSED: a replay that could not run is a failed factor, never a
        # silently satisfied one. `mode` is still named -- EVIDENCE_REPLAY was
        # the mode attempted, even though it never produced a report -- so the
        # parent process can still reconstruct a real (if failed) ReplayReport.
        replay_report = {
            "mode": "EVIDENCE_REPLAY",
            "ran": False,
            "valid": False,
            "record_count": 0,
            "head_digest": None,
            "mismatches": [f"REPLAY_DID_NOT_RUN:{type(exc).__name__}"],
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }

    await gym.teardown(episode_id)
    return {
        "episode_id": episode_id,
        "transitions": transitions,
        "final_state": final_state,
        "independently_verified": bool(verification.passed),
        "ocel": ocel,
        "ocel_valid": ocel_valid,
        "ocel_error": ocel_error,
        "ocel_digest": digest_ocel_log(ocel),
        "n_receipts": len(receipts),
        "replay": replay_report,
        # The real Receipt/Operation objects backing this episode's standing.
        # `autofde_lab` is not importable from this subprocess's interpreter
        # (it runs in ~/gymact's own .venv, not autofde-lab's), so
        # `standing_from_episode` cannot be called HERE even though this is
        # the point where the OCEL log, replay report, and receipts are all
        # simultaneously real, in-hand Python objects. They are instead
        # round-tripped as their own real pydantic JSON (`model_dump`), and
        # reconstructed as real `Receipt`/`ReplayReport` objects (via
        # `model_validate`, not re-derived or approximated) in
        # `run_real_trial`, which is the nearest point across the process
        # boundary that can actually import `crown_evidence`.
        "receipts_json": [r.model_dump(mode="json") for r in receipts],
        "operations_json": [str(r.operation.value) for r in receipts],
    }


if __name__ == "__main__":
    a = sys.argv
    out = asyncio.run(main(a[1], a[2], a[3], json.loads(a[4]), json.loads(a[5]),
                          json.loads(a[6]), json.loads(a[7]), a[8]))
    print(json.dumps(out, default=str))
'''


_COUNTER_DELTAS = {"increment": 1, "decrement": -1}


def real_goal_attained(observation: dict) -> bool:
    """THE real-world verdict, read off the provider's own observation.

    Every bounded provider in the pool publishes `solved` as a derived
    dimension it computes itself. Reading it here is not the model grading
    its own work: the model is explicitly forbidden from *claiming* `solved`
    (typed induction records it CONTEXT_DEPENDENT), so this value can only
    come from the real environment after real actuation.
    """
    # Membership check, not `.get("solved")`: an observation that never
    # published the dimension at all is a different situation from one that
    # published `False`, and the caller records the whole observation as the
    # factor's evidence so the distinction survives into the record.
    return "solved" in observation and observation["solved"] is True


def model_goal_predicate(provider_key: str, initial_observation: dict, config: dict):
    """The goal handed to planning, expressed over BASE dimensions.

    It cannot be `solved is True`: `solved` is derived, so typed induction
    refuses to claim it and no simulated plan could ever reach it -- every
    trial would report NO_TYPED_VALID_PLAN for a representational reason
    rather than a real one. Stating the goal in base terms is what a goal
    specification legitimately is; it discloses nothing about what any
    action DOES, which is what the agent must still discover.
    """
    obs = dict(initial_observation)
    if provider_key in ("cube_counter", "cube_container_counter"):
        target = obs.get("target", config.get("target"))

        def counter_goal(state: dict) -> bool:
            return target is not None and state.get("counter") == target

        return counter_goal, f"counter == target ({target})"
    if provider_key == "resource_flow":
        target = obs.get("target", config.get("target"))

        def flow_goal(state: dict) -> bool:
            output = state.get("output")
            return (
                target is not None
                and isinstance(output, (int, float))
                and output >= target
            )

        return flow_goal, f"output >= target ({target})"
    if provider_key == "switchboard":

        def board_goal(state: dict) -> bool:
            # Both sides must be PRESENT. `state.get("required_on") ==
            # state.get("required_count")` returned True when the state carried
            # neither dimension (None == None) -- a goal satisfied by a state
            # that says nothing at all.
            if "required_on" not in state or "required_count" not in state:
                return False
            return (
                state.get("master") is True
                and state["required_on"] == state["required_count"]
            )

        return board_goal, "master and required_on == required_count"
    if provider_key == "lock_and_key":
        depth = obs.get("depth", config.get("depth"))

        def lock_goal(state: dict) -> bool:
            return depth is not None and state.get("locks_open") == depth

        return lock_goal, f"locks_open == depth ({depth})"
    if provider_key == "memory":
        # `target` is a crown-layer-only config key -- MemoryEnvironment has
        # no concept of "target" at all and silently ignores it (confirmed
        # live: materialize() reads only config["initial"]/
        # config["requires_authority"]), unlike resource_flow where target
        # really is part of the provider's own domain state. Read from
        # config only, never from obs, for that reason.
        target = config.get("target")

        def memory_goal(state: dict) -> bool:
            return target is not None and state.get("counter") == target

        return memory_goal, f"counter == target ({target})"
    raise ValueError(f"UNSUPPORTED_PROVIDER_FOR_GOAL:{provider_key}")


def predict_step_postconditions(
    plan: tuple[str, ...],
    provider_key: str,
    initial_observation: dict,
    payloads: Optional[list[dict]] = None,
) -> list[dict]:
    """Predict the observation expected AFTER each action of `plan`.

    Needed because `execute_verified` verifies a postcondition after every
    single action: broadcasting one terminal expectation to every step makes
    each intermediate step REFUSED (POSTCONDITION_FAILED) even when the plan
    is executing exactly as intended. Refusing an intermediate step of a
    correct plan is a false negative, and a false REFUSED is as much a
    standing error as a false ALIVE.

    Authority note: this is a hardcoded model of the *counter providers'*
    arithmetic, deliberately independent of the discovered model and of any
    planner's claim -- that independence is what makes the postcondition a
    real check rather than the solver grading its own work. It is NOT a
    general oracle: an unknown provider raises rather than guessing.
    """
    if provider_key not in (
        "cube_counter",
        "cube_container_counter",
        "switchboard",
        "resource_flow",
        "lock_and_key",
        "memory",
    ):
        raise ValueError(
            f"UNSUPPORTED_PROVIDER_FOR_POSTCONDITION_PREDICTION:{provider_key}; "
            f"known: cube_counter, cube_container_counter, switchboard, "
            f"resource_flow, lock_and_key, memory"
        )
    if provider_key == "switchboard":
        return _predict_switchboard(plan, initial_observation)
    if provider_key == "resource_flow":
        return _predict_resource_flow(plan, initial_observation)
    if provider_key == "lock_and_key":
        return _predict_lock_and_key(plan, initial_observation)
    if provider_key == "memory":
        # MUST be an explicit branch, not left to fall through to the
        # generic _COUNTER_DELTAS tail below: that generic branch would
        # numerically coincide for `increment` (delta=1 either way) but
        # also unconditionally attaches a `solved` key MemoryEnvironment
        # never publishes (observe() returns the raw KV dict verbatim, no
        # derived dimension) -- causing every step to spuriously fail
        # POSTCONDITION_FAILED. Real, precisely-named wiring hazard caught
        # by design review before this was ever wired; see
        # docs/2026-08-08-level4-gym-census-round2.md's memory design.
        return _predict_memory(plan, initial_observation)
    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import decode_action

    payloads = payloads or [{} for _ in plan]
    counter = int(initial_observation.get("counter", 0))
    target = initial_observation.get("target")
    out: list[dict] = []
    for i, action_id in enumerate(plan):
        # Plan entries are ACTION IDS; a parameterized one carries its
        # payload (`increment_by[value=1]`), so match on the binding.
        action, decoded = decode_action(action_id)
        if action in _COUNTER_DELTAS:
            counter += _COUNTER_DELTAS[action]
        elif action == "increment_by":
            step_payload = payloads[i] or decoded
            counter += int(step_payload.get("value", 0))
        else:
            raise ValueError(f"UNSUPPORTED_ACTION_FOR_POSTCONDITION_PREDICTION:{action_id}")
        step_expected: dict = {"counter": counter}
        if target is not None:
            step_expected["solved"] = counter == int(target)
        out.append(step_expected)
    return out


def _predict_switchboard(plan: tuple[str, ...], initial: dict) -> list[dict]:
    """Independent oracle for `switchboard`, written from the provider's
    declared semantics -- not from the discovered model.

    `required_on` and `solved` are deliberately NOT predicted: which switch
    indices are 'required' is seeded hidden state the environment never
    discloses, so an oracle that claimed them would be guessing. Omitting an
    unpredictable dimension narrows the check honestly; inventing a value
    for it would make the check pass for the wrong reason.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import decode_action

    n = int(initial.get("n_switches", 0))
    switches = {i: bool(initial.get(f"switch_{i}", False)) for i in range(n)}
    master = bool(initial.get("master", False))
    toggles = int(initial.get("toggles", 0))
    out: list[dict] = []
    for action_id in plan:
        binding, payload = decode_action(action_id)
        if binding == "toggle_switch":
            index = int(payload["index"])
            switches[index] = not switches[index]
            toggles += 1
        elif binding == "engage_master":
            if switches.get(0) and switches.get(1):
                master = True
        elif binding == "reset_pair":
            switches[0] = False
            switches[1] = False
        else:
            raise ValueError(f"UNSUPPORTED_ACTION_FOR_POSTCONDITION_PREDICTION:{action_id}")
        step: dict = {f"switch_{i}": v for i, v in switches.items()}
        step["master"] = master
        step["toggles"] = toggles
        out.append(step)
    return out


def _predict_resource_flow(plan: tuple[str, ...], initial: dict) -> list[dict]:
    """Independent oracle for `resource-flow`.

    `mine_rate` is observable, so mining is predictable. The catalyst bonus
    is NOT observable, so after `burn_catalyst` the `output` pool becomes
    unpredictable and is dropped from every later expectation (as is
    `solved`, which depends on it). Everything still predictable stays
    checked.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import decode_action

    capacity = int(initial.get("capacity", 0))
    target = initial.get("target")
    rate = int(initial.get("mine_rate", 1))
    raw = int(initial.get("raw", 0))
    refined = int(initial.get("refined", 0))
    output = int(initial.get("output", 0))
    catalyst = bool(initial.get("catalyst", True))
    output_known = True
    out: list[dict] = []
    for action_id in plan:
        binding, _ = decode_action(action_id)
        if binding == "mine":
            raw = min(capacity, raw + rate)
        elif binding == "refine":
            raw -= 1
            refined += 1
        elif binding == "assemble":
            refined -= 1
            output += 1
        elif binding == "burn_catalyst":
            catalyst = False
            output_known = False  # bonus is hidden seeded state
        else:
            raise ValueError(f"UNSUPPORTED_ACTION_FOR_POSTCONDITION_PREDICTION:{action_id}")
        step: dict = {"raw": raw, "refined": refined, "catalyst": catalyst}
        if output_known:
            step["output"] = output
            if target is not None:
                step["solved"] = output >= int(target)
        out.append(step)
    return out


def _predict_lock_and_key(plan: tuple[str, ...], initial: dict) -> list[dict]:
    """Independent oracle for `lock-and-key`.

    Which key opens which lock is a hidden seeded permutation, so the
    success of `open_lock` cannot be predicted. The oracle predicts the
    consequence of a SUCCESSFUL open (the key is consumed, so
    `holding_key` becomes False and `locks_open` advances) -- which is
    exactly the right check: if the held key does not fit, the real
    environment refuses, `holding_key` stays True, and the step fails
    POSTCONDITION_FAILED rather than silently passing.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import decode_action

    depth = int(initial.get("depth", 0))
    locks_open = int(initial.get("locks_open", 0))
    held = int(initial.get("held_key", -1))
    jammed = bool(initial.get("rack_jammed", False))
    out: list[dict] = []
    for action_id in plan:
        binding, payload = decode_action(action_id)
        if binding == "pick_key":
            held = int(payload["key"])
        elif binding == "drop_key":
            held = -1
        elif binding == "open_lock":
            locks_open += 1
            held = -1
        elif binding == "force_latch":
            locks_open += 1
            held = -1
            jammed = True
        else:
            raise ValueError(f"UNSUPPORTED_ACTION_FOR_POSTCONDITION_PREDICTION:{action_id}")
        out.append(
            {
                "locks_open": locks_open,
                "held_key": held,
                "holding_key": held != -1,
                "rack_jammed": jammed,
                "solved": locks_open >= depth,
            }
        )
    return out


def _predict_memory(plan: tuple[str, ...], initial: dict) -> list[dict]:
    """Independent oracle for `memory`, from MemoryEnvironment.actuate's own
    increment arithmetic (gymact/providers.py:99-107) -- NOT from the
    discovered model. Never predicts `solved`: unlike cube_counter/
    resource_flow/lock_and_key, MemoryEnvironment never computes or
    publishes a derived `solved` dimension (observe() returns the raw KV
    state verbatim, gymact/providers.py:85-87) -- a predicted `solved` key
    would never match observed state and would make every step spuriously
    POSTCONDITION_FAILED. `set`/`delete` are not handled here: they are
    excluded from this migration's bounded action space entirely (see
    _ACTION_PARAMS/_STATIC_PAYLOADS design), so a plan containing one is
    impossible to construct in the first place; an unexpected binding
    raises rather than fabricating an effect for it.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import decode_action

    counter_key = "counter"
    value = initial.get(counter_key, 0)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"UNPREDICTABLE_INITIAL_VALUE_FOR_MEMORY_ORACLE:{counter_key}={value!r}")
    out: list[dict] = []
    for action_id in plan:
        binding, payload = decode_action(action_id)
        if binding != "increment" or payload.get("key") != counter_key:
            raise ValueError(f"UNSUPPORTED_ACTION_FOR_POSTCONDITION_PREDICTION:{action_id}")
        amount = payload.get("amount", 1)
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise ValueError(f"UNPREDICTABLE_AMOUNT_FOR_POSTCONDITION_PREDICTION:{action_id}")
        value += amount
        out.append({counter_key: value})
    return out


def commit_and_execute(
    commitment: Any,
    provider_key: str,
    config: dict,
    expected: Any,
    evidence_dir: Path,
    payloads: Optional[list[dict]] = None,
) -> dict:
    """The ONLY actuation path. Refuses anything that is not a real
    `PowlCommitment` -- an advisory candidate (raw plan, planner attempt,
    critique) is a typed refusal, never an implicit grant.

    `expected` is either:

    - a ``list[dict]`` of per-step postconditions, one per plan action --
      ``expected[i]`` is verified immediately after action ``i``; or
    - a single ``dict`` (backward-compatible form), which is treated as the
      expectation for the FINAL step only. Earlier steps get a plain
      predicted postcondition from `predict_step_postconditions` rather than
      the terminal one, which is what made multi-step plans report REFUSED
      on every intermediate action.
    """
    if not isinstance(commitment, PowlCommitment):
        raise AdvisoryAuthorityRefused(
            f"ADVISORY_AUTHORITY_USED_AS_BEARER: {type(commitment).__name__} is advisory "
            f"output and carries no actuation authority; only a PowlCommitment "
            f"produced by commit(independently_validate(...)) may reach actuation"
        )
    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
        _PROVIDERS,
        decode_action,
    )

    module_path, class_name, provider_name = _PROVIDERS[provider_key]
    # A committed plan is a sequence of ACTION IDS, which for a
    # parameterized capability carry their payload (`toggle_switch[index=2]`).
    # The gym only knows bindings, so decode here -- and let a decoded
    # payload supply the actuation payload when the caller passed none.
    action_ids = tuple(commitment.plan)
    decoded = [decode_action(a) for a in action_ids]
    plan = tuple(binding for binding, _ in decoded)
    if payloads is None:
        payloads = [dict(p) for _, p in decoded]
    else:
        payloads = [
            dict(supplied) if supplied else dict(inferred)
            for supplied, (_, inferred) in zip(payloads, decoded)
        ]
    if len(payloads) != len(plan):
        raise ValueError(f"payloads length {len(payloads)} != plan length {len(plan)}")

    if isinstance(expected, list):
        expected_list = [dict(e) for e in expected]
        if len(expected_list) != len(plan):
            raise ValueError(
                f"per-step expected length {len(expected_list)} != plan length {len(plan)}"
            )
    elif isinstance(expected, dict):
        expected_list = predict_step_postconditions(
            plan, provider_key, {"counter": 0, "target": config.get("target")}, payloads
        )
        if expected_list:
            expected_list[-1] = dict(expected)
    else:
        raise TypeError(f"expected must be a dict or list[dict], got {type(expected).__name__}")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    script = evidence_dir / "execute.py"
    script.write_text(_EXECUTE_SCRIPT, encoding="utf-8")
    (evidence_dir / "commitment.ttl").write_text(commitment.turtle, encoding="utf-8")
    ledger_path = evidence_dir / "receipts.sqlite3"

    completed = subprocess.run(
        [
            str(GYMACT_VENV_PYTHON), str(script), module_path, class_name, provider_name,
            json.dumps(config), json.dumps(list(plan)), json.dumps(expected_list),
            json.dumps(payloads), str(ledger_path),
        ],
        capture_output=True, text=True, cwd=str(GYMACT), timeout=300,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"execute bridge failed:\nstdout={completed.stdout}\nstderr={completed.stderr}")
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    if result.get("materialize_failed"):
        # A typed refusal from `_EXECUTE_SCRIPT`, not a crash -- surfaced as
        # a distinct exception so `run_real_trial` can report it through the
        # normal TrialReport channel (BlockedEvidence), matching the "a
        # trial that cannot be modelled is a FAILED trial with a named
        # reason, never an absent one" convention this module uses
        # everywhere else.
        raise ActuationMaterializeRefused(str(result.get("reason") or "UNKNOWN_MATERIALIZE_REFUSAL"))
    # Write the CANONICAL bytes, not a pretty-printed rendering.
    #
    # `ocel_digest` is computed by gymact's `digest_ocel_log` over
    # `json.dumps(log, sort_keys=True, separators=(",", ":"))`. Writing the
    # same log with `indent=2` produced a file that does NOT hash to the
    # digest the evidence reference cites -- measured on a real crown
    # artifact: file sha256 07fc9f2e... vs canonical 975b1778... So
    # `_ocel_ref()`'s `#ocel_digest=` pointed at a file that could not verify
    # against it, which is precisely the unverifiable evidence reference the
    # `evidence_ref` requirement exists to prevent. `sha256sum` on this file
    # now reproduces `ocel_digest`.
    (evidence_dir / "episode.ocel.json").write_text(
        json.dumps(result["ocel"], sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return result


# --------------------------------------------------------------------------
# OCEL referential integrity (the gap gymact does not close generically)
# --------------------------------------------------------------------------


def _parse_fact(fact: str) -> tuple[str, Any]:
    """Reverse the bridge's ``"name=value"`` fact encoding back to a typed
    value, so `state_typing` classifies real kinds (a float `reward` must be
    seen as CONTINUOUS, not as the string ``"0.16666"``)."""
    import ast

    name, _, raw = fact.partition("=")
    try:
        return name, ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return name, raw


def _observation_from_facts(facts: list[str]) -> dict[str, Any]:
    return dict(_parse_fact(f) for f in facts)


@dataclass(frozen=True)
class TrialReport:
    """The full, honest record of one real crown trial.

    The acceptance verdict is carried entirely by `standing` -- a single
    `crown_evidence.Standing` produced by the ONE real evidence chain,
    `standing_from_episode` (or, for a trial that never reached actuation, a
    directly-named `UnknownEvidence`/`RefusedEvidence`/`BlockedEvidence`/
    `UnsupportedEvidence`). There is no boolean ground-truth field left to
    disagree with it and no conjunction to assemble: `is_alive()`/`verdict()`
    below `match` on the real type, branchless by construction.

    `n_probes`, `n_planner_attempts`, `representation_losses`,
    `ocel_ref_violations`, `replay_mismatches` (and the other evidence-data
    fields below them) remain plain descriptive counts/records -- they
    describe what was observed, they do not themselves determine standing.
    """

    seed: int
    run_id: str
    provider: str
    n_probes: int
    n_planner_attempts: int
    planners_producing_candidates: tuple[str, ...]
    disagreement_detected: bool
    standing: Standing
    ocel_ref_violations: tuple[str, ...]
    replay_mismatches: tuple[str, ...]
    evidence_dir: str
    representation_losses: dict[str, str] = field(default_factory=dict)
    n_supported_solvers: int = 0
    committed_plan: tuple[str, ...] = ()
    discriminating_probe: Optional[str] = None
    step_standings: tuple[str, ...] = ()
    outcome: str = "UNKNOWN"
    # --- typed-model gate -------------------------------------------------
    goal_predicate_description: str = ""
    typed_derived_dimensions: tuple[str, ...] = ()
    unsound_candidates_rejected: int = 0
    committed_plan_source: str = ""
    final_state: dict = field(default_factory=dict)
    # --- descriptive replay/OCEL evidence data (not verdicts) -------------
    replay_record_count: int = 0
    replay_error: Optional[str] = None
    ocel_digest: str = ""
    replay_head_digest: Optional[str] = None

    # -- the acceptance verdict, branchless: match on the real type ---------

    def is_alive(self) -> bool:
        """The ONLY green verdict. `Level4AliveEvidence` means every real
        process check in `standing_from_episode`'s chain produced positive
        evidence AND a real, independently-observed goal-consequence event
        reported `passed=True`; every other `Standing` variant is not
        alive, including `ConformantButGoalUnmetEvidence` (clean process,
        goal absent/unmet) and `UnknownEvidence` (neither established)."""
        match self.standing:
            case Level4AliveEvidence():
                return True
            case _:
                return False

    def verdict(self) -> str:
        """`ALIVE` / `UNKNOWN` / `NOT_ALIVE`, per standing-law vocabulary.
        `RefusedEvidence` and `ConformantButGoalUnmetEvidence` are both real,
        checked negative answers (`NOT_ALIVE`, mirroring
        `CrownFactor.is_evidence()` treating `REFUSED` as evidence -- a
        clean process with a named-absent/failed goal is exactly as checked
        as an explicit refusal); `UnknownEvidence`/`BlockedEvidence`/
        `UnsupportedEvidence` are all "never established either way"
        (`UNKNOWN`, mirroring `CrownFactor.NON_EVIDENCE_STATES`)."""
        match self.standing:
            case Level4AliveEvidence():
                return "ALIVE"
            case RefusedEvidence() | ConformantButGoalUnmetEvidence():
                return "NOT_ALIVE"
            case UnknownEvidence() | BlockedEvidence() | UnsupportedEvidence():
                return "UNKNOWN"
            case _:  # pragma: no cover - exhaustive over Standing's 6 variants
                raise TypeError(f"UNHANDLED_STANDING_VARIANT:{type(self.standing).__name__}")

    def to_row(self) -> dict:
        """Scoreboard row. `standing` is serialized through
        `crown_evidence.standing_to_dict`, not `dataclasses.asdict`: its
        `Level4AliveEvidence`/`ConformantButGoalUnmetEvidence` cases nest
        real gymact pydantic models (`ConformanceResult`, `ReplayReport`)
        that `asdict` would leave un-converted rather than turn into plain,
        JSON-safe dicts."""
        row = {f.name: getattr(self, f.name) for f in dataclasses_fields(self) if f.name != "standing"}
        row["standing"] = standing_to_dict(self.standing)
        return row


def _is_metric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _changed_dims(record: dict, non_metric_only: bool = False) -> set[str]:
    pre = record.get("observed_pre") or {}
    post = record.get("observed_post") or {}
    changed = {k for k in post if pre.get(k) != post.get(k)}
    if non_metric_only:
        changed = {k for k in changed if not _is_metric(post.get(k))}
    return changed


def _discover_by_probing(env: RealBlindEnvironment, probe_budget: int) -> tuple[list[dict], int]:
    """Learn every action's effect without wrecking the episode.

    Replaces a loop that committed every applicable probe to history. That
    loop had two measured defects, both of which made `lock_and_key`
    undiscoverable:

    1. **Irreversible probes poisoned the run.** Probing `force_latch`
       jammed the key rack permanently at probe 6; every remaining probe was
       refused, so `open_lock` was never observed succeeding and the trial
       ended `NO_TYPED_VALID_PLAN`. Probes are now SPECULATIVE by default --
       really executed, really observed, then discarded.
    2. **A guarded action was never observed succeeding.** `open_lock`
       requires a held key, `refine` requires a raw token; probing each
       action alone from the baseline can never see either succeed. An
       action that stays refused is now retried behind a chained prefix
       built from actions already known to work, so `assemble` is probed
       behind `(mine, refine)` and `open_lock` behind each `pick_key[k]`.

    Exactly one action per round is committed, to advance the frontier. The
    choice prefers an action that is *measurably* safe -- one touching only
    metric dimensions, or one shown by a real self-inverse probe to undo
    itself. Only when no safe action exists does it pay for a lookahead
    sweep and keep whichever candidate leaves the most actions applicable.
    That is what stops `force_latch` from being adopted: it is measured to
    strand the episode, not guessed to be dangerous by its name.
    """
    records: list[dict] = []
    actions = env.available_actions()
    learned: set[str] = set()
    committed: set[str] = set()
    self_probed: set[str] = set()
    establisher: dict[str, tuple[str, ...]] = {}
    n = 0

    def probe(action: str, prefix: tuple[str, ...] = (), commit: bool = False) -> dict:
        nonlocal n
        record = env.try_action(action, commit=commit, prefix=prefix)
        records.append(record)
        n += 1
        if record.get("applicable"):
            learned.add(action)
        return record

    while n < probe_budget:
        sweep: dict[str, dict] = {}
        for action in actions:
            if n >= probe_budget:
                break
            sweep[action] = probe(action)

        # Chained establisher search for anything still never-applicable.
        #
        # Single-helper prefixes only reach preconditions ONE action can
        # establish. Measured on `switchboard`: `engage_master` needs
        # switches 0 AND 1 on, so every single-helper probe was refused, the
        # action was never once observed applicable, and induction had
        # nothing to model it with -- the trial ended NO_TYPED_VALID_PLAN
        # for want of an observation, not for want of a plan. Pair prefixes
        # are tried only for actions single helpers failed to establish, so
        # the extra cost is paid exactly where the evidence is missing.
        for action in actions:
            if action in learned or n >= probe_budget:
                continue
            for helper in sorted(learned):
                if n >= probe_budget:
                    break
                prefix = establisher.get(helper, ()) + (helper,)
                if action in prefix:
                    continue
                if probe(action, prefix=prefix).get("applicable"):
                    establisher[action] = prefix
                    break
        for action in actions:
            if action in learned or n >= probe_budget:
                continue
            for first in sorted(learned):
                if action in learned or n >= probe_budget:
                    break
                for second in sorted(learned):
                    if n >= probe_budget:
                        break
                    prefix = (first, second)
                    if action in prefix or first == second:
                        continue
                    if probe(action, prefix=prefix).get("applicable"):
                        establisher[action] = prefix
                        break

        # --- ACTIVELY SEEK REFUSAL EVIDENCE ------------------------------
        # An action with successes and ZERO refusals is the dangerous case:
        # the induction had no evidence to bound it with, so it was modelled
        # as unconditionally applicable with a constant effect, and BFS
        # stacked it. The probe that settles it is the action re-run from the
        # state ITS OWN EFFECT produced -- which is what reveals `force_latch`
        # jamming the rack, `toggle_switch[i]` turning the switch back off,
        # and `burn_catalyst` having spent the catalyst. That is real active
        # experimentation, not a workaround, and it costs one speculative
        # probe per action.
        #
        # It also supplies the POSITIVE evidence: an action that really is
        # repeatable (`increment`) is now seen succeeding twice from two
        # different pre-states with the same delta, which is exactly what
        # clears `repeatability_unknown`. Without this probe the sweep only
        # ever observes each action once, from one state.
        for action in actions:
            if n >= probe_budget:
                break
            if action not in learned or action in self_probed:
                continue
            self_probed.add(action)
            probe(action, prefix=establisher.get(action, ()) + (action,))

        if all(action in learned for action in actions) and self_probed >= learned:
            break  # nothing left to learn; stop before burning budget

        candidates = [
            a
            for a in actions
            if sweep.get(a, {}).get("applicable")
            and a not in committed
            and _changed_dims(sweep[a])  # an inert action advances nothing
        ]
        if not candidates or n >= probe_budget:
            break

        chosen: Optional[str] = None
        risky: list[str] = []
        for a in candidates:
            if not _changed_dims(sweep[a], non_metric_only=True):
                chosen = a  # touches only metric dimensions
                break
            if n >= probe_budget:
                break
            twice = probe(a, prefix=(a,))
            baseline = sweep[a].get("observed_pre") or {}
            after = twice.get("observed_post") or {}
            if twice.get("applicable") and all(
                after.get(d) == baseline.get(d)
                for d in baseline
                if not _is_metric(baseline.get(d))
            ):
                chosen = a  # really undoes itself
                break
            risky.append(a)

        if chosen is None:
            best_count = -1
            for a in risky:
                if n >= probe_budget:
                    break
                count = 0
                for b in actions:
                    if n >= probe_budget:
                        break
                    if probe(b, prefix=(a,)).get("applicable"):
                        count += 1
                if count > best_count:
                    best_count, chosen = count, a

        if chosen is None or n >= probe_budget:
            break
        probe(chosen, commit=True)
        committed.add(chosen)

    # --- ACTIVELY SEEK THE UNOBSERVED RELATIONAL PAIRS -------------------
    #
    # An action with a RELATIONAL precondition is known only at the joint
    # dimension values it was really observed to succeed at; every other pair
    # is UNKNOWN and `RelationalPrecondition.permits` refuses it. That is
    # sound, and on `lock_and_key` at depth 3 it is also insufficient:
    # `open_lock` was observed succeeding exactly once, at
    # ``(held_key=0, locks_open=0)``, so the model could reach `locks_open`
    # 1 and never 3 -- an honest NO_TYPED_VALID_PLAN caused by missing
    # evidence rather than by an unreachable goal.
    #
    # Missing evidence is something a discovery agent can go and get. The
    # probe that gets it is the action re-run from the state ITS OWN SUCCESS
    # produced, behind each helper in turn: `open_lock` behind
    # ``(pick_key[perm0], open_lock, pick_key[k])`` observes the second lock's
    # key, and the round repeats to observe the third. Every probe is
    # speculative, so nothing is committed; the cost is bounded by the
    # remaining budget, and if the budget runs out the outcome is the same
    # honest refusal as before -- never a guess about an unobserved pair.
    def _relationally_uncertain() -> dict[str, tuple[str, ...]]:
        typed_now = [r for r in records if "observed_pre" in r and "observed_post" in r]
        if not typed_now:
            return {}
        dom = induce_typed_domain(typed_now)
        out: dict[str, tuple[str, ...]] = {}
        for action_id, act in dom.actions.items():
            if not act.relational_preconditions:
                continue
            chain = next(
                (
                    tuple(r.get("prefix") or ())
                    for r in reversed(typed_now)
                    if r["action"] == action_id and r.get("applicable")
                ),
                None,
            )
            if chain is not None:
                out[action_id] = chain
        return out

    while n < probe_budget:
        uncertain = _relationally_uncertain()
        if not uncertain:
            break
        progressed = False
        for action, chain in sorted(uncertain.items()):
            if n >= probe_budget:
                break
            base = chain + (action,)
            for helper in sorted(learned):
                if n >= probe_budget:
                    break
                if probe(action, prefix=base + (helper,)).get("applicable"):
                    progressed = True
                    break
        if not progressed:
            break

    return records, n


def validate_federation_candidates(
    typed_domain: TypedDomain,
    typed_initial: dict,
    ranked: tuple[tuple[str, tuple[str, ...], float], ...],
    goal_predicate,
    model_digest: str = "",
) -> tuple[Optional[ValidatedPlan], str, list[dict]]:
    """Validate EVERY distinct federation candidate against the typed model.

    Extracted from `run_real_trial` so the rejection count is exercisable
    directly with real collaborators (a real `TypedDomain` from real probe
    records, real `PlannerAttempt`s) rather than only reachable through a
    full trial.

    The defect this replaces: the original loop `break`-ed on the first valid
    candidate, so `unsound_candidates_rejected` counted only the candidates
    ranked ahead of the accepted one -- and read 0 on every trial of all three
    frozen attempts. A metric that cannot be non-zero is not evidence.
    """
    validated: Optional[ValidatedPlan] = None
    plan_source = ""
    verdicts: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for planner, plan, _score in ranked:
        plan_t = tuple(plan)
        if plan_t in seen:
            continue
        seen.add(plan_t)
        ok, _final, reason = validate_plan_typed(
            typed_domain, typed_initial, plan_t, goal_predicate
        )
        verdicts.append(
            {"planner": planner, "plan": list(plan_t), "valid": bool(ok), "reason": reason}
        )
        if ok and validated is None:
            validated = ValidatedPlan(
                plan=plan_t, model_digest=model_digest, validated_against="TypedDomain"
            )
            plan_source = f"federation:{planner}"
    return validated, plan_source, verdicts


def run_real_trial(
    seed: int,
    provider_key: str,
    config: dict,
    evidence_root: Path,
    probe_budget: int = 12,
    planner_timeout_s: float = 10.0,
    lm: Any = None,
) -> TrialReport:
    """probe -> induce -> project -> federate -> critique -> (discriminate,
    re-induce, replan) -> independently validate -> commit -> execute.

    Per-trial isolation matches `level4_generator.Trial`: a uuid4 run_id and
    a private evidence directory created with ``exist_ok=False``, so two
    trials can never share probe logs, ledgers or OCEL output.
    """
    run_id = str(uuid.uuid4())
    evidence_dir = Path(evidence_root) / f"realtrial_{seed}_{run_id}"
    evidence_dir.mkdir(parents=True, exist_ok=False)

    # The witness journal. Every relation the independent chain needs is
    # STATED here at the transition where it becomes true -- goal admission,
    # candidate selection, commitment, independent goal verification, replay.
    # Nothing is written back after the episode finishes: a relation
    # reconstructed from a completed episode is a claim about a claim.
    from autofde_lab.hub.domain.gym_procedure.level4_ocel import WitnessJournal

    journal = WitnessJournal(evidence_dir)

    env = RealBlindEnvironment(provider_key, config, evidence_dir / "discovery")

    # --- probe ------------------------------------------------------------
    raw_records, n_probes = _discover_by_probing(env, probe_budget)

    # --- typed projection (losses recorded, never silently dropped) --------
    observations = [_observation_from_facts(r.get("observed_pre_facts", [])) for r in raw_records]
    dims = classify_observation([o for o in observations if o])
    losses: dict[str, str] = {}

    def _project(facts: list[str]) -> list[str]:
        projected, lost = propositionalize(_observation_from_facts(facts), dims)
        losses.update(lost)
        return sorted(projected)

    probe_log = [
        {
            "action": r["action"],
            "applicable": r.get("applicable", False),
            "observed_pre_facts": _project(r.get("observed_pre_facts", [])),
            "delta_added": _project(r.get("delta_added", [])),
            "delta_removed": _project(r.get("delta_removed", [])),
        }
        for r in raw_records
    ]
    (evidence_dir / "typed_probe_log.json").write_text(
        json.dumps({"probe_log": probe_log, "representation_losses": losses}, indent=2),
        encoding="utf-8",
    )

    initial_facts = frozenset(probe_log[0]["observed_pre_facts"]) if probe_log else frozenset()
    goal = frozenset({"solved=True"})
    problem = DiscoveredProblem(initial_state=initial_facts, goal=goal)

    def _plan_round(log: list[dict]) -> tuple[DiscoveredDomain, Recipe, list, AdvisoryCritique, list[str]]:
        domain = induce_discovered_domain(log)
        recipe = project_to_recipe(domain, problem, gym=provider_key, task=f"seed{seed}", source_ref=f"realtrial:{run_id}")
        classified = classify_registered_solvers(recipe)
        supported = [c.name for c in classified if c.status == "SUPPORTED"]
        attempts = run_federation(recipe, supported, timeout_s=planner_timeout_s)
        return domain, recipe, attempts, critique_candidates(attempts, domain, lm=lm), supported

    base_probe = dict(
        seed=seed,
        run_id=run_id,
        provider=provider_key,
        n_probes=n_probes,
        n_planner_attempts=0,
        planners_producing_candidates=(),
        disagreement_detected=False,
        evidence_dir=str(evidence_dir),
        representation_losses=dict(losses),
        n_supported_solvers=0,
        discriminating_probe=None,
    )

    # A trial in which probing never observed ANY action succeed cannot be
    # modelled at all: `induce_discovered_domain` marks every action unknown,
    # `project_to_recipe` drops all of them, and `Recipe.__post_init__`
    # rightly refuses an empty procedure whose goal is unsatisfied. That
    # refusal is correct -- but raising it out of `run_real_trial` removes
    # the trial from the scoreboard entirely rather than scoring it as the
    # failure it is. Measured: 4 of 10 frozen seeds terminated as uncaught
    # `ValueError` and had to be hand-classified outside the conjunction,
    # which is precisely the "absent evidence is not a scored factor" hole
    # the replay repair closed one level up.
    #
    # A trial that cannot be modelled is a FAILED trial with a named reason,
    # never an absent one. Report it through the normal TrialReport channel
    # so `_row_is_alive` scores it False on real fields.
    if all(not r.get("applicable") for r in probe_log):
        refusal_reasons = sorted(
            {str(r.get("reason")) for r in raw_records if r.get("reason")}
        )
        return TrialReport(
            standing=UnknownEvidence(
                missing="NO_APPLICABLE_ACTION_DISCOVERED", episode_digest=None
            ),
            ocel_ref_violations=(),
            replay_mismatches=("NO_APPLICABLE_ACTION_DISCOVERED",),
            replay_record_count=0,
            replay_error="NO_APPLICABLE_ACTION_DISCOVERED",
            outcome="NO_APPLICABLE_ACTION_DISCOVERED",
            unsound_candidates_rejected=0,
            goal_predicate_description=(
                "REAL goal: solved is True in the post-execution observation "
                f"(unreachable: every probe was refused; provider reasons={refusal_reasons})"
            ),
            typed_derived_dimensions=(),
            **base_probe,
        )

    domain, recipe, attempts, critique, supported = _plan_round(probe_log)
    n_supported = len(supported)

    # --- discriminating probe when planners disagree ----------------------
    discriminating: Optional[str] = None
    if critique.disagreement_detected and n_probes < probe_budget:
        for action_id in sorted(domain.actions):
            probe = propose_discriminating_probe(domain, action_id)
            if probe is None:
                continue
            discriminating = f"{probe.action}: {probe.rationale}"
            rec = env.try_action(probe.action, commit=False)
            n_probes += 1
            probe_log.append(
                {
                    "action": rec["action"],
                    "applicable": rec.get("applicable", False),
                    "observed_pre_facts": _project(rec.get("observed_pre_facts", [])),
                    "delta_added": _project(rec.get("delta_added", [])),
                    "delta_removed": _project(rec.get("delta_removed", [])),
                }
            )
            domain, recipe, attempts, critique, supported = _plan_round(probe_log)
            break

    # --- TYPED model: the authoritative validation gate -------------------
    # `induce_discovered_domain` unions deltas across calls and so claims a
    # single `increment` establishes `solved=True`. That model validated a
    # 1-step plan for a 3-step goal and 30 planners agreed with it. The typed
    # model learns `counter += 1` and refuses to claim `solved` at all, so no
    # federation candidate can reach commitment without surviving it.
    #
    # Induced BEFORE `federation.json` is written, deliberately: `typed_search`
    # needs the typed model, and it is now a federated producer whose attempt
    # must appear in that file alongside every other planner's.
    typed_records = [r for r in raw_records if "observed_pre" in r and "observed_post" in r]
    typed_domain: TypedDomain = induce_typed_domain(typed_records)
    typed_initial = dict(typed_records[0]["observed_pre"]) if typed_records else {}
    goal_predicate, goal_expr = model_goal_predicate(provider_key, typed_initial, config)
    goal_predicate_description = (
        f"MODEL goal (base dimensions): {goal_expr}; "
        f"REAL goal: solved is True in the post-execution observation"
    )
    # `typed_search` COMPETES -- it does not bypass. Previously it was called
    # directly further down, produced no `PlannerAttempt`, appeared in no
    # `federation.json`, was never ranked, and still sourced the commitment
    # (`committed_plan_source == "typed_search"` on an archived trial where 0
    # of 13 federation candidates matched the committed plan). It is now one
    # more producer under the same contract; the advisory ranking is
    # recomputed over the FULL attempt set so it is ranked with the others.
    attempts = list(attempts) + [
        run_typed_search_attempt(
            typed_domain,
            typed_initial,
            goal_predicate,
            recipe_problem_digest(recipe),
            timeout_s=planner_timeout_s,
        )
    ]
    critique = critique_candidates(attempts, domain, lm=lm)

    candidate_planners = tuple(sorted({a.planner_identity for a in attempts if a.outcome == "PLAN_CANDIDATE"}))

    (evidence_dir / "federation.json").write_text(
        json.dumps(
            [
                {"planner": a.planner_identity, "representation": a.representation,
                 "outcome": a.outcome, "plan": list(a.candidate_plan),
                 "duration_s": a.planning_duration_s, "detail": a.detail}
                for a in attempts
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    # THE COMMON CANDIDATE SET -- the single door to commitment. Every
    # producer's PLAN_CANDIDATE enters here and nothing else can.
    common = CommonCandidateSet(recipe_problem_digest(recipe))
    common.admit_all(attempts)

    # GOAL ADMISSION -- the admitted goal acquires a durable identity here,
    # before any plan exists to reach it. A goal recovered afterwards from the
    # final state could not fail to be met.
    goal_id = journal.admit_goal(
        goal_id=f"urn:level4:goal:{run_id}",
        expression=goal_expr,
        target=dict(config),
    )

    base = dict(
        seed=seed, run_id=run_id, provider=provider_key, n_probes=n_probes,
        n_planner_attempts=len(attempts), planners_producing_candidates=candidate_planners,
        disagreement_detected=critique.disagreement_detected, evidence_dir=str(evidence_dir),
        representation_losses=dict(losses), n_supported_solvers=n_supported,
        discriminating_probe=discriminating,
    )

    # --- independent validation -> commitment -> actuation ----------------
    typed_derived = tuple(typed_domain.derived_dimensions())
    typed_base = dict(
        goal_predicate_description=goal_predicate_description,
        typed_derived_dimensions=typed_derived,
    )
    model_digest = _digest(
        {a: sorted(e.describe() for e in act.effects.values()) for a, act in typed_domain.actions.items()}
    )

    # EVERY federation candidate is validated, not just the ones ahead of the
    # first acceptance.
    #
    # The previous loop `break`-ed on the first valid plan and incremented
    # `rejected` only for candidates examined before it. Measured: the counter
    # read 0 on every trial of all three frozen attempts -- including trials
    # whose committed plan was model-valid and reality-invalid -- because
    # either the top-ranked candidate validated (so nothing was ever counted)
    # or the federation produced no candidates at all and the plan came from
    # `search_plan_typed` (so the loop body never ran). A metric that cannot
    # be non-zero is not evidence that nothing unsound was proposed.
    #
    # Now: validate all DISTINCT candidate plans, count every one the typed
    # model rejected, and persist the per-candidate verdicts so the number is
    # falsifiable from the evidence directory rather than trusted.
    #
    # And every candidate now means EVERY candidate: the selection sweep runs
    # over the common candidate set, which includes `typed_search`. The
    # advisory ranking only orders the sweep; it cannot admit or exempt.
    selected, candidate_verdicts = select_governed_candidate(
        common, typed_domain, typed_initial, goal_predicate, critique.ranked_candidates
    )
    validated = (
        ValidatedPlan(
            plan=selected.plan, model_digest=model_digest, validated_against="TypedDomain"
        )
        if selected is not None
        else None
    )
    plan_source = f"federation:{selected.planner_identity}" if selected is not None else ""
    rejected = sum(1 for v in candidate_verdicts if not v["valid"])
    (evidence_dir / "typed_validation.json").write_text(
        json.dumps(
            {
                "n_distinct_candidates": len(candidate_verdicts),
                "unsound_candidates_rejected": rejected,
                "verdicts": candidate_verdicts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # (The former `search_plan_typed` fallback lived here. It is gone as a
    # FALLBACK, not as a capability: `typed_search` runs above as a federated
    # producer, so its candidate reaches this point through the common set.)
    if validated is None:
        return TrialReport(
            standing=UnknownEvidence(missing="NO_TYPED_VALID_PLAN", episode_digest=None),
            ocel_ref_violations=(),
            replay_mismatches=(), outcome="NO_TYPED_VALID_PLAN",
            unsound_candidates_rejected=rejected, **typed_base, **base
        )

    # SELECTION -- this candidate, for that goal, from that source. Recorded
    # at the moment of selection, so no reader has to re-derive "which of the
    # candidates was chosen" from a verdict file.
    candidate_id = journal.select_candidate(
        candidate_id=f"urn:level4:candidate:{run_id}",
        goal_id=goal_id,
        planner=plan_source,
        source=validated.validated_against,
        plan=tuple(validated.plan),
    )

    # THE GATE. A plan that did not come through the common candidate set
    # cannot source a commitment -- typed refusal, not a comment.
    common.require_governed(validated.plan, selected.planner_identity)

    commitment = commit(validated, trial_id=run_id)
    # COMMITMENT -- this commitment realizes that candidate.
    journal.commit_plan(
        commitment_subject=f"urn:trial:{run_id}", candidate_id=candidate_id
    )
    payloads = [env.payload_for(a) for a in validated.plan]
    expected_steps = predict_step_postconditions(
        validated.plan, provider_key, typed_initial, payloads
    )
    try:
        result = commit_and_execute(
            commitment, provider_key, config, expected_steps, evidence_dir / "actuation", payloads
        )
    except ActuationMaterializeRefused as exc:
        # A real, named blocker at the actuation stage -- discovery and
        # typed search both already succeeded (this trial reached
        # commitment), so this is not an unmodellable trial and not a
        # planning-layer gap. Reported through the normal TrialReport
        # channel, never an unhandled crash: see
        # `ActuationMaterializeRefused`'s docstring for the real incident
        # this repairs.
        return TrialReport(
            standing=BlockedEvidence(reason=str(exc)),
            ocel_ref_violations=(),
            replay_mismatches=("ACTUATION_MATERIALIZE_REFUSED",),
            replay_record_count=0,
            replay_error=str(exc),
            outcome="ACTUATION_MATERIALIZE_REFUSED",
            unsound_candidates_rejected=rejected,
            committed_plan=validated.plan,
            committed_plan_source=plan_source,
            **typed_base,
            **base,
        )
    # INDEPENDENT CONSEQUENCE + REPLAY -- both stated as the execution returns
    # them, naming exact identities. The goal outcome is read off the real
    # `verify_goal_consequence` event the subprocess projected from gymact's
    # own `VerificationResult`; an absent event records NOTHING (UNKNOWN),
    # and is never written as a refutation.
    _ledger_path = evidence_dir / "actuation" / "receipts.sqlite3"
    _final_act = journal.final_actuation_receipt_id(_ledger_path)
    for _event in result["ocel"].get("events", []) if isinstance(result.get("ocel"), dict) else []:
        if _event.get("type") != GOAL_CONSEQUENCE_EVENT_TYPE or _final_act is None:
            continue
        _attributes = {a["name"]: a["value"] for a in _event.get("attributes", [])}
        if "passed" not in _attributes or "verification_id" not in _attributes:
            continue
        _episode = next(
            (r["objectId"] for r in _event.get("relationships", []) if r.get("qualifier") == "episode"),
            "",
        )
        journal.observe_goal_consequence(
            verification_id=str(_attributes["verification_id"]),
            goal_id=goal_id,
            outcome="ESTABLISHED" if _attributes["passed"] == "True" else "REFUTED",
            actuation_receipt_id=_final_act,
            # The verifier is gymact's kernel `verify()` path; the actuator is
            # the actuation the plan's final step opened. Two identities, so
            # self-certification is a graph property, not a flag.
            verifier_id=f"urn:level4:verifier:gymact-kernel-verify:{_episode}",
            actuator_id=f"urn:level4:actuation:{_final_act}",
        )
    if isinstance(result.get("replay"), dict) and result["replay"].get("head_digest"):
        journal.complete_replay(
            ledger=_ledger_path,
            head_digest=str(result["replay"]["head_digest"]),
            record_count=int(result["replay"].get("record_count") or 0),
            valid=bool(result["replay"].get("valid")),
            mode=str(result["replay"].get("mode") or ""),
        )

    violations = validate_ocel_referential_integrity(result["ocel"])
    # Read the replay record STRICTLY. A missing "replay" key, or a missing
    # field inside it, means replay evidence was not produced -- which is a
    # failed factor, not a satisfied one. The previous code used
    # .get("mismatches", []) and so treated "no replay record at all" as
    # "replay clean".
    replay_rec = result["replay"] if "replay" in result else None
    if not isinstance(replay_rec, dict):
        replay_rec = {
            "mode": "EVIDENCE_REPLAY",
            "ran": False,
            "valid": False,
            "record_count": 0,
            "head_digest": None,
            "error": "REPLAY_RECORD_ABSENT",
            "mismatches": ["REPLAY_RECORD_ABSENT"],
        }
    replay_rec.setdefault("mode", "EVIDENCE_REPLAY")
    # Index, never `.get(key, default)`: a replay record that omits `ran` or
    # `valid` is a malformed record, and defaulting it to False would quietly
    # convert "the bridge did not report" into "the bridge reported a
    # failure". Both are wrong to guess -- so the missing key is materialised
    # explicitly, with a named reason, before it is read.
    for required_key, absent_marker in (
        ("ran", False), ("valid", False), ("mismatches", ["REPLAY_FIELD_ABSENT"]),
        ("record_count", 0), ("error", None), ("head_digest", None),
    ):
        if required_key not in replay_rec:
            replay_rec[required_key] = absent_marker
            if required_key in ("ran", "valid"):
                replay_rec["mismatches"] = list(replay_rec["mismatches"] or []) + [
                    f"REPLAY_FIELD_ABSENT:{required_key}"
                ]
                replay_rec["error"] = f"REPLAY_FIELD_ABSENT:{required_key}"
    mismatches = [str(m) for m in (replay_rec["mismatches"] or [])]
    replay_ran = bool(replay_rec["ran"])
    replay_valid = bool(replay_rec["valid"])
    if not replay_ran and "REPLAY_RECORD_ABSENT" not in mismatches:
        mismatches.append("REPLAY_DID_NOT_RUN")
    # `final_state` is kept as descriptive evidence data on `TrialReport` --
    # it is not itself a verdict field and no comparison against it is made
    # here. The REAL goal-attainment verdict now lives inside `standing`
    # itself: `_standing_from_bridge_result` -> `standing_from_episode` reads
    # a real `verify_goal_consequence` OCEL event -- projected by the
    # execution bridge above from the real `VerificationResult` returned by
    # `gym.verify(episode_id, final_expected)` -- out of `result["ocel"]`,
    # and only returns `Level4AliveEvidence` when that independent
    # postcondition reports `passed=True`. A clean process with an
    # absent/failed goal consequence returns `ConformantButGoalUnmetEvidence`
    # instead, never a silently-upgraded `Level4AliveEvidence`.
    real_final = dict(result["final_state"] or {}) if "final_state" in result else {}
    standing = _standing_from_bridge_result(result, replay_rec, expected_steps)
    return TrialReport(
        standing=standing,
        ocel_ref_violations=tuple(violations),
        replay_mismatches=tuple(mismatches),
        replay_record_count=int(replay_rec["record_count"] or 0),
        replay_error=replay_rec["error"],
        replay_head_digest=replay_rec["head_digest"],
        ocel_digest=str(result["ocel_digest"]) if "ocel_digest" in result else "",
        committed_plan=validated.plan,
        committed_plan_source=plan_source,
        unsound_candidates_rejected=rejected,
        final_state=real_final,
        step_standings=tuple(t["standing"] for t in result["transitions"]),
        outcome="EXECUTED",
        **typed_base,
        **base,
    )


def validate_ocel_referential_integrity(log: dict) -> list[str]:
    """Walk every event relationship's objectId against the declared objects,
    and every event/object type against the declared type tables. Returns a
    list of violations (empty == clean)."""
    violations: list[str] = []

    # A missing section is a violation, not an empty one. `log.get("events",
    # [])` made a log with NO events table iterate zero times and report clean
    # -- the same absence-equals-success shape as the replay defect, one layer
    # down: a log that omits everything scored identically to a log that
    # referenced everything correctly.
    for section in ("objects", "objectTypes", "events", "eventTypes"):
        if section not in log:
            violations.append(f"OCEL_SECTION_ABSENT:{section}")
        elif not isinstance(log[section], list):
            violations.append(f"OCEL_SECTION_NOT_A_LIST:{section}")
    if violations:
        return violations

    object_ids = {o["id"] if "id" in o else None for o in log["objects"]}
    object_types = {t["name"] if "name" in t else None for t in log["objectTypes"]}
    event_types = {t["name"] if "name" in t else None for t in log["eventTypes"]}

    for obj in log["objects"]:
        if "type" not in obj or obj["type"] not in object_types:
            violations.append(f"DANGLING_OBJECT_TYPE:{obj.get('id')}->{obj.get('type')}")
    for ev in log["events"]:
        if "type" not in ev or ev["type"] not in event_types:
            violations.append(f"DANGLING_EVENT_TYPE:{ev.get('id')}->{ev.get('type')}")
        # An event with no relationships key at all is not "an event with zero
        # relationships" -- it is an event whose object linkage was never
        # recorded, and OCEL requires that linkage.
        if "relationships" not in ev:
            violations.append(f"EVENT_RELATIONSHIPS_ABSENT:{ev.get('id')}")
            continue
        for rel in ev["relationships"] or []:
            if "objectId" not in rel or rel["objectId"] not in object_ids:
                violations.append(f"DANGLING_OBJECT_REFERENCE:{ev.get('id')}->{rel.get('objectId')}")
    return violations
