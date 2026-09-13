
_AUTHORITY_REF = "urn:autofde-lab:level4-crown-authority"
_GOAL_CONSEQUENCE_EVENT_TYPE = "verify_goal_consequence"
import asyncio, datetime, hashlib, importlib, json, sys


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


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
    gym.register_provider(provider_cls())

    m = await gym.materialize(MaterializationIntent(provider=provider_name, config=config))
    episode_id = m.episode.episode_id

    probe_provider = provider_cls()
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
