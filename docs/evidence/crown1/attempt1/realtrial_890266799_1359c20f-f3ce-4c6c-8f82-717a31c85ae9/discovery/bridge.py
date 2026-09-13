
import asyncio
import importlib
import json
import sys


async def main(module_path: str, class_name: str, provider_name: str, config: dict, requests: list) -> dict:
    from gymact import GymAct, MaterializationIntent
    from gymact.models import ActuationIntent

    provider_cls = getattr(importlib.import_module(module_path), class_name)
    gym = GymAct()
    gym.register_provider(provider_cls())

    materialization = await gym.materialize(MaterializationIntent(provider=provider_name, config=config))
    if not materialization.accepted:
        return {"materialize_failed": True, "reason": materialization.receipt.reason}
    episode_id = materialization.episode.episode_id

    # capabilities() lives on the materialized Environment object, which
    # GymAct keeps internal to the kernel rather than returning it from
    # materialize() -- capabilities are static per provider/config (no
    # actuation happens here), so reading them off a second, disposable,
    # never-actuated Environment instance is side-effect-free and gives
    # the real binding->iri mapping without reaching into kernel internals.
    probe_provider = provider_cls()
    probe_env = await probe_provider.materialize(scenario=None, config=config)
    caps = {c.binding: c for c in probe_env.capabilities()}
    await probe_env.teardown()

    results = []
    for req in requests:
        binding = req["action"]
        cap = caps.get(binding)
        if cap is None:
            results.append({"action": binding, "applicable": False, "reason": "UNKNOWN_CAPABILITY_LOCAL"})
            continue
        before = await gym.observe(episode_id)
        before_state = dict(before.state)
        outcome = await gym.act(ActuationIntent(episode_id=episode_id, capability=cap.iri, payload=req.get("payload", {})))
        after = await gym.observe(episode_id)
        after_state = dict(after.state)
        # The kernel reports accepted=True for any actuate() that did not
        # raise -- including a lawful-but-inert one (a provider reporting
        # `applicable: False` in its own effect, e.g. mining into a full
        # pool). Treating an inert action as applied teaches discovery that
        # a refused action is available, so the provider's own flag wins
        # whenever it supplies one.
        effect = outcome.effect if isinstance(outcome.effect, dict) else {}
        results.append({
            "action": req.get("action_id", binding),
            "binding": binding,
            "payload": req.get("payload", {}),
            "applicable": bool(outcome.accepted) and bool(effect.get("applicable", True)),
            # REAL TYPED observations, straight off gym.observe(...).state.
            # The stringified `*_facts` fields below are kept for the older
            # untyped IR, but stringifying is lossy (a float reward becomes an
            # opaque atom, an int delta becomes an absolute fact) -- typed
            # induction consumes these two dicts instead.
            "observed_pre": before_state,
            "observed_post": after_state,
            "observed_pre_facts": sorted(f"{k}={v}" for k, v in before_state.items()),
            "delta_added": sorted(
                f"{k}={after_state[k]}" for k in after_state
                if before_state.get(k) != after_state.get(k)
            ),
            "delta_removed": sorted(
                f"{k}={before_state[k]}" for k in before_state
                if before_state.get(k) != after_state.get(k)
            ),
            "standing": outcome.standing.value if hasattr(outcome.standing, "value") else str(outcome.standing),
            "reason": outcome.receipt.reason if outcome.receipt else None,
        })

    final_state = after_state if requests else dict((await gym.observe(episode_id)).state)
    ocel_log = gym.episode_ocel_log(episode_id)
    await gym.teardown(episode_id)
    return {
        "episode_id": episode_id,
        "results": results,
        "final_observe": final_state,
        "ocel_log": ocel_log,
        # Real capability surface, read off the provider itself. DO bindings
        # are the only actuatable ones; READ bindings are refused by the
        # kernel with READ_CAPABILITY_IS_NOT_ACTUATION.
        "capabilities": [
            {"binding": c.binding,
             "consequence": c.consequence.value if hasattr(c.consequence, "value") else str(c.consequence),
             "iri": c.iri}
            for c in caps.values()
        ],
    }


if __name__ == "__main__":
    module_path, class_name, provider_name = sys.argv[1], sys.argv[2], sys.argv[3]
    config = json.loads(sys.argv[4])
    requests = json.loads(sys.argv[5])
    out = asyncio.run(main(module_path, class_name, provider_name, config, requests))
    print(json.dumps(out, default=str))
