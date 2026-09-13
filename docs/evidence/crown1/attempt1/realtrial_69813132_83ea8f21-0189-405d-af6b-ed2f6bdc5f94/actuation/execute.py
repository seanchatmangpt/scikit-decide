
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
        transitions.append({
            "action": binding,
            "step_index": i,
            "expected": step_expected,
            "standing": vt.receipt.standing.value if hasattr(vt.receipt.standing, "value") else str(vt.receipt.standing),
            "verified": vt.receipt.verified,
            "reason": vt.receipt.reason,
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

    replay_report = None
    try:
        rep = replay_ledger(ledger, mode=ReplayMode.EVIDENCE_REPLAY,
                            expected=ReplayExpectation(subject_ref=m.episode.environment_id))
        replay_report = {"admitted": getattr(rep, "admitted", None),
                         "mismatches": list(getattr(rep, "mismatches", []) or [])}
    except Exception as exc:
        replay_report = {"error": f"{type(exc).__name__}: {exc}"[:300]}

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
