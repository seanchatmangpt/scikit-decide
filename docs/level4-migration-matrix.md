# Level 4 gym migration matrix

Real census, this session, of every GymAct-capable provider reachable from `level4_gymact_bridge.py`, the sibling `~/gymact` package's `gyms/` directory, and `autofde_lab.hub.domain.*` bridges — gathered by 30 real, read-only census agents (out of ~44 dispatched; the workflow was killed mid-run at 46 agents dispatched/31 completed, `w9lme71pm`/`wf_a0bbfca7-d50`) plus 3 real tracer-bullet trials run directly. Every row below is either a real trial result or a real-source-inspection census result — none is inferred from memory.

**Superseded in coverage, not in content, by `docs/2026-08-08-level4-gym-census-round2.md`**: a second, complete (57/57, zero kills) census workflow found 74 total gyms (up from this round's ~44), including a real 5-category goal-oracle semantic taxonomy for the `VendorBenchmarkProvider` family and a second, separate, family-wide authority-threading gap discovered after the constructor fix below landed. Read that document for the current full picture; this document's own 5 `LEVEL4_ALIVE` tracer bullets and their trial identities remain the authoritative record of what's actually been run.

## Level 4 ALIVE (6)

| Gym | Trial identity | Real finding |
|---|---|---|
| `resource_flow` (TracerBulletA) | seed `3979297810`, trial `5e10eecf-52e6-463f-893c-efa0da93d5a7` | `Conforms: True`, 14/14 falsifiers, destructive verification. See `docs/2026-08-08-level4-shacl-tracer-bullet.md`. |
| `lock_and_key` (TracerBulletB) | seed `3979297810`, `depth=2`, `probe_budget=40`, trial `7ee7eaec-3eff-4b07-b796-6bff521c0ece` | Same, zero kernel edits from A. |
| `switchboard` (TracerBulletC) | seed `3979297810`, `probe_budget=40`, trial `b95bea45-4b18-48f7-9321-934e325ce443` | Same, zero kernel edits from A/B, run by a census workflow agent through the unmodified CLI. |
| `cube_counter` (TracerBulletD) | seed `3979297810`, trial `bc560e63-0844-4245-9382-9a9828f3f4da` | Reached only after a real fix (see below) to a discovery/planning-layer bug -- **zero changes** to the evidence kernel itself. `Conforms: True`, real severed-edge non-vacuousness check flips to `False`. Committed plan `(increment, increment, increment)`, deriving the unobserved goal state `counter=3` from a learned `+1` law rather than having directly probed it. |
| `cube_container_counter` (TracerBulletE) | seed `3979297810`, trial `c6398f4e-6328-4f8c-a01f-23e9cca63cdd` | **The repair-leverage confirmation.** Same `_dimensions_with_arithmetic_evidence` fix, applied to `cube_counter` alone, transferred to this second, structurally distinct, Docker-backed gym with **zero further code changes** -- real `EXECUTED`, real `Level4AliveEvidence`, committed plan `(increment, increment, increment)`, `Conforms: True`, severed-edge check flips to `False`. First observed instance of one basis-level repair generalizing to a previously untested gym. |
| `memory` (TracerBulletF) | seed `4102`, trial `9c2245d4-ffff-4d3f-ae4f-14f33e60c98c` (interactive; `tests/domains/python/test_level4_memory_gym_chicago.py`'s own module-scoped fixture reruns it independently under pytest) | **First genuinely new gym wired since the `FIVE_GYM_KERNEL_GATE` checkpoint**, not a repair-leverage rerun of an already-wired one. In-process `gymact.providers.MemoryProvider` (no Docker, no network -- the structurally simplest gym in the manifest). Required a new, explicit `_predict_memory` postcondition oracle (`level4_crown.py`) routed through a dedicated dispatch branch placed *before* the generic `_COUNTER_DELTAS` fallback -- design review had flagged that falling through to the generic branch would numerically coincide on `increment` but wrongly attach a `solved` key `MemoryEnvironment` never publishes, spuriously failing every step. Real `EXECUTED`, real `Level4AliveEvidence`, `representation_losses == {}` (no continuous/unrepresentable dimension, unlike `cube_counter`'s `reward`), `Conforms: True` through the **unmodified** evidence kernel, severed-edge check flips to `False`. |

`SIX_GYM_KERNEL_GATE = PASSED`: `level4_witness.py`, `verify.py`, and `ontology/shapes/{level4,authority,planning}.shacl.ttl` are byte-identical across all six -- confirmed via `git status --short src/autofde_lab/evidence/ ontology/shapes/` showing zero diff at the point `memory` was projected. Zero provider-specific branches exist in any of them (`grep -n "resource_flow\|lock_and_key\|switchboard\|cube_counter\|memory\|provider_key ==" src/autofde_lab/evidence/*.py` → zero matches). `predict_step_postconditions`/`model_goal_predicate` in `level4_crown.py` DO carry a `memory`-specific branch each -- that is expected and correct: those two functions are the crown's per-gym oracle/goal layer, outside the frozen `autofde_lab.evidence` kernel by design.

### The `cube_container_counter` leverage result, precisely

The first attempt (colima's daemon unreachable) produced a second, real, independent finding: `_EXECUTE_SCRIPT` (the actuation-stage bridge) accessed `m.episode.episode_id` without checking `m.accepted` first -- unlike the discovery-stage bridge, which does check -- so any actuation-time materialize refusal crashed `run_real_trial` with an unhandled `AttributeError` instead of the typed `TrialReport` this module's own design promises everywhere else. Fixed: `_EXECUTE_SCRIPT` now returns a typed `{"materialize_failed": True, "reason": ...}` result on refusal; `commit_and_execute` raises a new `ActuationMaterializeRefused`; `run_real_trial` catches it and returns `BlockedEvidence(reason=...)` / `outcome="ACTUATION_MATERIALIZE_REFUSED"`. Verified live in isolation (`commit_and_execute` called directly against the real refusing provider) before colima was touched, and with a real, deterministic, environment-independent trigger (an unregistered `MaterializationIntent.provider` name, refused by `gymact`'s own kernel with `UNKNOWN_PROVIDER`) in `tests/domains/python/test_execute_bridge_materialize_refusal_chicago.py`.

With the user's explicit authorization, colima was restarted (`colima restart`; it had reported itself "already running" while its socket was dead -- a hung daemon, not merely a stopped one) and the **identical, unmodified** trial was rerun: real `EXECUTED`, confirming the leverage hypothesis directly rather than leaving it open. Both runs (blocked, then alive) are the real controlled experiment -- not two unrelated data points.

### The `cube_counter` fix, precisely

`cube_counter` failed for a reason entirely outside the evidence kernel: `state_typing._is_categorical_id()` reclassified `counter` from `INTEGER` to `CATEGORICAL_ID` the moment `decrement` produced a negative value, stripping its arithmetic semantics before effect induction ever ran -- confirmed directly by calling `classify_observation()` on the real trial's observations. The heuristic exists to fix a real, different bug (`lock_and_key`'s `held_key=-1` "no key held" sentinel wrongly getting arithmetic treatment); its own docstring's stated premise ("counter/raw/output/locks_open... never negative") is exactly what `cube_counter`'s own `decrement` action falsifies.

Fix (`typed_induction.py`, `_dimensions_with_arithmetic_evidence`): a `CATEGORICAL_ID`-classified dimension is reclassified back to arithmetic-eligible only when some single action was observed succeeding from **>= 2 distinct pre-state values** of that dimension with the **same delta each time** -- real transition evidence outweighing the value-set coincidence. The bar is set precisely so it cannot reopen the original bug: `held_key` never clears it for any of its actions (`pick_key[key=K]` is only ever observed from the one pre-state `held_key=-1`; `drop_key`/`open_lock` set an absolute value from varying pre-states, an inconsistent "delta" by construction). Verified live, both directions, on real trial data:

- `cube_counter`: `counter` regains `INTEGER`/metric standing; `increment.effects['counter'].delta == 1.0`; `search_plan_typed` derives `(increment, increment, increment)` reaching `counter=3` **without `counter=3` ever having been observed** during the bounded probe budget.
- `lock_and_key`: `held_key` stays `CATEGORICAL_ID`, non-metric; every action's effect on it stays an absolute assignment, never a delta -- the paired regression guard holds.

### Repair leverage to `cube_container_counter`: resolved (see "Level 4 ALIVE" above)

The first attempt genuinely blocked on `BLOCKED:EXTERNAL_COLIMA_DAEMON_UNREACHABLE` (`cube.infra_local._launch_docker_service`'s `docker ps -q` call returning exit 1, root-caused to the exact command -- colima's daemon had gone unreachable between an earlier successful `docker info` check and this trial's actuation step). Per `.claude/rules/absence-is-not-evidence.md` that was correctly recorded as genuinely open, not a quiet pass or fail, since discovery/typed-search reaching commit was suggestive but not conclusive. With explicit authorization the daemon was restarted and the identical, unmodified trial reran to a real, conclusive `EXECUTED` -- see TracerBulletE above.

Chicago-style test: `tests/domains/python/test_typed_induction_arithmetic_standing_chicago.py`, 4/4 real (real `RealBlindEnvironment`/`_discover_by_probing` against both real providers, real `induce_typed_domain`, real `run_real_trial` end-to-end, zero mocks). Attribution of two pre-existing, unrelated failures in `test_level4_crown_unmodellable_trial_chicago.py` confirmed precisely by `git stash`-ing the fix and re-running: identical failures occur with or without it.

## Real, precisely diagnosed: not yet ALIVE

| Gym | Real finding |
|---|---|
| `cube_container_counter` | Census: `SAFE_EXECUTABLE`, `estimated_migration_difficulty: low`, real dependencies verified live (Docker daemon reachable via colima, `vendor/gyms/cube-standard` submodule checked out, module imports cleanly in `~/gymact/.venv`). Shares `cube_counter`'s goal predicate/oracle **and its `counter` dimension** -- now likely fixed by the same `_dimensions_with_arithmetic_evidence` change (see "Level 4 ALIVE" above), not yet run through `run_real_trial` this session to confirm. |

`cube_counter` moved from this table to "Level 4 ALIVE" above after a real, precisely diagnosed fix -- see that section for the full mechanism.

## ADAPTER_MISSING (19)

Two distinct sub-populations:

**Individually unwired GymAct providers** (`gymnasium_env`, `terraform_docker_apply`, `ggen_legacy`, `mcp_client_session`, `inspect_evals`, `discovered`) — each absent from `level4_gymact_bridge.py`'s `_PROVIDERS` dict; adding an entry is gym/capability-layer work, not a kernel change.

**The `VendorBenchmarkProvider` family** (`agentbench`, `agentlab`, `asb`, `assetopsbench`, `azuregoat`, `bountytasks`, `crmarena`, `cube-harness`, `cube-standard`, `cybergym-e2e`, `doomarena`, `aiopslab` — 12 of this census's sample; the real class covers 52 pinned vendor revisions total per `gymact.gyms.vendor_benchmarks.VENDOR_REVISIONS`, so most weren't individually censused before the workflow was killed): **one shared, precisely diagnosed root cause**, confirmed by direct source inspection (`agentdojo`'s census result, representative): `level4_gymact_bridge.py`'s `_BRIDGE_SCRIPT` always instantiates providers zero-arg (`provider_cls()`), but `VendorBenchmarkProvider.__init__(self, name: str)` requires a positional `name` — every vendor in this family hits `TypeError: __init__() missing 1 required positional argument: 'name'` before `materialize()` is even reached. This is real DCM leverage: one bridge-construction fix is a prerequisite for all 52, but **not sufficient by itself** — see the two further gaps below, both real and separately diagnosed, not yet collapsed into a smaller basis:

1. **No goal predicate or independent postcondition oracle exists for any vendor benchmark.** `model_goal_predicate`/`predict_step_postconditions` in `level4_crown.py` both hard-raise `UNSUPPORTED_PROVIDER_FOR_GOAL`/`UNSUPPORTED_PROVIDER_FOR_POSTCONDITION_PREDICTION` for any `provider_key` outside the 5 already-wired names. `VendorBenchmarkEnvironment.observe()` returns only `{vendor, revision, root, last_result}` — no task id, no pass/fail signal, no security-check outcome; a real goal predicate per vendor would need each benchmark's own evaluator/expected-state/test-oracle output, which is not currently surfaced through the generic `run-native` capability at all.
2. **Real, materially higher risk than any currently-wired gym.** `VendorBenchmarkEnvironment.actuate()`'s one capability (`run-native`) executes an arbitrary native subprocess (`asyncio.create_subprocess_exec`) bounded only by an argv[0]-path guard — it can write files anywhere under the vendor checkout and make real outbound LLM-API calls (OpenAI/Anthropic/Cohere/Google, confirmed present in several vendors' own dependency lists) using whatever credentials are ambient. This is qualitatively different from the 5 wired gyms, which mutate only in-memory episode state. Per this session's own explicit instruction: do not let `SUPPORTED` become `EXECUTE IT` — this family needs an explicit budget/authority abstraction before any real actuation, not just a constructor fix.

## AUTHORITY_REQUIRED (2)

`cloudgoat`, `cloudfoxable` — real cloud-infrastructure attack-simulation benchmarks; census flags real-world mutation risk requiring deliberate authority scoping beyond the current `AllowListAuthorityResolver({one static ref})` pattern.

## CAPABILITY_MISSING (5)

`azuregoat_privesc`, `browsergym`, `codebase`, `kubernetes_reconciliation`, `multicloud` — registered in the sibling `gymact` package or as a separate autofde-lab bridge (`azuregoat_privesc`), but not reachable through the existing `RealBlindEnvironment`/`_PROVIDERS` construction path for provider-specific reasons (each census result names its own).

## DEPENDENCY_BLOCKED (1)

`androidworld` — real external dependency absent locally.

## Not captured

The workflow was killed (`status: killed`, not `completed`) partway through the census fan-out — 31 of 46 dispatched agents returned a result (one, `gym_id: null`, was malformed/truncated and is not included above); the remaining ~13-15 in-flight census agents and the entire migration-attempts phase never ran. Given the `VendorBenchmarkProvider` family alone covers 52 pinned vendor revisions (most uncensused), the true total gym surface is larger than this table shows. This table is a real, honest partial census, not a complete one.

## What this session did NOT do, deliberately

- Did not fix the `_BRIDGE_SCRIPT` constructor-signature mismatch. It is a real, precisely diagnosed, single-point defect blocking ~52 vendor benchmarks, but fixing it without also resolving the goal-oracle and authority gaps would just move the failure mode from "won't construct" to "constructs, then either can't be graded or can execute unbounded native commands" — not real progress.
- Did not hand-write per-vendor goal predicates. Per this session's own explicit instruction, that would be exactly the `if vendor == "foo": ...` anti-pattern this kernel's design forbids. Whether vendor benchmarks' own evaluator/expected-state/test-oracle output can be projected through a small number of shared semantic categories (not 52 individual cases) is real, unstarted design work.
- Did not attempt `cube_container_counter` (its dependency chain — Docker/colima — makes a failed attempt more expensive to clean up than `cube_counter`'s pure in-memory case). Now that `cube_counter`'s `counter`-classification bug is fixed and shared code paths confirmed, this is next to try, not next to root-cause.

## See also

- `docs/2026-08-08-level4-shacl-tracer-bullet.md` — the three real ALIVE tracer bullets, in full.
- `docs/STATUS.md` Pass 10 — the ledger row.
- Repo task #21 / #41 — the pre-existing "lock_and_key: prefix-keyed induction + CATEGORICAL_ID dimensions" item this pass's `cube_counter` fix sharpened and closed one real failure mode of; task #21 itself (`lock_and_key`'s own prefix-keyed relational induction, a separate concern from dimension classification) remains open.
