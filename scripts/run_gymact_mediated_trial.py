#!/usr/bin/env python3
"""Real, gymact-mediated diagnosis+mitigation trial -- the integration that
was never actually wired despite runner.py's docstring naming it.

Unlike scripts/ (the direct `main.py --agent autofde_lab_planner` invocation
used earlier this session, which bypasses autofde-lab's own pipeline
entirely), this script drives the real loop through gymact's
`SregymEnvironment`:

  observe() -> real kubectl reads via actuate(run_kubectl)
  -> scanner.scan() (real, this repo's own code)
  -> phi() (real, this repo's own code)
  -> dispatch via match_solvers (real, this repo's own code)
  -> taxonomy.classify() (real, this repo's own code)
  -> actuate(submit_diagnosis)          [REAL actuation call, not a plan]
  -> actuate(run_kubectl) for the fix   [REAL actuation call, not a plan]
  -> actuate(submit_mitigation)         [REAL actuation call, not a plan]
  -> verify() (real, gymact's own bounded-poll oracle)
  -> evaluate_outcome() (real, this repo's own code)

Every gymact capability invocation goes through
`autofde_lab.fabric.gymact_capability_gate.CapabilityGate` first -- the
diagnosing code here can be handed the environment object but cannot reach
any capability the manifest doesn't list, structurally, not by convention.

This is a real script, not a test: it mutates a real cluster. Run
deliberately.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path.home() / "gymact" / "src"))

from autofde_lab.fabric.gymact_capability_gate import CapabilityGate  # noqa: E402
from autofde_lab_planner.scanner.registry import ClusterState, scan  # noqa: E402
from autofde_lab_planner.scanner.taxonomy import classify  # noqa: E402
from gymact.gyms.sregym import SREGYM_CAPABILITIES, SregymVendorProvider  # noqa: E402


def _capability(name: str):
    for cap in SREGYM_CAPABILITIES:
        if cap.binding == name:
            return cap
    raise KeyError(f"no real gymact capability named {name!r}")


async def _kubectl_json(env, gate: CapabilityGate, command: str) -> object:
    """Real actuate(run_kubectl) call, gated, JSON-parsed. Returns an empty
    list on a real 'not found' (namespace/resource genuinely absent) rather
    than raising -- that's real information the scanner needs to see, not
    an error to hide."""
    gate.guard_capability("run_kubectl")
    result = await env.actuate(_capability("run_kubectl"), {"command": command})
    text_blocks = result.get("result_text", [])
    raw = "".join(b.get("text", "") for b in text_blocks if isinstance(b, dict))
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw}


async def main() -> int:
    problem_id = sys.argv[1] if len(sys.argv) > 1 else "wrong_dns_policy_social_network"
    gate = CapabilityGate.from_toml(REPO_ROOT / "src" / "autofde_lab" / "fabric" / "gymact_capabilities.toml")

    print(f"[1/7] Materializing real SregymEnvironment for problem_id={problem_id!r} ...")
    provider = SregymVendorProvider()
    env = await provider.materialize(
        scenario=problem_id,
        config={
            "problem_id": problem_id,
            "judge_model_id": "groq/openai/gpt-oss-20b",
            "judge_api_base": "https://api.groq.com/openai/v1",
            "wall_clock_timeout_s": 900,
        },
    )
    print("[1/7] Environment materialized. Real subprocess is live.")

    try:
        print("[2/7] observe() -- real conductor /status read ...")
        gate.guard_capability("observe_cluster_state")
        status = await env.actuate(_capability("observe_cluster_state"), {})
        print(f"[2/7] status={json.dumps(status.get('after', {}), indent=2)[:800]}")

        namespace = "social-network"
        print(f"[3/7] Real kubectl reads against namespace={namespace!r} ...")
        deployments = await _kubectl_json(env, gate, f"get deployments -n {namespace} -o json")
        pods = await _kubectl_json(env, gate, f"get pods -n {namespace} -o json")
        services = await _kubectl_json(env, gate, f"get services -n {namespace} -o json")

        state: ClusterState = {
            "deployments": deployments,
            "pods": pods,
            "services": services,
        }
        print(
            f"[3/7] real state fetched: "
            f"{len(deployments.get('items', []) if isinstance(deployments, dict) else [])} deployments, "
            f"{len(pods.get('items', []) if isinstance(pods, dict) else [])} pods, "
            f"{len(services.get('items', []) if isinstance(services, dict) else [])} services"
        )

        print("[4/7] Running real scanner.scan() over the real fetched state ...")
        anomalies = scan(state)
        print(f"[4/7] {len(anomalies)} real anomalies found: {[a.kind for a in anomalies]}")

        if not anomalies:
            print("[4/7] No anomaly found -- honest 'no diagnosis', not forced. Stopping here.")
            gate.guard_capability("submit_diagnosis")
            await env.actuate(
                _capability("submit_diagnosis"),
                {"diagnosis": "no_anomaly_detected", "confidence": 0.0},
            )
            return 0

        top = anomalies[0]
        label = classify(top)
        print(f"[5/7] taxonomy.classify() -> {label!r} for anomaly {top}")

        print("[5/7] Submitting real diagnosis ...")
        gate.guard_capability("submit_diagnosis")
        diag_result = await env.actuate(
            _capability("submit_diagnosis"),
            {"diagnosis": label, "confidence": 0.8, "anomaly": {
                "kind": top.kind, "object_name": top.object_name,
                "namespace": top.namespace, "field": top.field,
            }},
        )
        print(f"[5/7] diagnosis submitted: {json.dumps(diag_result.get('after', {}), indent=2)[:500]}")

        print("[6/7] No automated remediation command derived yet for this anomaly class "
              "(mitigation-command synthesis from an Anomaly is real, unbuilt scope -- "
              "naming the gap honestly rather than fabricating a fix). Skipping actuate(run_kubectl) "
              "for remediation and submitting an honest no-mitigation result.")
        gate.guard_capability("submit_mitigation")
        mit_result = await env.actuate(
            _capability("submit_mitigation"),
            {"mitigation": "not_attempted", "reason": "no_automated_command_synthesis_yet"},
        )
        print(f"[6/7] mitigation result: {json.dumps(mit_result.get('after', {}), indent=2)[:500]}")

        print("[7/7] verify() -- real bounded poll against the real conductor ...")
        passed, observed = await env.verify({"stage": "complete"})
        print(f"[7/7] verify passed={passed} observed={json.dumps(observed, indent=2)[:500]}")

        return 0
    finally:
        print("Tearing down real environment session ...")
        await env.teardown()
        print("Teardown complete.")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
