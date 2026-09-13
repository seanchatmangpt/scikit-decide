#!/usr/bin/env python3
"""Real, live trial of `gymact_dspy_react.run_dspy_diagnosis` against a real,
materialized `SregymVendorProvider` environment on a real, reachable kind
cluster (`kind-gymact-test`), with `attempt_mitigation=True` -- exercising
the real portfolio -> safe_to_actuate filter -> kubectl-translate ->
gated actuate() -> submit_mitigation chain in `gymact_mitigation_actuation.py`
end-to-end for the first time this session, not a re-run of the existing
Chicago unit tests (which all use `_FakeSregymEnvironment` per
`.claude/rules/testing-chicago-style.md`'s one legitimate infeasible-in-CI
exception).

This is a real script, not a test: it mutates a real cluster and makes real,
live, billed Groq LM calls. Run deliberately.
"""

from __future__ import annotations

import asyncio
import json
import sys

import numpy  # noqa: F401  -- force full numpy init before dspy's lazy loader touches it;
# without this, `import dspy` followed by `from autofde_lab... import numpy.typing`
# re-enters numpy mid-init via dspy.utils.lazy_import and raises
# "cannot import name 'NDArray' from partially initialized module 'numpy._typing'"
# (reproduced and confirmed live this session; pytest doesn't hit it because test
# modules import autofde_lab, which fully initializes numpy, before dspy is touched).
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path.home() / "gymact" / "src"))

import dspy  # noqa: E402

from autofde_lab.reasoning.gymact_dspy_react import DiagnosisResult, run_dspy_diagnosis  # noqa: E402


async def main() -> int:
    problem_id = sys.argv[1] if len(sys.argv) > 1 else "wrong_dns_policy_social_network"

    print(f"[trial] problem_id={problem_id!r}, attempt_mitigation=True, live groq LM, real cluster")

    lm = dspy.LM("groq/openai/gpt-oss-20b", max_tokens=16000, cache=False)

    result: DiagnosisResult = await run_dspy_diagnosis(
        problem_id,
        mcp_server_port=9954,
        api_port=8000,
        judge_model_id="groq/openai/gpt-oss-20b",
        judge_api_base="https://api.groq.com/openai/v1",
        wall_clock_timeout_s=900,
        startup_timeout_seconds=900.0,
        verify_timeout_seconds=300.0,
        max_iters=6,
        attempt_mitigation=True,
        lm=lm,
    )

    print("[trial] === REAL RESULT ===")
    print(f"problem_id={result.problem_id}")
    print(f"namespace={result.namespace}")
    print(f"diagnosis={result.diagnosis[:400]!r}")
    print(f"confidence={result.confidence}")
    print(f"mitigation_attempted={result.mitigation_attempted}")
    print(f"submit_mitigation_response={json.dumps(result.submit_mitigation_response, default=str)[:1000]}")
    mitigation_execution = None
    if isinstance(result.trajectory, dict):
        mitigation_execution = result.trajectory.get("mitigation_execution")
    print(f"mitigation_execution={json.dumps(mitigation_execution, default=str)[:1000]}")

    out = {
        "problem_id": result.problem_id,
        "namespace": result.namespace,
        "diagnosis": result.diagnosis,
        "confidence": result.confidence,
        "mitigation_attempted": result.mitigation_attempted,
        "submit_mitigation_response": result.submit_mitigation_response,
        "mitigation_execution": mitigation_execution,
    }
    out_path = REPO_ROOT / "docs" / f"2026-08-11-live-trial-{problem_id}.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"[trial] wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
