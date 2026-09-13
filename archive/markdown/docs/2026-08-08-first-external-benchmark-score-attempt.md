# FIRST_EXTERNAL_BENCHMARK_SCORE — gate attempt (2026-08-08)

**Verdict: `BLOCKED:NO_SAFE_EXECUTABLE_CANDIDATE_CLEARED_TRIAGE`.** No benchmark ran. No score
exists. No SOTA comparison was made. This document records real, cited investigation evidence
and a real, unexecuted design — nothing here is execution evidence, per
`.claude/rules/standing-law.md`.

## Scope and why this exists

Six real gyms (`resource_flow`, `lock_and_key`, `switchboard`, `cube_counter`,
`cube_container_counter`, `memory`) reach `Level4AliveEvidence` through the common kernel —
see `docs/level4-migration-matrix.md`. That is architecture standing, not a public-benchmark
result. This session's explicit next milestone, named by the user, was
`FIRST_EXTERNAL_BENCHMARK_SCORE`: `Benchmark -> GymAct -> DecisionBasis -> Execution ->
Official/faithful evaluator -> Score`, compared against a real published number. This document
is the real attempt at that gate, run via an ultracode workflow
(`wf_83ef6b7e-172`, 11 agents, 165 tool calls, ~866s), not a claim that it was reached.

## Non-negotiable safety scope, stated up front

Every agent in this workflow carried a hard constraint: no paid third-party API call, no
ambient-credential use, no execution of a specific vendor's code without independently
confirming (from real source, not inference) that doing so requires zero external network
calls to a paid service. This mirrors the boundary this session already drew once before for
the `VendorBenchmarkProvider` family's `run-native` capability (see
`docs/level4-migration-matrix.md`'s "What this session did NOT do, deliberately"). An honest
"still blocked" was treated as a valid, expected outcome throughout — not something to force
past.

## Triage: 8 real candidates, read-only, cited

Category A (fixed reward-file convention) and B (exit-code contract) candidates were chosen
deliberately — the cheapest goal-oracle shape, per
`docs/2026-08-08-level4-gym-census-round2.md`'s 5-category taxonomy — since those are the
closest to already-wired. Each was independently re-verified live from real checked-out
source, not trusted from the prior census (which explicitly flagged most rows as
not-independently-re-verified).

| Gym | Verdict | Real, cited reason |
|---|---|---|
| `devops-gym` | `REQUIRES_EXTERNAL_API` | README requires `LLM_API_KEY`; only documented path is Terminal-Bench (`tb run --agent --model`). Compounded by `REQUIRES_INFRA_ABSENT` — submodule working tree is empty (182,418 files unchecked-out) and per-task Docker base images aren't present. |
| `mcpmark` | `REQUIRES_EXTERNAL_API` | `pipeline.py --models` is a mandatory CLI arg; every entry in `MODEL_CONFIGS` resolves to a paid provider key (OpenAI/OpenRouter/DeepSeek); the evaluator reads a real API key before any task runs. No `--dry-run`/`--baseline`/`--no-agent` path exists anywhere in the source. |
| `sregym` | `REQUIRES_INFRA_ABSENT` | A real, LLM-free, credential-free oracle path exists and was traced to source: `tests/integration/validate_problem.py` -> `IncorrectImageMitigationOracle.evaluate()` is pure `kubectl get deployment` comparison, zero LLM/network/credential. Blocked only because the required kind cluster (Calico CNI, specific node image, HotelReservation app images) isn't provisioned here (`kind get clusters` shows no match). **The most promising future candidate of the 7 excluded.** |
| `sec-bench` | `REQUIRES_EXTERNAL_API` | Shipped `config.example.toml` defaults `model_id = "gpt-5-mini"`; README requires `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`. The evaluator-only path avoids the LLM call but has no local ground-truth predictions to grade (`REQUIRES_DATA_ABSENT`) and needs >200GB of Docker Hub image pulls. |
| `sadservers` | `REQUIRES_INFRA_ABSENT` | Goal-oracle shape (stdout marker) confirmed real for 124/125 scenarios, but 124 require SadServers' own proprietary AWS SaaS ("code is not publicly available" per its own README); the 1 scenario with local build files (`saintjohn`) has a broken Dockerfile referencing a nonexistent `badlog.conf`. |
| `harbor` | **`SAFE_ZERO_COST_CANDIDATE`** (narrowly scoped) | See below. |
| `o11y-bench` | `REQUIRES_EXTERNAL_API` | README requires `ANTHROPIC_API_KEY` "used by the grading pipeline" itself; `grading/judge.py` makes a real `Anthropic(...)` LLM-as-judge call as part of the verifier's normal contract, independent of which agent model is under test. |
| `osworld` | `REQUIRES_EXTERNAL_API` | Every `mm_agents/*` implementation is an LLM API client (`PromptAgent` defaults `model="gpt-4-vision-preview"`); the core loop calls `agent.predict()` every step. Compounded by `REQUIRES_INFRA_ABSENT` (no provisioned VM via VMware/Docker/Modal/Daytona/AWS). |

## The one candidate: `harbor`, oracle mode only

`harbor`'s **default, advertised** usage (`harbor run --agent claude-code --model
anthropic/claude-opus-4-1 ...`) is `REQUIRES_EXTERNAL_API`, identical to the 5 excluded above —
this is not an exception to that pattern. But Harbor ships a real, separate `oracle` agent
(`src/harbor/agents/oracle.py`) that uploads a task's own bundled reference solution and runs
it — no model call anywhere in the file (`grep` for `api_key`/`API_KEY`/`anthropic`/`openai`:
zero hits, confirmed by two independent reads this session). Against the bundled
`examples/tasks/hello-world` task (`[solution.env]`/`[verifier.env]` both empty, a 3-line
`solve.sh` with no network/model calls), this is a real, source-confirmed, zero-LLM,
zero-credential invocation.

**A real self-correction, caught by re-verification, not merely asserted:** the design's first
pass assumed the process exit code was the goal signal (matching category B). Re-reading
`harbor`'s own CLI source (`cli/jobs.py`'s `start()`) found this is **false** — `harbor run`
never gates its own exit code on trial reward. The real signal is
`jobs/<job_name>/result.json` -> `trial_results[0].verifier_result.rewards["reward"]`. Using
the exit code instead would have been exactly the fabricated-postcondition failure this repo's
`_predict_memory`/`_predict_lock_and_key` discipline and `absence-is-not-evidence.md` forbid.

## Why `harbor` did not execute

Passing triage established only that no disqualifying evidence was found by source-reading —
not that a real run was ready. Three concrete, named, unfinished gaps:

1. **`REQUIRES_NEW_CODE:BRIDGE_RESULT_SURFACING`** — `level4_gymact_bridge.py`'s generic
   `_BRIDGE_SCRIPT` only returns `last_result` (argv/returncode/stdout/stderr); it has no
   mechanism to read `result.json`. Unwritten code, not a config toggle.
2. **`UNSUPPORTED:HARBOR_CLI_NOT_INSTALLED`** — `which harbor` is not found in this
   environment; needs `uv tool install harbor` (real, unattempted, non-paid PyPI install).
3. **`REQUIRES_ENV_THREADING:HARBOR_TELEMETRY`** — neither `RealBlindEnvironment._call` nor
   `VendorBenchmarkEnvironment.run_native` pass an explicit `env=`; both inherit the ambient
   environment. `HARBOR_TELEMETRY=0` must be set before construction to guarantee Harbor's
   PostHog telemetry call never fires (non-secret, non-paid endpoint, but avoidable and unset).

Beyond those three, the workflow's own `wire-and-execute` agent was independently stopped by
this session's external safety classifier before attempting anything: it had chosen to run
`harbor`'s Docker-based CLI (which `curl`s an installer script from `astral.sh` inside the
container) on its own initiative, and the classifier correctly noted the user's instruction
("ultracode to get me proof of SOTA") never named `harbor` specifically or authorized executing
that vendor's code. **No file was written, no subprocess was invoked, no code was merged.**

## Governance/budget/authority scaffolding still missing, precisely

Even for `harbor`'s zero-cost oracle mode, this repo has none of the following, and would need
them before treating any vendor-family result as trustworthy at scale:

- No scoped budget abstraction — `run_native`'s only guard (`_safe_argv`) rejects an absolute
  or `..`-containing `argv[0]`; it has no dollar/token/wall-clock budget concept, and the same
  mechanism would run any of the 5 `REQUIRES_EXTERNAL_API` vendors identically if pointed at
  their agent-mode argv.
- No explicit per-call human-confirmation gate — `materialize()` -> `run_native()` is a direct
  path to a live subprocess with inherited ambient environment.
- `VendorBenchmarkEnvironment.requires_authority = True` is set correctly per this repo's
  planner-selects/broker-authorizes law, but this session never exercised or tested that path.
- `result.json`'s shape is traced through Harbor's Pydantic models but never observed against a
  real execution — `MEDIUM` confidence, named as such, not yet `ALIVE`.

## Net statement

Six-gym Level-4 crown standing is unaffected and unchanged by this attempt. The seventh,
external-benchmark class remains `BLOCKED:NO_SAFE_EXECUTABLE_CANDIDATE_CLEARED_TRIAGE`. One
candidate (`harbor`, oracle mode only) survived independently-re-verified triage; zero
integration code was merged; zero subprocesses were invoked. The next lawful step is the
already-tracked implementation task ("VendorBenchmarkProvider family: fix bridge constructor +
design goal-oracle projection"), plus explicit user authorization naming `harbor` specifically
before any real `run-native` call — not a claim of proximity to a score.

## See also

- `docs/level4-migration-matrix.md` — the six-gym `SIX_GYM_KERNEL_GATE` architecture record
  this attempt deliberately did not re-litigate.
- `docs/2026-08-08-level4-gym-census-round2.md` — the prior, not-independently-re-verified
  5-category goal-oracle taxonomy this attempt's triage re-verified live for 8 real vendors.
- `.claude/rules/absence-is-not-evidence.md` — the discipline behind ruling out the exit-code
  goal signal for `harbor` once source-reading showed it was unfounded.
- Repo task "VendorBenchmarkProvider family: fix bridge constructor + design goal-oracle
  projection" — where the three named implementation gaps above are tracked.
