# sregym/stratus + local server: real terminal result for the LLM-driven attempt

**Verdict: `BLOCKED:LOCAL_MODEL_TOOL_CALLING_REQUEST_INCOMPATIBLE`** (precise reason below) --
recorded as D0's first attached observation, closing the LLM-driven path of task #50, not the
task itself. Real, cited, run this session. Not further chased past this point, per this
session's own explicit correction: architecture work does not wait on, or get replaced by,
indefinitely debugging one external vendor's LLM tool-calling stack.

## What actually happened, in order

Six real infrastructure defects were found and fixed live this session to get a real kind
cluster + hotel-reservation deployment to a genuine `diagnosis`-stage-ready state (Docker
daemon `default-ulimits`, a stale kube-system namespace-controller cache after a daemon
restart, a hung containerd on `kind-worker2`, kernel-wide `fs.inotify.max_user_instances=128`
exhaustion, a process-detachment mistake on relaunch, and a `--max-context 4096` non-default
model server flag). Each is a real, root-caused, verified fix -- see the prior pass's evidence
in the conversation transcript; this document covers only the terminal LLM result that follows
once those were cleared.

With the cluster genuinely `Ready for submission. Current stage is: diagnosis` and the real
`stratus` diagnosis agent launched against the local TurboFieldfare/Gemma server (confirmed
healthy, `--max-context 65536`, the repo's own documented default and max), the diagnosis agent
crashed on its first LLM call:

```
ERROR    llm_backend.get_llm_backend - Bad request error - request is malformed:
         litellm.BadRequestError: OpenAIException - generation failed
ERROR    llm_backend.get_llm_backend - Error details: No response details
ERROR    llm_backend.get_llm_backend - This often happens when tool_calls don't have
         matching tool response messages.
```

Real, on-disk terminal artifact: `results/0808_2353/stratus/misconfig_app_hotel_res/
misconfig_app_hotel_res_stratus_results.csv` contains only the header row
(`attempt,problem_id`) -- no reward data. The harness's own driver completed and wrote this
empty result (`✅ Completed misconfig_app_hotel_res: results={}`, return code 1) -- i.e. the
outer benchmark loop terminated cleanly on a real, unhandled crash inside the agent subprocess,
not a hang.

## Hypotheses tested this session, each with a real result

| Hypothesis | Test | Result |
|---|---|---|
| Context window too small | Restarted the server at `--max-context 65536` (8x the prior `4096`), relaunched the identical run | **Ruled out** -- identical crash at the identical `diagnosis_agent.py:66` call site |
| Too many tools (7-tool diagnosis config) confuses the server | Direct `curl` to `http://127.0.0.1:8080/v1/chat/completions` with the real 7-tool schema from `diagnosis_agent_config.yaml` | **Ruled out** -- server returned a real, valid `tool_calls` response (`get_services`) |
| Prompt too long | Measured `diagnosis_agent_prompts.yaml`: 81 lines, 5420 chars, ~1300-1500 tokens | **Ruled out** -- far under any real context ceiling |
| macOS unified log has more server-side detail | `/usr/bin/log show --predicate 'process == "TurboFieldfareServer"' --last 5m` | **Blocked**, not ruled out -- `Operation not permitted` (elevated macOS permission unavailable this session) |

## Real, cited, leading candidate cause -- not further chased

`llm_backend/get_llm_backend.py` (read this session, lines 39-40 and 107-110):

```python
litellm.drop_params = True
litellm.modify_params = True
...
llm = ChatLiteLLM(**model_config)
if tools:
    llm = llm.bind_tools(tools, tool_choice="auto")
```

This is a real, sourced difference from the direct `curl` replication above: LangChain's
`bind_tools(tools, tool_choice="auto")` plus LiteLLM's global `drop_params`/`modify_params`
mutate the outgoing request in ways the hand-built `curl` payload never exercised (candidate
concrete differences, none yet confirmed: an explicit `tool_choice` field, `parallel_tool_calls`,
or LiteLLM's own schema-normalization pass hitting a code path TurboFieldfareServer's
OpenAI-compatible surface doesn't handle). This is a real, named, falsifiable candidate -- not
a guess dressed as a finding -- but it is **not chased further this session**, per this
session's own explicit correction: continuing to debug one external vendor's LLM tool-calling
stack indefinitely is exactly the "default to LLM" behavior being corrected, not the two-lane
architecture work the standing goal actually requires.

## Disposition

- **D0 (sregym/stratus)** in `src/autofde_lab/sota/materialize_sregym.py`: this is its first
  attached observation -- `BLOCKED:LOCAL_MODEL_TOOL_CALLING_REQUEST_INCOMPATIBLE`, not
  `PASS`/`FAIL` on the actual remediation task, because the agent never reached a point where
  `IncorrectImageMitigationOracle.evaluate()` could run. Per `.claude/rules/absence-is-not-
  evidence.md`, this is recorded as its own typed value, not coerced into either a pass or a
  fail.
- The live kind cluster / hotel-reservation deployment this observation was captured against has
  since torn itself down (`kubectl get pods -n hotel-reservation` / `-n observe` both now report
  "No resources found") -- re-provisioning is required before any further live attempt against
  this exact D0 point, whether LLM-driven or planner-driven.
- Task #50 ("Stage 2: sregym real remediation task via stratus + local server") is retitled to
  scope only the LLM-driven sub-attempt closed by this document; a new task carries the
  planner-driven pivot this session's explicit correction ("use all the planning available")
  requires next.

## See also

- `docs/2026-08-08-decision-basis-lane-b.md` -- the DecisionBasis this observation attaches to.
- `.claude/rules/absence-is-not-evidence.md` -- why `BLOCKED` is its own typed value, not
  coerced into pass/fail.
- `.claude/rules/standing-law.md` -- the `BLOCKED:<reason>` vocabulary this verdict uses.
