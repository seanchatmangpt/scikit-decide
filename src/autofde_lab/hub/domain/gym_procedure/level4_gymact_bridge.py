# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real GymAct-backed BlindEnvironment -- subprocess bridge to ~/gymact.

Follows the exact pattern established by
`tests/ecosystem/test_gymact_terragoat_bridge_chicago.py`: gymact's own
venv runs a small bridge script that imports gymact and drives a real
`GymAct` kernel episode; this process never imports gymact directly. The
bridge script is the ONLY thing that ever sees the provider's real
capability semantics -- what crosses the process boundary back to
autofde-lab is exactly the same two-method shape as
`level4_generator.BlindEnvironment`: action names, and
(applicable, observed_pre_facts, delta_added, delta_removed) per probe.

`episode_id` (minted by GymAct itself, per episode) is the trial's real
isolation key -- one subprocess-driven episode per trial, never shared.

Real provider API confirmed against `~/gymact/tests/test_cube_counter.py`:
`GymAct().register_provider(ProviderInstance())`, then
`gym.materialize(MaterializationIntent(provider=<provider.name>, config=...))`,
`gym.observe(episode_id).state` (a dict), `gym.act(ActuationIntent(...))`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from autofde_lab.hub.domain.gym_procedure.trial_isolation import (
    acquire_exclusive_evidence_dir,
)

HOME = Path.home()
GYMACT = HOME / "gymact"
GYMACT_VENV_PYTHON = GYMACT / ".venv" / "bin" / "python"

# provider registry name -> (import path, class name, provider .name)
_PROVIDERS = {
    "cube_counter": ("gymact.gyms.cube_counter", "CubeCounterProvider", "cube-counter"),
    "cube_container_counter": (
        "gymact.gyms.cube_container_counter",
        "CubeContainerCounterProvider",
        "cube-container-counter",
    ),
    "switchboard": ("gymact.gyms.switchboard", "SwitchboardProvider", "switchboard"),
    "resource_flow": (
        "gymact.gyms.resource_flow",
        "ResourceFlowProvider",
        "resource-flow",
    ),
    "lock_and_key": (
        "gymact.gyms.lock_and_key",
        "LockAndKeyProvider",
        "lock-and-key",
    ),
    # NOT gymact.local_providers -- that module holds FilesystemProvider/
    # GitProvider/SQLiteProvider (real disk/subprocess state). MemoryProvider
    # is a separate, genuinely in-process module (gymact/providers.py),
    # confirmed live before wiring this entry -- see
    # docs/2026-08-08-level4-gym-census-round2.md's own module-path
    # correction note for this gym.
    "memory": ("gymact.providers", "MemoryProvider", "memory"),
    # Real class name confirmed by direct read of ~/gymact's own sregym.py
    # (not the differently-named SREGymProvider that also exists on an
    # unmerged gymact PR branch): SregymVendorProvider, provider .name
    # "sregym", already imported directly (not through this bridge) by
    # autofde_lab.reasoning.sregym_pipeline via SREGYM_CAPABILITIES. This
    # entry is what lets the generic Level-4 discovery/trial harness reach
    # the same real provider generically, not just that one hand-written
    # pipeline.
    "sregym": ("gymact.gyms.sregym", "SregymVendorProvider", "sregym"),
    # Cherry-picked into ~/gymact as a standalone file (see that repo's own
    # commit ba52b51) from an unmerged first-class-SWEGym PR -- real, not
    # vendored/faked. materialization_requires_authority=False (materialize
    # only looks up dataset metadata); the single evaluate-patch DO
    # capability requires authority at actuate time (real Docker mutation).
    "swegym": ("gymact.gyms.swegym", "SWEGymProvider", "swegym"),
}

# How to enumerate a parameterized DO capability's payload space.
#
#   binding -> (payload_key, observation_field_bounding_the_range)
#
# This is an *enumeration* declaration, not domain knowledge: it says how
# many distinct actions a capability denotes and what key names the
# parameter, never what any of them DO. The discovery agent still learns
# every effect by probing. Bindings absent here take an empty payload.
_ACTION_PARAMS: dict[str, dict[str, tuple[str, str]]] = {
    "switchboard": {"toggle_switch": ("index", "n_switches")},
    "lock_and_key": {"pick_key": ("key", "depth")},
}

# Fixed payloads for bindings whose parameter is not an index into an
# observation-bounded range.
_STATIC_PAYLOADS: dict[str, dict[str, dict]] = {
    "cube_counter": {"increment_by": {"value": 1}},
    "cube_container_counter": {"increment_by": {"value": 1}},
    # `memory`'s `set`/`delete` bindings take a fully open-ended string key
    # (and `set` an open-ended value) with no declared mechanism to bound
    # candidate values -- deliberately left unentered here, matching the
    # census's honest scope-narrowing for filesystem/http-json's own
    # open-ended payloads. Both fall through to available_actions()'s
    # existing empty-payload default, which the real MemoryEnvironment
    # refuses with a real, safe, typed KeyError (caught by GymAct's kernel
    # as PROVIDER_ERROR:KeyError, never a crash) -- so discovery correctly
    # learns them as permanently inapplicable rather than exercising them
    # unboundedly.
    "memory": {"increment": {"key": "counter", "amount": 1}},
}

_PARAM_SEP_OPEN = "["
_PARAM_SEP_CLOSE = "]"


def encode_action(binding: str, payload: dict) -> str:
    """Action id for one concrete (binding, payload) pair."""
    if not payload:
        return binding
    inner = ",".join(f"{k}={payload[k]}" for k in sorted(payload))
    return f"{binding}{_PARAM_SEP_OPEN}{inner}{_PARAM_SEP_CLOSE}"


def decode_action(action_id: str) -> tuple[str, dict]:
    """Inverse of `encode_action`: action id -> (binding, payload)."""
    if not action_id.endswith(_PARAM_SEP_CLOSE) or _PARAM_SEP_OPEN not in action_id:
        return action_id, {}
    binding, _, rest = action_id.partition(_PARAM_SEP_OPEN)
    payload: dict = {}
    for part in rest[:-1].split(","):
        if not part:
            continue
        key, _, raw = part.partition("=")
        try:
            payload[key] = int(raw)
        except ValueError:
            payload[key] = raw
    return binding, payload

#: Admitted by the AllowListAuthorityResolver below. A real ref through a
#: real resolver -- an unadmitted ref is still refused.
_AUTHORITY_REF = "urn:autofde-lab:level4-crown-authority"

_BRIDGE_SCRIPT = """
_AUTHORITY_REF = "urn:autofde-lab:level4-crown-authority"
import asyncio
import importlib
import inspect
import json
import sys


def _construct_provider(provider_cls, provider_name: str):
    # Construct a provider generically, whether its class needs zero
    # constructor arguments (cube_counter, switchboard, resource_flow,
    # lock_and_key, cube_container_counter -- every currently wired
    # provider) or one real required argument matching its own registered
    # name (e.g. gymact.gyms.vendor_benchmarks.VendorBenchmarkProvider's
    # `name: str`, shared by every VENDOR_REVISIONS entry). Introspects the
    # REAL constructor signature -- never a per-provider-name branch -- so
    # this generalizes to any future provider without editing this bridge
    # again. A provider needing more than one required argument beyond
    # `self` is an honest TypeError here, not a silent misconfiguration.
    required = [
        p for n, p in inspect.signature(provider_cls.__init__).parameters.items()
        if n != "self"
        and p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.KEYWORD_ONLY)
    ]
    if not required:
        return provider_cls()
    return provider_cls(provider_name)


async def main(module_path: str, class_name: str, provider_name: str, config: dict, requests: list) -> dict:
    from gymact import AllowListAuthorityResolver, GymAct, MaterializationIntent
    from gymact.models import ActuationIntent

    provider_cls = getattr(importlib.import_module(module_path), class_name)
    # Authority is EXERCISED, not bypassed. gymact's providers disagree on
    # their own default: cube_counter's materialize does
    # config.get("requires_authority", True) while its environment __init__
    # defaults the same flag False, and resource_flow defaults it False. With
    # a bare GymAct() the fail-closed DenyAuthorityResolver then refused every
    # cube_counter actuation with LIVE_AUTHORITY_REQUIRED, so discovery
    # observed zero applicable actions and every counter trial ended
    # NO_APPLICABLE_ACTION_DISCOVERED.
    #
    # The fix is a real resolver and a real authority_ref, NOT
    # `requires_authority: False` in config -- that would switch the gate off,
    # whereas this runs it. AllowListAuthorityResolver is gymact's own
    # bounded resolver, documented for exactly this local-gym case, and it
    # still refuses any capability whose ref is not admitted.
    gym = GymAct(authority_resolver=AllowListAuthorityResolver({_AUTHORITY_REF}))
    gym.register_provider(_construct_provider(provider_cls, provider_name))

    # Authority is exercised at MATERIALIZE time too, not only on each
    # ActuationIntent. Measured live this session: providers whose
    # `materialization_requires_authority` is True (a class attribute on
    # every gymact.gyms.vendor_benchmarks.VendorBenchmarkProvider instance,
    # among others -- confirmed for terragoat/sqlite/swe-bench/tau2-bench/
    # ggen-legacy) were refused with LIVE_AUTHORITY_REQUIRED before
    # `capabilities()` was ever reached, because `MaterializationIntent`
    # carries its own real `authority_ref` field (confirmed via
    # `MaterializationIntent.model_fields`) that neither bridge script ever
    # populated -- only `ActuationIntent` calls did. Same fix, same
    # generalization discipline as that one: a real, admitted ref through
    # the same real bounded resolver, not a config flag that switches the
    # gate off.
    materialization = await gym.materialize(
        MaterializationIntent(provider=provider_name, config=config, authority_ref=_AUTHORITY_REF)
    )
    if not materialization.accepted:
        return {"materialize_failed": True, "reason": materialization.receipt.reason}
    episode_id = materialization.episode.episode_id

    # capabilities() lives on the materialized Environment object, which
    # GymAct keeps internal to the kernel rather than returning it from
    # materialize() -- capabilities are static per provider/config (no
    # actuation happens here), so reading them off a second, disposable,
    # never-actuated Environment instance is side-effect-free and gives
    # the real binding->iri mapping without reaching into kernel internals.
    probe_provider = _construct_provider(provider_cls, provider_name)
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
        outcome = await gym.act(ActuationIntent(episode_id=episode_id, capability=cap.iri, payload=req.get("payload", {}), authority_ref=_AUTHORITY_REF))
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
"""


def skip_reason() -> str | None:
    if not GYMACT.is_dir():
        return f"BLOCKED:GYMACT_CHECKOUT_ABSENT: {GYMACT} does not exist"
    if not GYMACT_VENV_PYTHON.is_file():
        return f"BLOCKED:GYMACT_VENV_ABSENT: {GYMACT_VENV_PYTHON} does not exist"
    return None


class RealBlindEnvironment:
    """The only interface a discovery agent may use against a REAL provider.
    Each `try_action` round-trips one subprocess call -- one live GymAct
    episode per Trial (fresh materialize+teardown each call, kept simple
    and correct over kept-alive-across-calls; correctness over throughput
    for this first real increment). `episode_id` returned by the LAST call
    is retained for evidence purposes but each probe is its own
    materialize/act/observe/teardown round-trip against a config that
    encodes prior history via `payload`, since a fresh episode always
    starts from the provider's real initial state -- so `try_action`
    passes the FULL action history as `requests`, replaying it plus the
    new probe each time. This keeps isolation perfect (fresh state per
    call, no possibility of cross-probe contamination) at the cost of
    O(n^2) actuation calls across a full discovery run -- acceptable for
    these bounded providers and honestly documented rather than hidden."""

    def __init__(
        self,
        provider_key: str,
        config: dict,
        evidence_dir: Path,
        claim: object | None = None,
    ) -> None:
        if provider_key not in _PROVIDERS:
            raise ValueError(
                f"unknown provider {provider_key!r}; known: {sorted(_PROVIDERS)}"
            )
        self._module_path, self._class_name, self._provider_name = _PROVIDERS[
            provider_key
        ]
        self._provider_key = provider_key
        self._config = config
        self._actions: list[str] | None = None
        self._payloads: dict[str, dict] = {}
        self._evidence_dir = evidence_dir
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        # Claim the directory exclusively. Without this, two environments
        # constructed with the same evidence_dir silently share one
        # probes.jsonl -- reproduced for real: two trials (target=2 and
        # target=5) each doing one increment leave a single log whose
        # records carry target values [2, 5], which no verifier reading
        # that log alone can attribute back to a trial. That is precisely
        # the Level 3 cross-trial contamination incident's shape, so the
        # claim is taken here in __init__ rather than left to callers who
        # can forget it.
        #
        # A caller that ALREADY holds the claim for this directory (e.g. a
        # trial runner that claimed it before constructing anything) passes
        # it in as `claim`, so a legitimate single owner does not collide
        # with itself. Passing someone else's claim does not help: the
        # lockfile is still on disk, so any genuinely different trial that
        # tries to claim the same directory is still refused.
        self._claim = claim if claim is not None else acquire_exclusive_evidence_dir(
            self._evidence_dir, owner=f"RealBlindEnvironment:{provider_key}"
        )
        self._log_path = self._evidence_dir / "probes.jsonl"
        self._bridge_script = self._evidence_dir / "bridge.py"
        self._bridge_script.write_text(_BRIDGE_SCRIPT, encoding="utf-8")
        self._history: list[dict] = []
        self._last_episode_id: str | None = None
        self._last_ocel: dict | None = None

    def available_actions(self) -> list[str]:
        """The provider's REAL actuatable surface, read off its own
        `capabilities()` over the bridge -- DO bindings only, since a READ
        binding is refused by the kernel with
        READ_CAPABILITY_IS_NOT_ACTUATION and is not an action at all.

        A parameterized binding denotes one action per payload value, so it
        is expanded over the range declared in `_ACTION_PARAMS` and bounded
        by a real observation field (`n_switches`, `depth`). Discovery still
        learns every effect by probing; only the *arity* is declared.
        """
        if self._actions is None:
            result = self._call([])
            observation = dict(result.get("final_observe") or {})
            params = _ACTION_PARAMS.get(self._provider_key, {})
            statics = _STATIC_PAYLOADS.get(self._provider_key, {})
            actions: list[str] = []
            payloads: dict[str, dict] = {}
            for cap in result.get("capabilities", []):
                if cap.get("consequence") != "DO":
                    continue
                binding = cap["binding"]
                if binding in params:
                    payload_key, bound_field = params[binding]
                    bound = observation.get(bound_field)
                    if not isinstance(bound, int) or isinstance(bound, bool):
                        raise RuntimeError(
                            f"ACTION_RANGE_UNOBSERVABLE: {self._provider_key}.{binding} "
                            f"declares its range via observation field {bound_field!r}, "
                            f"which is absent or non-integer in {sorted(observation)}"
                        )
                    for value in range(bound):
                        action_id = encode_action(binding, {payload_key: value})
                        actions.append(action_id)
                        payloads[action_id] = {payload_key: value}
                else:
                    payload = dict(statics.get(binding, {}))
                    action_id = encode_action(binding, payload)
                    actions.append(action_id)
                    payloads[action_id] = payload
            self._actions = actions
            self._payloads = payloads
        return list(self._actions)

    def payload_for(self, action_id: str) -> dict:
        if self._actions is None:
            self.available_actions()
        if action_id in self._payloads:
            return dict(self._payloads[action_id])
        return decode_action(action_id)[1]

    def _request_for(self, action: str) -> dict:
        binding, decoded = decode_action(action)
        return {
            "action": binding,
            "action_id": action,
            "payload": dict(self._payloads.get(action, decoded)),
        }

    def try_action(
        self,
        action: str,
        payload: dict | None = None,
        *,
        commit: bool = True,
        prefix: tuple[str, ...] = (),
    ) -> dict:
        """Probe one action.

        `commit=False` makes the probe SPECULATIVE: the action is really
        executed against a real episode replayed from the recorded history,
        its real effect is observed, and then it is discarded rather than
        adopted into history. This is what makes probing non-destructive.
        Committing every probe let an irreversible action wreck the episode
        mid-discovery -- measured: probing `force_latch` on `lock_and_key`
        jammed the key rack permanently at probe 6, and all six remaining
        probes were refused, so nothing about `open_lock` could ever be
        learned.

        `prefix` runs extra actions (also discarded) before the probe, which
        is how an action guarded by a precondition another action must
        establish gets observed succeeding at all.
        """
        binding, decoded = decode_action(action)
        if payload is None:
            payload = self._payloads.get(action, decoded)
        req = {"action": binding, "action_id": action, "payload": dict(payload)}
        requests = self._history + [self._request_for(p) for p in prefix] + [req]
        result = self._call(requests)
        self._last_episode_id = result.get("episode_id")
        self._last_ocel = result.get("ocel_log")
        record = result["results"][-1]
        # Only advance history on real, applied success -- a refused probe
        # doesn't change real state, so it must not be replayed forward.
        if commit and record.get("applicable"):
            self._history.append(req)
        record["committed"] = bool(commit and record.get("applicable"))
        record["prefix"] = list(prefix)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record

    def committed_history(self) -> list[str]:
        return [r.get("action_id", r["action"]) for r in self._history]

    def episode_ocel_log(self) -> dict | None:
        return self._last_ocel

    def episode_id(self) -> str | None:
        return self._last_episode_id

    def _call(self, requests: list[dict]) -> dict:
        completed = subprocess.run(
            [
                str(GYMACT_VENV_PYTHON),
                str(self._bridge_script),
                self._module_path,
                self._class_name,
                self._provider_name,
                json.dumps(self._config),
                json.dumps(requests),
            ],
            capture_output=True,
            text=True,
            cwd=str(GYMACT),
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"gymact bridge subprocess failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"
            )
        return json.loads(completed.stdout.strip().splitlines()[-1])
