# Lane B — extracting the DecisionBasis, wrapping current hardcoded behavior

**Verdict: real, tested extraction complete.** Not architecture search, not SOTA validation --
the missing capability itself, made addressable: `D = Model x Planner x ToolPolicy x
RepairPolicy x VerificationPolicy x Budget`, with real, cited D0 points for both real agent-
driven benchmark attempts this session ran (`harbor`/`terminus-2`, `sregym`/`stratus`), and a
real materializer proving each D0 reproduces the exact command this session actually executed.

## Why this exists

A prior real finding this session (`docs/2026-08-08-first-external-benchmark-score-attempt.md`
and the follow-up local-server investigation) established that only `Model` had ever been
proven swappable in this repo's real external-benchmark attempts -- every other axis (which
decision loop, which tools, whether/how a failed attempt gets retried, which evaluator, what
resource ceiling) was an unexamined, hardcoded fact about whichever vendor driver happened to
be invoked. That absence is itself the finding that matters: it is not resolved by any single
benchmark trial passing or failing, and does not need to wait for one.

## Extraction discipline: wrap, don't invent

Every field on every dimension traces to a real, cited fact about already-executed or
already-configured real invocations -- never a guessed default:

- **`sregym`/`stratus`** (`src/autofde_lab/sota/materialize_sregym.py`): tool/repair/step
  fields are read directly from the real, checked-out
  `vendor/gyms/sregym/clients/stratus/configs/mitigation_agent_config.yaml` at call time, not
  duplicated as a second, drift-prone copy (`.claude/rules/no-dual-bookkeeping.md`). Real
  values found: `retry_mode: validate`, `max_retry_attempts: 10`, `max_step: 20`, and an
  8-tool real action space (`wait_tool`, `get_traces`, `get_services`, `get_operations`,
  `get_dependency_graph`, `get_metrics`, `exec_kubectl_cmd_safely`, `f_submit_tool`) -- notably
  **no Loki/log-query tool**, even though `sregym`'s `mcp_server/` wires one up generally; a
  real, cited absence, not an oversight papered over.
- **`harbor`/`terminus-2`** (`src/autofde_lab/sota/materialize_harbor.py`): grounded against
  both `terminus_2.py`'s source AND the real, already-persisted `result.json`/`trajectory.json`
  from this session's successful (reward 1.0) `hello-world-v3` trial. Real findings:
  `n_episodes` counts main-loop LLM calls only (confirmed: 4 episodes = 2 `bash_command` +
  2 `mark_task_complete` confirmations, exact match to the real trajectory); the tool policy is
  a **single** implicit action (free-text keystrokes via a JSON-object prompt contract, not
  native tool-calling -- the source's own comment says so explicitly); repair is a real
  3-layer system (deterministic JSON auto-fix -> bare re-prompt -> tenacity 3-attempt retry for
  transport errors), never LLM-driven replanning; the real governing budget was the task's
  120s wall-clock timeout, not the 1,000,000-episode default cap (never close to reached).

## What was built

- `src/autofde_lab/sota/decision_basis.py` -- the frozen vocabulary (`Model`, `Planner`,
  `ToolPolicy`, `RepairPolicy`, `VerificationPolicy`, `Budget`, `DecisionBasis`).
- `src/autofde_lab/sota/materialize_sregym.py` -- `current_sregym_stratus_basis()` (reads the
  real vendor YAML) + `materialize_sregym_invocation()` (D -> real argv/env).
- `src/autofde_lab/sota/materialize_harbor.py` -- `current_harbor_terminus2_basis()` (cited
  against real source + the real trial artifact) + `materialize_harbor_invocation()`.
- `tests/sota/test_decision_basis_sregym_chicago.py`,
  `tests/sota/test_decision_basis_harbor_chicago.py` -- 10/10 real, passing, zero mocks. The
  load-bearing assertion in each: the materializer's output is byte-for-byte identical to the
  real command line this session actually ran -- proving the abstraction is faithful to
  current behavior, not an invented one.

## The one hard constraint, not a free dimension

`VerificationPolicy` is deliberately not treated as something a search may vary away from "the
benchmark's own real, unmodified evaluator" -- this repo's own
`.claude/rules/absence-is-not-evidence.md` makes that a structural requirement, not a
preference. `sregym`'s internal "weak oracles" (`AlertOracle`, `ClusterStateOracle`, used by
`RepairPolicy`'s `validate` retry mode to decide whether to keep retrying) are real and are
part of the `RepairPolicy` dimension -- they must never be conflated with the final
`VerificationPolicy` verdict (`IncorrectImageMitigationOracle.evaluate()` for
`misconfig_app_hotel_res`).

## What this explicitly does not do yet

- No architecture search. `D0` for each driver is exactly today's hardcoded point, nothing
  else -- no second point has been generated or run.
- No aggregate benchmark matrix. Only the one already-in-flight problem
  (`misconfig_app_hotel_res`) has a `DecisionBasis` point; the other 33 "Ported" problems (and
  the other 56 in `sregym`'s full 90-problem suite) are real, catalogued, and unexercised.
- No `D0` evidence attached yet for the `sregym` point -- the real, live `misconfig_app_hotel_res`
  trial this D0 describes (Lane A) was still running when this document was written; its real
  PASS/FAIL/BLOCKED result becomes `D0`'s first attached observation once it lands, per this
  session's own explicit two-lane instruction (extract the basis now; do not wait for the run,
  and do not let the run's outcome retroactively justify or invalidate the extraction).

## See also

- `docs/2026-08-08-first-external-benchmark-score-attempt.md` -- the triage that first
  surfaced "only Model is swappable" as a real, cited finding.
- `docs/2026-08-08-local-server-agent-driven-harbor-checkpoint.md` -- Stage 1's real,
  successful harbor/terminus-2 checkpoint this D0 is grounded against.
- `.claude/rules/no-dual-bookkeeping.md` -- why `materialize_sregym.py` reads the real vendor
  file instead of hardcoding a copy.
- `.claude/rules/absence-is-not-evidence.md` -- why `VerificationPolicy` is a hard constraint.
