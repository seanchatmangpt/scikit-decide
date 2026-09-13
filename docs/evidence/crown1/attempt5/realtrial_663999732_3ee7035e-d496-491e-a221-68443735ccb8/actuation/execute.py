
import asyncio, importlib, json, sys


async def main(module_path, class_name, provider_name, config, plan, expected_list, payloads, ledger_path):
    from gymact import GymAct, MaterializationIntent
    from gymact.models import ActuationIntent
    from gymact.crown_runtime import execute_verified
    from gymact.sqlite_ledger import SQLiteReceiptLedger
    from gymact.ocel import receipts_to_ocel, validate_ocel_log, digest_ocel_log
    from gymact.replay import replay_ledger, ReplayExpectation, ReplayMode

    provider_cls = getattr(importlib.import_module(module_path), class_name)
    ledger = SQLiteReceiptLedger(ledger_path)
    gym = GymAct(receipt_ledger=ledger)
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
        intent = ActuationIntent(episode_id=episode_id, capability=cap.iri, payload=payloads[i])
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
            "ran": True,
            "valid": bool(rep.valid),
            "record_count": int(rep.record_count),
            "head_digest": rep.head_digest,
            "mismatches": mismatches,
            "error": None,
        }
    except Exception as exc:
        # Fail CLOSED: a replay that could not run is a failed factor, never a
        # silently satisfied one.
        replay_report = {
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
    }


if __name__ == "__main__":
    a = sys.argv
    out = asyncio.run(main(a[1], a[2], a[3], json.loads(a[4]), json.loads(a[5]),
                          json.loads(a[6]), json.loads(a[7]), a[8]))
    print(json.dumps(out, default=str))
