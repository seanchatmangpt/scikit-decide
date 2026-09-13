# LOCAL_LLM_AGENT_DRIVEN_CHECKPOINT — Harbor `terminus-2` × TurboFieldfare (2026-08-08)

**Verdict: `PARTIAL_ALIVE`.** A real, genuine (non-oracle-replay), local-LLM-driven agent
decision loop ran inside Harbor's own unmodified `terminus-2` agent, was scored `1.0` by
Harbor's own unmodified verifier, at zero paid-API cost and zero ambient-credential use — a
real, bounded working checkpoint. The larger claim it is a step toward
(`FIRST_EXTERNAL_BENCHMARK_SCORE`, a real, externally-recognized, SOTA-comparable score) does
**not** follow from it yet: this trial ran against Harbor's own bundled `hello-world` toy task,
not a public benchmark. See "What this does and does not establish" below before citing this
document for anything stronger.

## Scope and why this exists

`docs/2026-08-08-first-external-benchmark-score-attempt.md` found every real external vendor
benchmark blocked on either a real paid-LLM requirement or missing infra, except `harbor`'s
zero-LLM `oracle` agent mode — which only replays a task's own bundled reference solution,
proving evidence plumbing, not agent capability. That attempt's verdict,
`BLOCKED:NO_SAFE_EXECUTABLE_CANDIDATE_CLEARED_TRIAGE`, stands unretracted for the genuinely
agent-driven case: it never found a genuinely agent-driven, zero-paid-cost path.

This session's user identified that autofde-lab already has one: a real, live, local,
non-paid model server (`~/turbo-fieldfare`'s TurboFieldfare/Gemma server,
`http://127.0.0.1:8080/v1`, model id `gemma-4-26b-a4b-it`, OpenAI-compatible), already wired
into this repo's own DSPy advisory layer at
`src/autofde_lab/hub/solver/dspy_policy/dspy_policy.py`'s `default_lm()`. Five parallel Explore
investigations this session confirmed, from source, that Harbor's `terminus-2` agent supports a
pluggable LiteLLM backend via `--ak api_base=...`, with zero fallback to any paid credential.
This document records Stage 1 of the resulting plan: get a genuinely agent-driven Harbor trial
running against that local server at all, on Harbor's own simplest bundled task, before
attempting anything harder.

Six internal GymAct fixtures reaching real `Level4AliveEvidence`
(`docs/level4-migration-matrix.md`) are unaffected and unrelated to this document — cited only
for context, not re-derived here.

## Non-negotiable safety scope, stated up front

`ANTHROPIC_API_KEY` and `ZAI_API_KEY` were explicitly scrubbed from the subprocess environment
before every `harbor run` invocation below, and `HARBOR_TELEMETRY=0` was set. LiteLLM's
`hosted_vllm` provider has no fallback to any paid provider — confirmed from source in a prior
investigation this session, restated, not re-verified, here.

## Three real attempts, in order — two honest failures, then success

All three commands were run from `vendor/gyms/harbor`.

### Attempt 1 — `api_base` missing `/v1`, real 404

```bash
harbor run \
  --agent terminus-2 \
  --model hosted_vllm/local-model \
  --ak api_base=http://127.0.0.1:8080 \
  --path examples/tasks/hello-world \
  -o jobs
```

Real output:

```text
litellm.llms.custom_httpx.http_handler.MaskedHTTPStatusError: Client error '404 Not Found' for
url 'http://127.0.0.1:8080/chat/completions'
```

Real bug: LiteLLM's `hosted_vllm` provider posts to `<api_base>/chat/completions` literally —
the TurboFieldfare server only implements `/v1/chat/completions`. Fix: include `/v1` in the
`api_base` value itself.

### Attempt 2 — placeholder model name, real 404 from the server itself

```bash
harbor run \
  --agent terminus-2 \
  --model hosted_vllm/local-model \
  --ak api_base=http://127.0.0.1:8080/v1 \
  --path examples/tasks/hello-world \
  -o jobs
```

Real output:

```text
litellm.NotFoundError: Hosted_vllmException - {"error":{"param":"model","message":"requested
model is not available","type":"invalid_request_error","code":"model_not_found"}}
```

Real bug: the placeholder model name `local-model` doesn't match what the server actually
serves. Fix: use the real, confirmed model id `gemma-4-26b-a4b-it` (confirmed earlier this
session via `curl http://127.0.0.1:8080/v1/models` ->
`{"data":[{"id":"gemma-4-26b-a4b-it",...}]}`).

### Attempt 3 — real success

```bash
harbor run \
  --agent terminus-2 \
  --model hosted_vllm/gemma-4-26b-a4b-it \
  --ak api_base=http://127.0.0.1:8080/v1 \
  --ak model_info='{"max_input_tokens":32768,"max_output_tokens":4096,"input_cost_per_token":0,"output_cost_per_token":0}' \
  --path examples/tasks/hello-world \
  --job-name autofde-lab-level4-harbor-terminus2-hello-world-v3 \
  -o jobs
```

Real CLI output:

```text
  1/1 Mean: 1.000 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0:01:27 0:00:00
adhoc • terminus-2 • gemma-4-26b-a4b-it
┏━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┓
┃ Trials ┃ Exceptions ┃  Mean ┃
┡━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━┩
│      1 │          0 │ 1.000 │
└────────┴────────────┴───────┘
Reward: 1.0 | Count: 1
Total runtime: 1m 27s
```

## Real, verified result

Real result file, under the `--job-name` from Attempt 3 above:
`jobs/.../hello-world__Q7JV4qH/result.json`.

- `agent_info`: `{"name": "terminus-2", "version": "2.0.0", "model_info": {"name":
  "gemma-4-26b-a4b-it", "provider": "hosted_vllm"}}`
- `verifier_result`: `{"rewards": {"reward": 1.0}}`
- `agent_result`: `n_input_tokens: 5729, n_cache_tokens: 4710, n_output_tokens: 909,
  cost_usd: null`
- `agent_result.metadata`: `n_episodes: 4` (4 real LLM round-trips),
  `api_request_times_msec: [27813.38, 7010.35, 3746.46, 4003.11]` (real local-inference
  latencies, consistent with a laptop-hosted small model, not a network API call)
- Task: bundled `examples/tasks/hello-world` (`instruction.md`: "Create a file called
  hello.txt with 'Hello, world!' as the content."), **not** a public/leaderboard benchmark.

Real terminal transcript
(`jobs/.../hello-world__Q7JV4qH/agent/terminus_2.pane`), confirming the local model genuinely
reasoned about the task itself — this is `terminus-2`, the genuine agent, not the `oracle`
agent from `docs/2026-08-08-first-external-benchmark-score-attempt.md`'s superseded attempt:

```text
root@39fc20711b5f:/app# echo "Hello, world!" > hello.txt
root@39fc20711b5f:/app# cat hello.txt
Hello, world!
```

## What this does and does not establish

**Does establish:** a genuine (non-oracle-replay), local-LLM-driven agent decision loop, scored
by Harbor's real, unmodified verifier (a real pytest assertion running inside the container),
with zero paid API calls and zero ambient-credential use — `ANTHROPIC_API_KEY`/`ZAI_API_KEY`
explicitly scrubbed from the subprocess environment, and `hosted_vllm`'s own LiteLLM provider
confirmed from source (prior investigation this session) to have no fallback to any paid
provider.

**Does not establish:** a SOTA-comparable score. `hello-world` is Harbor's own bundled toy
example, not a public benchmark with a leaderboard. This is a real evidence-chain/plumbing
checkpoint — `PARTIAL_ALIVE`, per `.claude/rules/standing-law.md` — not a SOTA claim, and must
never be described as one.

**Status in the larger plan:** this is Stage 1 of a larger, still-in-progress plan. Stage 2 — a
real, harder, externally-recognized-benchmark attempt against `sregym`'s K8s-remediation problem
`misconfig_app_hotel_res`, via the `stratus` driver, against the same local server — is in
progress as of this document and not yet complete. No Stage 2 result is reported here.

## See also

- `docs/2026-08-08-first-external-benchmark-score-attempt.md` — the prior `BLOCKED` attempt this
  document's Stage 1 reopens with a genuinely agent-driven, non-oracle path.
- `docs/level4-migration-matrix.md` — the six-gym internal `Level4AliveEvidence` architecture
  record, cited for context only, not re-derived here.
- `.claude/rules/standing-law.md` — the status vocabulary this document's verdict line uses.
- `.claude/rules/absence-is-not-evidence.md` — why this document names the exact scope of what
  the reward signal does and does not prove, rather than generalizing a single trial.
- `src/autofde_lab/hub/solver/dspy_policy/dspy_policy.py` — this repo's own existing
  `default_lm()` wiring to the same TurboFieldfare server used here.
