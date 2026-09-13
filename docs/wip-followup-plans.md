# WIP Follow-up Plans

Drafted by parallel agents; scoped implementation plans for the deferred WIP categories from the WIP-closure plan (see /Users/sac/.claude/plans/launch-5-lumen-explore-fizzy-crane.md "Explicitly out of scope" section). Not yet implemented — for review/prioritization.


---

## Scheduling mixin architecture

# Follow-up implementation plan: `builders/domain/scheduling` architectural TODOs

Scope: the ~15 TODOs enumerated in the task, in `scheduling_domains.py`, `task_duration.py`, `resource_costs.py`, `preallocations.py`. No code in this document — ordering, dependencies, and test shapes only.

## Cluster map (what actually depends on what)

There are 4 independent clusters. Within a cluster, items are ordered; across clusters, order doesn't matter except where noted.

- **A. Applicable-actions dispatch** — `scheduling_domains.py` L271 (isinstance dispatch), L1369 (single-resource-unit-per-task limitation), and `preallocations.py` (applicable-actions integration)
- **B. Resource-consumption tracking for ongoing tasks** — L434/453 (`resource_used` not updated for variable-consumption tasks), L739/847-849 (sampled-duration stopgap for resume)
- **C. Cost/objective model** — `resource_costs.py` (cost → transition cost) and L1170 (multi-objective weighting)
- **D. Duration/distribution semantics** — `task_duration.py` L25, L57, L114, and the dead-code question at L309 (`sampled_durations` dict)

C depends on nothing but is logically downstream of B (transition cost reads `resource_used`, so getting B right first avoids re-deriving cost math against a value that's about to change). A and D are independent of everything else and of each other.

---

## Cluster A — Applicable-actions dispatch

### A1. `scheduling_domains.py` L271: isinstance-based dispatch in `_get_applicable_actions_from`

Current code:
```python
if isinstance(self, WithoutResourceSkills) and isinstance(self, WithoutResourceUnit):
    return SchedulingActionSpace(domain=self, state=memory)
else:
    return SchedulingActionSpaceWithResourceUnitSamplable(domain=self, state=memory)
```
This is a real design decision, not just style: the mixin chain (`WithoutResourceSkills`/`WithResourceSkills`, `WithoutResourceUnit`/`WithResourceUnits` in `resource_type.py`, `skills.py`) already encodes exactly this distinction at the type level, but the action-space selection re-derives it at runtime via `isinstance` instead of letting the mixin composition select the right action-space class directly (e.g. a `_get_applicable_actions_from` override living on `WithoutResourceUnit`/`WithResourceUnits` themselves, following the same override-point pattern used elsewhere: `_get_action_space_`, `_get_observation_space_`).

**Decision needed before touching this**: does the action-space class become a mixin-provided override point (each resource-mixin branch implements its own `_get_applicable_actions_from`), or does the domain keep a single dispatch point but replace `isinstance` with a declarative capability flag/class attribute set by each mixin (e.g. `_uses_resource_units: bool`)? The former is more idiomatic given the rest of the codebase's three-tier method-naming/override-point convention; the latter is a smaller diff. Pick one before starting — this repo's own convention (mixins own their override points) argues for the former.

**Test**: build two fixture domains — one composing `WithoutResourceSkills`+`WithoutResourceUnit` (mirrors `SingleModeRCPSP` in `tests/scheduling/test_scheduling.py`), one composing `WithResourceUnits` (mirrors `MultiModeMultiSkillRCPSP`). Call `domain.get_applicable_actions(domain.reset())` on each and assert the returned space is an instance of the expected concrete `SchedulingActionSpace*` class and that `.get_elements()` returns a non-empty, correctly-typed list of `SchedulingAction`. No mocking — this is exactly `tests/scheduling/test_scheduling.py`'s existing `ToyRCPSPDomain`/`ToyMS_RCPSPDomain` pattern, extended to assert on the space type.

### A2. L1369: `SchedulingActionSpaceWithResourceUnit`/`...Samplable` only correct for 1-resource-unit-per-task

The comment states the enumeration strategy (enumerate individual "worker" resource units) breaks down when a task needs a *combination* of resource units. Fixing this needs a design decision: either (a) enumerate valid *combinations* of resource units per task/mode up front (combinatorial blowup risk — needs a bound or lazy sampling), or (b) keep enumeration for the single-unit case and add a separate `SamplableSpace`-only strategy (no `EnumerableSpace`) for multi-unit combinations, since `SamplableSpace.sample()` doesn't need the full enumeration. Given `SchedulingActionSpaceWithResourceUnitSamplable` (the one actually used, per A1) is already samplable-only, (b) is the lower-risk path: confirm whether `EnumerableSpace` conformance is actually required anywhere in the solver code paths that reach a multi-unit-per-task domain before doing the combinatorial version.

**Depends on**: A1's dispatch decision (this is one branch of it), and requires a concrete multi-unit-per-task fixture domain, which doesn't appear to exist in `tests/domains/`/`tests/scheduling/` yet — check `MultiModeMultiSkillRCPSP` in `scheduling_domains.py` for whether it already models multi-unit tasks or only multi-skill-single-unit tasks before assuming a new fixture is needed.

**Test**: a fixture domain where a task's mode requires 2 resource units of the same type simultaneously (not 2 different tasks each taking 1). Call `.sample()` (and `.get_elements()` if enumerable is kept) and assert every returned `SchedulingAction.resource_unit_names` has the right cardinality and only contains currently-available units — not a state-machine mock, an actual domain `reset()` + space query.

### A3. `preallocations.py`: cost/preallocation handling should move into domain (applicable actions)

`WithPreallocations._get_preallocations()` returns `dict[task_id, list[resource_names]]` but nothing in `scheduling_domains.py` currently reads it — confirmed by search: no call site for `get_preallocations()` exists outside the mixin file itself and `tests/scheduling/test_scheduling.py`'s import of `WithoutPreallocations` (used only as a base class, never queried). This is genuinely dead wiring, not dead code to delete: the TODO says applicable-actions computation should *consult* it (a preallocated resource should be excluded from another task's candidate resource-unit set, or forced into the owning task's set) inside `get_possible_starting_tasks`/`check_if_action_can_be_started`/`get_resource_used`.

**Depends on**: A1 (whichever dispatch mechanism A1 lands on is where preallocation filtering gets threaded in — likely inside `_get_elements()` of the resource-unit action space, or inside `get_resource_used`/`check_if_action_can_be_started`'s resource-availability check).

**Test**: fixture domain with a task pre-allocated to a specific named resource unit and a second task competing for the same unit type. Assert that `get_applicable_actions()` for the second task never offers the preallocated unit, and that the first task's start action either auto-assigns it or requires it. This is currently untestable (no wiring exists) — this test is the acceptance criterion for the feature, not a regression guard.

---

## Cluster B — Resource-consumption tracking for variable-consumption/resumed tasks

### B1. L434/453: `resource_used` dict not updated for variable-consumption tasks in `update_progress`/`update_progress_uncertain`

Both functions update `tasks_progress[task_id]` but the comment flags that `resource_used`/`resource_used_for_task` isn't refreshed here — meaning a task whose resource draw changes over its lifetime (`ModeConsumption` supports time-varying consumption per `modes.py`'s `get_resource_need_at_time`) will show stale resource usage between the `update_start_tasks` call and the next `update_res_consumption` call. Check whether `update_res_consumption`/`update_res_consumption_uncertain` (which *does* call `get_resource_used(..., time_since_start=...)` and correctly diffs `prev`/`new`) is already called in the same per-step sequence as `update_progress` — looking at `update_time`: yes, `update_progress` then `update_res_consumption` then `update_complete_tasks`, in that order, every step. If `update_res_consumption` runs every step and already reconciles `resource_used_for_task[task_id][r]` against the newly-computed `resource_to_use[r]`, **the TODO may already be resolved by `update_res_consumption`'s existence** and the comment in `update_progress` is stale.

**First action here is not a code change but a verification**: write the Chicago test below before assuming a fix is needed. If it passes as-is, the correct "fix" is deleting the two stale TODO comments (L434, L453), not adding logic.

**Test**: fixture domain with a mode whose `ModeConsumption` resource need varies with `time_since_start` (`ConstantModeConsumption` won't exercise this — need a custom `ModeConsumption` subclass or check if one already exists in `modes.py`). Start the task, step the domain through several `TIME_PR` actions, and after each step assert `state.resource_used[r]` equals the resource's actual need at that `time_since_start`, read via `get_resource_used(...)` directly — not via a mock of `update_res_consumption`.

### B2. L739/847-849: sampled-duration stopgap — `get_latest_sampled_duration` called at start, commented out at resume

`update_start_tasks` (L847) samples+stores a duration via `get_latest_sampled_duration(progress_from=0.0)` and stashes it on the new `Task` object (`sampled_duration`), which `update_progress`'s `get_task_progress(..., sampled_duration=...)` then reads directly from `state.tasks_details[task_id].sampled_duration` — bypassing the `sampled_durations` cache dict entirely for progress computation. At L739, the equivalent resample-on-resume call is commented out, meaning a paused-then-resumed task never gets a fresh duration sample for its remaining portion even in domains where duration should be resampled at `progress_from > 0` (per `UncertainMultivariateTaskDuration`'s docstring, this is explicitly a use case: "you want to sample a different value each time").

**Decision needed**: does resuming a task keep the *original* full-task sampled duration (current de-facto behavior — the `Task.sampled_duration` field is never touched again after `update_start_tasks`), or does it resample a duration for the remaining portion? This is a semantics question the current code never actually decided — it's commented out, not implemented-then-reverted. The right call depends on whether `sampled_duration` in `Task`/`get_task_progress` is meant to represent "duration of the whole task" (supports the current behavior — no change needed except deleting the dead comment block L741-762) or "duration of the current active segment" (requires resampling + `Task` gaining a per-segment duration list, a bigger change touching `Task` in `task.py`, `get_task_progress`, and `_check_time_lags_constraint_on_start`'s `previous_task_end` computation at L930-935 which also reads `sampled_duration` as if it's whole-task).

Given `_check_time_lags_constraint_on_start` already treats `sampled_duration` as whole-task (start + sampled_duration = end), the lower-risk, backward-compatible reading is "whole-task duration, sampled once at start, never resampled" — in which case **this TODO resolves by deleting the 22 lines of commented-out dead code (L741-762) and the TODO comment**, not by implementing resampling. Implementing true resampling-on-resume is a larger semantics change that should be a separate, explicitly-scoped follow-up only if a concrete domain needs it (none in the current hub does, per the RCPSP/MS-RCPSP domains being non-preemptive-by-default or using `WithoutPreemptivity`).

**Depends on**: nothing technically, but should be decided before B1 lands since both touch `update_progress`/duration semantics in the same code path.

**Test (for the "delete dead code" resolution)**: a preemptive fixture domain (composing whatever mixin governs `get_task_preemptivity()` — check `preemptivity.py`) where a task is started, paused mid-progress, resumed, and run to completion. Assert `state.tasks_details[task].sampled_duration` is identical before and after the pause/resume cycle, and that total elapsed active time to completion equals that fixed duration (accounting for `get_task_active_time`'s pause-time subtraction). This nails down the "no resampling" behavior as an explicit, tested contract instead of an implicit one.

---

## Cluster C — Cost/objective model

### C1. `resource_costs.py`: "to be handled by domain (in transition cost)"

`WithModeCosts`/`WithResourceCosts` currently just return static dicts (`get_mode_costs()`, `get_resource_cost_per_time_unit()`) that `_get_transition_value` (around L1132-1168) already reads directly to compute `transition_cost`. This wiring already exists and works — the TODO comments (L22, L32, L54, L62) read as leftover design-migration notes from when costs might have lived elsewhere, not as an indication of missing functionality. **Action: verify via the test below, then if it passes, delete the 4 stale TODO comments rather than changing code.** This is the same "verify-before-assuming-a-fix" situation as B1.

**Test**: `MultiModeRCPSPWithCost` fixture (already imported in `tests/scheduling/test_scheduling.py` — reuse or extend it) with known non-zero mode costs and resource costs. Run a short rollout via `rollout()` or manual `step()` calls, and assert the accumulated `Value.cost` from `_get_transition_value` matches a hand-computed expected cost for the known action sequence — not a mock of `get_mode_costs`.

### C2. L1170: multi-objective transition value needs weighting

```python
weighed_transition_cost = 1.0 * transition_makespan + 1.0 * transition_cost
```
Hardcoded 1.0/1.0 weights when both `MAKESPAN` and `COST` objectives are active. This is a real gap: no way for a domain/user to configure relative weighting, and summing incommensurable units (time-steps vs. currency) silently is misleading. **Decision needed**: where do weights live — a new constructor/domain-level method (`_get_objective_weights() -> dict[SchedulingObjectiveEnum, float]`, mirroring the `_get_X_`/`get_X` override-point convention used everywhere else in this file) is the natural fit, defaulting to `{obj: 1.0 for obj in get_objectives()}` for backward compatibility.

**Depends on**: nothing blocking, but should land after C1 confirms the existing single-objective cost path is solid, since this changes the same function.

**Test**: a domain with both `MAKESPAN` and `COST` objectives and a nontrivial weight override (e.g. `{MAKESPAN: 2.0, COST: 0.5}`). Run the same fixed action sequence twice — once with default weights, once with the override — and assert the returned `Value.cost` scales exactly as expected between the two runs, computed from the same real `_get_transition_value` call path, no internals mocked.

---

## Cluster D — Duration/distribution semantics (`task_duration.py`)

### D1. L309 (`scheduling_domains.py`, `initialize_domain`): `self.sampled_durations = {}  # TODO: remove?`

This dict is `SimulatedTaskDuration.sample_task_duration`'s cache (task→mode→progress_from→duration). Per B2's finding, `update_progress`/`get_task_progress` actually reads duration from `state.tasks_details[task_id].sampled_duration` (the `Task` object), not from `self.sampled_durations`. So `self.sampled_durations` is written by `sample_task_duration`/read by `get_latest_sampled_duration`, and `get_latest_sampled_duration` is called exactly once, at `update_start_tasks` L847-849, whose *return value* then gets stored into the `Task` object — after which `self.sampled_durations` is never consulted again for that task's progress computation. It's also read once more in `compute_graph()` (L337, at `initialize_domain` time, to build static per-mode duration estimates for the precedence graph — a *different* consumer than the per-instance state duration).

So `self.sampled_durations` is doing two jobs: (1) a domain-level memoization cache so repeated `sample_task_duration` calls for the same `(task, mode, progress_from)` return consistent values within one domain instance (relevant for stochastic durations — first sample is "the" sample), and (2) supplying `compute_graph`'s static estimate at init time. Job (1) is load-bearing (removing it would make repeated calls to a stochastic `_sample_task_duration` return different values, silently breaking determinism-within-an-episode). **This resolves as: keep the dict, delete the "remove?" TODO, but rename/document it as "domain-instance-level duration memoization cache, consulted by `compute_graph` and `get_latest_sampled_duration`" so the next reader doesn't have to re-derive this.**

**Depends on**: B2's resolution (if B2 changes duration-resampling semantics, this cache's contract changes too — do this only after B2 is settled).

**Test**: fixture domain with `UncertainBoundedTaskDuration`/stochastic durations. Call `domain.sample_task_duration(task, mode)` twice directly and assert both calls return the same value (proves the cache is load-bearing, not incidental) — then call `domain._sample_task_duration` directly (bypassing the cache) twice with a seeded RNG changed between calls and assert those *can* differ, to document the cache is the only thing enforcing consistency.

### D2. L25 (`task_duration.py`, `SimulatedTaskDuration.sample_task_duration`): "for uncertain domain... you want to sample a different value each time... that's why I override this in below level"

This is a self-documenting comment, already resolved by `UncertainMultivariateTaskDuration.sample_task_duration` overriding the base to *not* cache (always calls `_sample_task_duration` fresh). Cross-check: does `get_latest_sampled_duration` (defined only on `SimulatedTaskDuration`, inherited unchanged by `UncertainMultivariateTaskDuration`) still do the right thing for the uncertain-multivariate branch? Looking at it: `get_latest_sampled_duration` checks `self.sampled_durations` (the cache) — but `UncertainMultivariateTaskDuration.sample_task_duration` never writes to that cache (it calls `_sample_task_duration` directly, bypassing `SimulatedTaskDuration.sample_task_duration`'s cache-write). So `get_latest_sampled_duration` for an uncertain-multivariate domain will almost always fall through to its own `sample_task_duration(...)` call at the bottom (cache miss), which for `UncertainMultivariateTaskDuration` *does* resample — this is actually consistent, not a bug. **Action: delete the TODO comment, it's resolved; the "challenge" it names was already addressed by the subclass override.** No code change, no new test needed beyond D1's (which already exercises `get_latest_sampled_duration` on the deterministic path — extend D1's test with one assertion on an `UncertainMultivariateTaskDuration` fixture confirming `sample_task_duration` called twice can differ).

### D3. L57 (`task_duration.py`): "Can we currently model multivariate distribution with the Distribution object?"

Real open question: `Distribution`/`DiscreteDistribution` in `autofde_lab.core` — check their interface — support `.sample()` and `.get_values()` for a single random variable. `UncertainMultivariateTaskDuration._get_task_duration_distribution` takes a `multivariate_settings: dict[str, int]` parameter (e.g. `{"t": state.t}` per its one call site at L875) suggesting "multivariate" here actually means "duration distribution parameterized by external state," not "jointly-distributed vector-valued duration" — i.e., it's conditional/contextual, not multivariate in the statistical sense. **Decision needed**: is this naming just wrong (should be `ContextualTaskDuration`/`ConditionalTaskDuration`), or is there a real planned use case for vector-valued task durations (e.g. duration + resource-need sampled jointly)? Check `hub/domain/rcpsp/` and `hub/domain/rddl` for any consumer that treats `_get_task_duration_distribution`'s return as multi-dimensional — if none does, this is a naming-only fix (rename class, update docstring, no behavior change) with no urgency; if a real vector use case exists, `Distribution` needs a new `MultivariateDistribution` type in `core.py`, which is a bigger, separate design task.

**Depends on**: nothing — but resolve the naming question before doing anything else in `task_duration.py`, since D4/L114 restates the same confusion at the next class down (`UncertainUnivariateTaskDuration` inherits `UncertainMultivariateTaskDuration` and its `_get_task_duration_distribution` signature still carries the unused `multivariate_settings` param down through `UncertainBoundedTaskDuration`/`UniformBoundedTaskDuration`, none of which use it).

**Test**: none until the naming/design decision is made — this is a rename-and-clarify item, not a behavior item. If it stays "contextual" (the likely outcome), no test is needed beyond existing coverage (`SingleModeRCPSP_Stochastic_Durations` in `tests/scheduling/test_scheduling.py` already exercises this path end-to-end). If it becomes truly multivariate, write a fixture domain whose duration distribution is a 2-vector and assert `.sample()` returns a length-2 result consumed correctly by `update_start_tasks_uncertain`.

### D4. L114 (`task_duration.py`, `UncertainUnivariateTaskDuration._get_task_duration_distribution`): "problem here I think"

Directly downstream of D3: `UncertainUnivariateTaskDuration` overrides `_get_task_duration_distribution` only to re-raise `NotImplementedError` with a different docstring ("univariate" vs. "multivariate") — the override does nothing functionally; its only purpose is documentation, and the "problem" is likely that the *signature* still accepts `multivariate_settings` even though "univariate" is supposed to mean it shouldn't need per-call external settings. Once D3 resolves the naming, this either goes away (if `Multivariate`→`Contextual` and `Univariate`→`Unconditional`, the redundant override can be deleted, letting `UncertainBoundedTaskDuration` inherit straight from the renamed base) or gets a real signature change (drop `multivariate_settings` from the univariate branch, requiring an ABC split — `UncertainBoundedTaskDuration`/`UniformBoundedTaskDuration`/`EnumerableTaskDuration`/`DeterministicTaskDuration` all currently accept and ignore `multivariate_settings` too, so this ripples down 4 more classes).

**Depends on**: D3's naming decision — do not touch D4 independently of D3, they're the same design question at two inheritance levels.

**Test**: same as D3 — no new test until the design decision lands; existing `test_scheduling.py` coverage of `DeterministicTaskDuration`/`UniformBoundedTaskDuration`-based fixtures (`SingleModeRCPSP`, `SingleModeRCPSP_Stochastic_Durations`) already exercises the inherited call path and would catch a signature-compatibility regression.

---

## Suggested execution order

1. **D1 → D2** (delete-stale-comment items, near-zero risk, clarifies duration-cache contract everyone else reads)
2. **B2** (decide + likely delete-dead-code; unblocks accurate understanding of B1)
3. **B1** (verify-then-likely-delete-stale-comment, needs B2's semantics settled first)
4. **C1** (verify-then-likely-delete-stale-comment)
5. **C2** (real feature: objective weighting — do after C1 confirms the base path is solid)
6. **A1** (real refactor: dispatch mechanism — biggest of the "worth doing" items, unlocks A2/A3)
7. **A3** (preallocation wiring — needs A1's dispatch decision)
8. **A2** (multi-resource-unit combinations — needs A1, and possibly a new fixture domain; largest scope, do last)
9. **D3 → D4** (naming/design decision, can happen any time in parallel with the rest since nothing else depends on it — but D4 must follow D3)

Roughly half these items (B1, B2's likely resolution, C1, D1, D2) are **verify-and-delete-stale-TODO**, not new implementation — the Chicago tests proposed for those are as much regression-proofing for future contributors as they are verification now. The other half (A1, A2, A3, C2, and D3/D4 if the vector case turns out real) are genuine scoped features, each gated on an explicit design decision called out above rather than a default "obviously correct" implementation.

---

## GNN / autoregressive vectorized-env support

Confirmed. `StableBaseline.__init__` always builds exactly one `AsGymnasiumEnv(domain)` from a single `domain_factory()` call and hands it to sb3's algo constructor as `env=`, which then goes through `_wrap_env` → `wrap_graph_env`/base sb3 `_wrap_env` → a 1-element `DummyVecEnv`. There is currently no code path anywhere in `StableBaseline` that builds `n>1` domain copies or a `SubprocVecEnv`/`n_envs`-parameterized `DummyVecEnv`. That's the actual gap, not just the guards in the three algorithm files.

## Follow-up implementation plan: real vectorized-env support for autofde_lab's stable-baselines3 integration

### 1. Scope and current state (what's stubbed vs. what works)

Three independent guard points currently raise `NotImplementedError` the instant `num_envs > 1` / `len(obs) > 1`:

| Location | Guard | What it protects |
|---|---|---|
| `autoregressive/common/on_policy_algorithm.py:37-41` (`ApplicableActionsOnPolicyAlgorithm.__init__`) | `isinstance(env, VecEnv) and env.num_envs > 1` | Rollout buffer that stores one flat `action_masks` list assuming `n_envs == 1` (`ApplicableActionsRolloutBuffer._add_action_masks` asserts `action_masks.shape[0] == 1`, `autoregressive/common/buffers.py:38-42`) |
| `gnn/common/on_policy_algorithm.py:42-46` (`GraphOnPolicyAlgorithm.__init__`) | same pattern | Graph observation batching path |
| `gnn/common/off_policy_algorithm.py:31-36` (`GraphOffPolicyAlgorithm.__init__`) | same pattern | `GraphReplayBuffer` also independently asserts `n_envs > 1` raises (`gnn/common/buffers.py:231-234`) |
| `gnn/common/utils.py:53-58` (`obs_as_tensor`) | `isinstance(obs, list) and len(obs) > 1` | The actual per-step tensor conversion — this is the deepest, most load-bearing single-env assumption; it silently `graph_instance_to_thg_data(obs[0], ...)`s a length-1 list even before the constructor guard fires in some call paths |

Upstream of all three: `StableBaseline.__init__` (`stable_baselines/stable_baselines.py:132-134`) only ever constructs one `AsGymnasiumEnv(domain)` from one `domain_factory()` call, and `wrap_graph_env` (`gnn/common/vec_env/dummy_vec_env.py:60-78`) only ever wraps that single env in a `GraphDummyVecEnv([lambda: env])`. **There is no vectorization on the autofde_lab side today at all** — the guards in the three files are defending buffer/tensor code that was written single-env-only, not rejecting an otherwise-supported feature. Non-vectorized (`n_envs == 1`) works today for: standard `RolloutBuffer`/`ReplayBuffer` paths (unaffected — those come straight from sb3), `GraphRolloutBuffer`/`DictGraphRolloutBuffer`/`GraphReplayBuffer`/`DictGraphReplayBuffer` (graph obs), `ApplicableActionsRolloutBuffer`/`ApplicableActionsGraphRolloutBuffer` (action masking + graph), all exercised today by `tests/solvers/python/test_gnn_sb3.py`.

### 2. What stable-baselines3 vectorized-env APIs this must implement against

- **`VecEnv.step(actions)` contract**: takes a batched `np.ndarray` of actions (shape `(n_envs, ...)`) and returns `(obs, rewards, dones, infos)` where `obs` is batched per sb3's `VecEnvObs` convention (dict of stacked arrays, or stacked array/tuple). Graph observations break the "stacked ndarray" assumption — sb3's own `DummyVecEnv._obs_from_buf` requires numeric dtype/shape, hence the existing `GraphDummyVecEnv` override that substitutes Python lists for the buffer slots holding graph subspaces. That override already batches correctly for `n_envs == 1`; extending it to `n_envs > 1` is mostly already-shaped code (`self.buf_obs[None] = [None for _ in range(self.num_envs)]` is already `num_envs`-general) — the gap is downstream consumers, not `GraphDummyVecEnv` itself.
- **`DummyVecEnv.__init__(env_fns)`**: needs `n>1` closures, each capturing its own domain instance from a fresh `domain_factory()` call (domains are stateful; sharing one instance across envs would corrupt state). `StableBaseline` needs a new `n_envs` (or `num_envs`/`vec_env_cls`) constructor parameter plumbed through to build `env_fns = [lambda: AsGymnasiumEnv(domain_factory()) for _ in range(n_envs)]`.
- **`SubprocVecEnv`**: true parallelism requires domains be picklable across processes (same constraint `ParallelDomain` already handles elsewhere in autofde_lab via `pathos`/`multiprocessing.Pipe`). Worth deferring to a phase 2 — `DummyVecEnv` with `n_envs > 1` (sequential-but-batched) already exercises every buffer/tensor code path that's currently stubbed and is the right first target.
- **Batched action masking**: `sb3_contrib`'s `get_action_masks(env)` / `MaskableRolloutBuffer.add(..., action_masks=...)` expect `action_masks` shaped `(n_envs, n_actions)` for fixed action-space size, but autofde_lab's applicable-actions case has a *variable* number of applicable actions per env per step — this is why `ApplicableActionsRolloutBuffer` stores a `list[np.ndarray]` per timestep rather than a fixed array. Vectorizing this specifically means that list becomes a *list of lists* (per-env ragged arrays), which the buffer's `_swap_and_flatten_action_masks`/`_get_action_masks_samples` don't currently express at all.
- **`obs_as_tensor` batched graph conversion**: needs a real multi-graph batching path — `torch_geometric.data.Batch.from_data_list([graph_instance_to_thg_data(g) for g in obs])` (the exact pattern `GraphBaseBuffer._graphlist_to_torch` in `gnn/common/buffers.py:50-58` already uses at sample time) instead of the current `obs[0]`-only shortcut. This is the single most mechanical piece of the three gaps — the target implementation already exists elsewhere in the same file tree as a template.

### 3. Per-component work breakdown

1. **`gnn/common/utils.py::obs_as_tensor`** — replace the `len(obs) > 1: raise NotImplementedError` branch with `thg.data.Batch.from_data_list([graph_instance_to_thg_data(g, device=device) for g in obs])`. Smallest, most mechanical piece; unblocks nothing by itself since callers still gate on `n_envs > 1` upstream.
2. **`gnn/common/vec_env/dummy_vec_env.py::wrap_graph_env`** — currently only ever called with a single `env` and always builds `GraphDummyVecEnv([lambda: env])`. Needs a new entry point (or parameter) accepting a *list* of already-constructed envs / env-factories for `n_envs > 1`, since today there's exactly one env in scope by construction.
3. **`stable_baselines.py::StableBaseline.__init__`** — add an `n_envs: int = 1` parameter; when `> 1`, call `self._domain_factory()` (or an explicit per-env factory) `n_envs` times to build `n_envs` independent `AsGymnasiumEnv` wrappers before handing them to the algo class. This is the actual missing plumbing — nothing downstream can be exercised with real vectorization until this exists.
4. **`gnn/common/on_policy_algorithm.py::GraphOnPolicyAlgorithm.__init__`** and **`gnn/common/off_policy_algorithm.py::GraphOffPolicyAlgorithm.__init__`** — drop the `num_envs > 1` guards once (1)-(3) land and `GraphRolloutBuffer`/`GraphReplayBuffer` batching is verified against real multi-env `_add_obs` calls (their `_add_obs` signatures already take `obs: list[GraphInstance]`, i.e. already per-env-list-shaped — needs verification under real multi-env `collect_rollouts`, not necessarily rewriting).
5. **`gnn/common/buffers.py::GraphReplayBuffer.__init__`** — remove its independent `n_envs > 1` raise (`buffers.py:231-234`) once (4)'s off-policy path is verified; check `_add_obs`/`_get_observations_samples` against a real `n_envs > 1` replay-buffer fill/sample cycle (off-policy adds happen per-`env.step()` call, one buffer row per env per step — needs confirming `ReplayBuffer.add()`'s parent-class indexing lines up with the graph-list append pattern).
6. **`autoregressive/common/on_policy_algorithm.py::ApplicableActionsOnPolicyAlgorithm.__init__`** and **`autoregressive/common/buffers.py::ApplicableActionsRolloutBuffer`** — this is the largest real gap, not a mechanical fix: `_add_action_masks` (`buffers.py:38-42`) hard-asserts `action_masks.shape[0] > 1` is invalid and only ever appends `action_masks[0]`. Needs redesigning to store a ragged per-env list-of-arrays per timestep (parallel structure to how `GraphRolloutBuffer.observations` is a list-of-lists via `swap_and_flatten_nested_list`), and `_swap_and_flatten_action_masks`/`_get_action_masks_samples` need the equivalent nested-list flattening `GraphRolloutBuffer` already uses as a template.
7. **`ApplicableActionsGraphRolloutBuffer`** (`autoregressive/common/buffers.py:52-61`) — currently an empty `...` combination class relying entirely on parent MRO; once (4)/(6) land independently, verify the combined graph-obs + applicable-actions + `n_envs > 1` case together, since it's the intersection of the two hardest gaps.

Recommended order: (1) → (3) → (2) → (4)+(5) [graph path, no action masking] → (6)+(7) [applicable-actions path, harder]. The graph-only path (`GraphPPO`/`GraphDQN`, no masking) is strictly simpler than the applicable-actions path and should land and be tested first as the vertical slice; autoregressive/masked support is a distinct, harder follow-up on top of it, not a parallel track, since it depends on (2)/(3) too.

### 4. Chicago-style test shape once done (real env, real `solve()`, real policy output — no mocks)

Two new tests parallel to existing ones in `tests/solvers/python/test_gnn_sb3.py`, both driving the *public* `StableBaseline` API end-to-end against the same fixture domains (`unmasked_graph_domain_factory`, `unmasked_jsp_domain_factory` from `tests/solvers/python/conftest.py` — real GNN-observation domains already used by every existing test in that file, not new mocks):

```python
def test_ppo_vectorized(unmasked_graph_domain_factory):
    domain_factory = unmasked_graph_domain_factory
    with StableBaseline(
        domain_factory=domain_factory,
        algo_class=GraphPPO,
        baselines_policy="GraphInputPolicy",
        n_envs=4,                          # new param from item 3 above
        learn_config={"total_timesteps": 400},
        n_steps=25,
    ) as solver:
        solver.solve()                      # exercises real collect_rollouts() over 4 real domain
                                             # instances, real GraphDummyVecEnv batching, real
                                             # GraphRolloutBuffer fill/sample, real PPO update
        rollout(
            domain=domain_factory(),        # separate, single, real (unvectorized) domain instance
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
        )                                   # asserts the trained policy actually produces valid
                                             # actions on a fresh domain — real observable behavior,
                                             # not an internal-call assertion
```

- Assert on real, observable outcomes only: `rollout()` completing without exception, the resulting trajectory's actions being members of `domain.get_action_space()`, and (for the off-policy/masking follow-up) `GraphDQN`/`MaskableGraphPPO`/`AutoregressivePPO` variants each getting their own `n_envs > 1` test using the same fixture-domain pattern.
- A second test should assert the vectorized path and the `n_envs=1` path produce buffers of the equivalent *shape* (same number of total transitions collected for `n_envs=4, n_steps=25` as `n_envs=1, n_steps=100`) — this is the one place a slightly more structural assertion earns its keep, since "did it actually batch 4 envs instead of silently only stepping 1" is exactly the kind of regression a purely rollout()-level test could miss silently.
- No mocking of `VecEnv`, `DummyVecEnv`, or the domain — mock only if a `SubprocVecEnv`-based phase-2 test needs a real multiprocessing boundary asserted, which is an externality (process spawning), not the domain/solver collaboration itself.

### Files touched by this plan
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/stable_baselines.py`
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/gnn/common/utils.py`
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/gnn/common/vec_env/dummy_vec_env.py`
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/gnn/common/on_policy_algorithm.py`
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/gnn/common/off_policy_algorithm.py`
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/gnn/common/buffers.py`
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/autoregressive/common/on_policy_algorithm.py`
- `/Users/sac/scikit-decide/src/autofde_lab/hub/solver/stable_baselines/autoregressive/common/buffers.py`
- `/Users/sac/scikit-decide/tests/solvers/python/test_gnn_sb3.py` (new tests)

---

## plado/PDDL IR unimplemented branches

## Findings before the plan (correcting the premise)

I read both files end-to-end and cross-checked every `NotImplementedError` branch against the actual installed `plado` class hierarchy (`.venv/lib/python3.13/site-packages/plado/{datalog/numeric.py,semantics/task.py}`), not just the sk-decide wrapper code. The premise that there are ~15 unhandled PDDL/plado expression/effect *kinds* doesn't hold up for most of the listed lines:

**`plado.py` (13 of the lines: 316,330,340,352,367,380,396,406,464,480,802,874,937)** — every one of these is the `else: raise NotImplementedError()` tail of an `if/elif` over scikit-decide's own internal enums (`StateEncoding`, `ActionEncoding`, `ObservationEncoding`), not over PDDL/plado expression or effect kinds. Each enum currently has exactly the members the `if/elif` chain covers (e.g. `ObservationEncoding` has only `GYM_GRAPH_OBJECTS`, and both its dispatches at 802/874/937 already handle it). These branches are dead/defensive code today — they only fire if someone adds a new enum member without updating the dispatch. Not a real gap.

**`llg_encoder.py` lines 868, 948, 969** — same story but over plado's actual class hierarchy: `AtomicEffect` has exactly 3 subclasses (`AddEffect`, `DelEffect`, `NumericEffect`, verified in `semantics/task.py`), all handled at line ~830; `NumericExpression` has exactly `Constant`, `Fluent`, and the 4 `BinaryOperation` subclasses (`Addition`, `Subtraction`, `Division`, `Multiplication`), all handled at lines ~939-948 and ~956-965. These three branches are unreachable against the current plado version.

**`llg_encoder.py` lines 593, 603** are the one genuine gap in that file: `IndexFunctionType.RANDSPHERE` is a defined enum member with no implementation in `index_function`/`index_function_inverse` (only `ONEHOT` is implemented).

**The actual missing capability isn't at any of the cited line numbers at all.** `LLGEncoder._check_actions_hypotheses()` (lines 329-375) `assert`s away conditional effects and multi-outcome probabilistic effects *before* the code ever reaches the effect-kind dispatch — meaning any PPDDL domain with genuine probabilistic or conditional effects raises `AssertionError` on `LLGEncoder.__init__`, not `NotImplementedError`. Since `PladoPPddlDomain` (probabilistic PDDL) is a first-class supported domain class in `plado.py`, this is the one place where "which PDDL construct kind is unhandled" is a real and consequential question — it's just not surfaced as a `NotImplementedError` at all.

## Scoped follow-up plan

**1. `IndexFunctionType.RANDSPHERE` (llg_encoder.py:593,603) — low priority, cosmetic gap**
- Likelihood in real files: N/A — this isn't a PDDL construct, it's an encoder-internal choice already exposed via `index_function_type` kwarg with `ONEHOT` as a working default. Nobody hits this unless they explicitly opt into `RANDSPHERE`.
- Fixture: none needed (no PDDL file exercises this — it's a unit-level encoder config).
- Test: parametrize the existing LLG encoder round-trip test (`encode`→`decode` on a small fixture domain) over `IndexFunctionType.{ONEHOT, RANDSPHERE}` once implemented.
- Order: last, or drop — arguably should be deleted/marked `UNSUPPORTED` rather than implemented, since nothing in the codebase currently constructs an `LLGEncoder` with `RANDSPHERE` and there's no evidence it's needed. Confirm with the plado paper/maintainers whether random-sphere injection is still intended before investing time.

**2. Conditional and probabilistic effects in `LLGEncoder` (the real gap, at `_check_actions_hypotheses`, not at any `NotImplementedError`) — highest priority**
- Likelihood: high. `PladoPPddlDomain` exists precisely to support PPDDL, and probabilistic effects (`(probabilistic 0.5 (effect-a) 0.5 (effect-b))`) are the defining feature of PPDDL problem sets (e.g. IPPC benchmark domains: `exploding-blocksworld`, `tireworld`, `elevators`). Conditional effects (`(when ... ...)`) are also common in standard PDDL2.1+ (`satellite`, `logistics`-derived domains). Right now, `action_encoding=GYM_MULTIDISCRETE`/`GYM_DISCRETE` work fine on such domains via `BasePladoDomain` (no LLG involved), but `state_encoding=GYM_GRAPH_LLG` with `encode_actions=True` will hard-`assert`-fail at construction time for any such domain.
- Fixtures needed:
  - A minimal PPDDL domain/problem pair with a single action containing a 2-outcome probabilistic effect, no conditions (exercises `ProbabilisticEffect.outcomes` with `len > 1`).
  - A minimal PDDL domain/problem with one `(when <cond> <effect>)` conditional effect (exercises `ConditionalEffect.condition` non-empty).
  - Ideally reuse/trim an existing IPPC PPDDL domain (e.g. `tireworld`) if one is already vendored in `tests/` fixtures for plado; otherwise hand-write ~10-line domain/problem files under `tests/domains/plado/` (check first whether such a directory already exists before creating fixtures from scratch).
- Implementation sketch (not code): extend `_encode_action` to iterate all `(prob, outcomes)` pairs in `ProbabilisticEffect.outcomes` and all `ConditionalEffect`s per outcome, adding a probability-weighted edge/node (reusing the existing `NUMERIC`+`EFFECT` edge machinery for the probability value, similar to how `Constant` numeric values are already encoded) and encoding the `ConditionalEffect.condition` via the existing `_encode_condition` helper (already generic over `SimpleCondition`). This is mostly wiring existing helpers together, not new primitives.
- Test: build the fixture domain, run `LLGEncoder(task, encode_actions=True)`, assert construction succeeds and `encode(state)`/`decode(graph)` round-trips atoms/fluents correctly for a state reachable after the probabilistic/conditional action.
- Order: do this first — it's the only item where real PDDL/PPDDL files in the wild will actually trigger a failure, and it blocks `GYM_GRAPH_LLG` + `encode_actions=True` for a whole domain class (PPDDL) sk-decide otherwise supports.

**3. The `plado.py` and remaining `llg_encoder.py` `NotImplementedError` branches — no action needed**
- These guard scikit-decide's own enums and plado's own exhaustive class hierarchies, both already fully covered by the existing `if/elif` chains. Leave as defensive fallbacks. If desired, a trivial low-value cleanup would be replacing the bare `NotImplementedError()` with a message naming the unexpected enum/type value, purely to aid debugging if plado ever adds a class — not a functional gap, so not worth prioritizing over item 2.

Files read: `/Users/sac/scikit-decide/src/autofde_lab/hub/domain/plado/plado.py`, `/Users/sac/scikit-decide/src/autofde_lab/hub/domain/plado/llg_encoder.py`, `/Users/sac/scikit-decide/.venv/lib/python3.13/site-packages/plado/datalog/numeric.py`, `/Users/sac/scikit-decide/.venv/lib/python3.13/site-packages/plado/semantics/task.py`.

---

## Remote branch triage

## Triage: remote-only branches vs master (read-only investigation)

| Branch | Commits ahead of master | Files touched | Recommendation |
|---|---|---|---|
| `origin/feat/close-planning-domain-gaps` | 0 | — | **stale-superseded** — tip `db6f00d` is already an ancestor of master. No unique content; safe to delete once someone confirms, but no action taken here. |
| `origin/feat/self-play-chicago-tests` | 0 | — | **stale-superseded** — tip `0f32a25` is already an ancestor of master. |
| `origin/fix/ray-gymnasium-python313-modernization` | 0 | — | **stale-superseded** — tip `576c625` is already an ancestor of master. |
| `origin/fix/rddl-python313-markers` | 0 | — | **stale-superseded** — tip `2fdc8fe` is already an ancestor of master. |
| `origin/agent/agentic-hiring-bootstrap` | 0 | — | **stale-superseded** — tip `0f32a25` is already an ancestor of master (same tip as self-play-chicago-tests). |
| `origin/agent/agentic-hiring-control-plane` | 0 | — | **stale-superseded** — same tip `0f32a25`, already merged into master. |
| `origin/agent/errc-wasm4pm-alive` | 8 (base `9e43394`, tip `afc5429`) | `src/autofde_lab/wasm/_artifacts.py`, `src/autofde_lab/wasm/_registry.py`, `src/autofde_lab/wasm/artifacts/chatman-interop-wasm.zip` (binary, 3803→6308 bytes) | **needs human review** — small, self-contained changeset touching a wasm artifact registry plus a binary zip blob; commit messages (`bind exact source-owned wasm4pm overlay`, `stage binary overlay manufacture`, `close exact wasm4pm interop identity`) read as agent-generated scaffolding/staging language rather than descriptive engineering commits — verify intent and provenance of the binary before considering merge. |
| `origin/agent/errc-wasm4pm-alive-proof` | 8 (identical) | identical to the above | **needs human review** — this branch is not merely similar to `agent/errc-wasm4pm-alive`, it is the *same* branch: both refs resolve to commit `afc5429d998927dd4a591faa4d6172c5bcec3028`. Treat as a duplicate ref, not a distinct line of work; resolve which name is canonical before doing anything else with either. |

### Notes
- Six of the eight branches (`feat/close-planning-domain-gaps`, `feat/self-play-chicago-tests`, `fix/ray-gymnasium-python313-modernization`, `fix/rddl-python313-markers`, `agent/agentic-hiring-bootstrap`, `agent/agentic-hiring-control-plane`) have tips that are ancestors of current `master` — their work already landed (verified via `git merge-base --is-ancestor origin/<branch> master`), so `master..origin/<branch>` shows zero commits. These are candidates for branch cleanup, not merge.
- `agent/errc-wasm4pm-alive` and `agent/errc-wasm4pm-alive-proof` share the exact same commit SHA (`afc5429`), same author timestamp (`2026-08-06T00:57:36-07:00`), same 8-commit history (`git rev-list` diff is empty). This is the one pair worth a closer human look — both for the duplicate-ref oddity and because it's the only pair with actual unmerged content, including a binary artifact swap.
- No merge, rebase, or delete operations were performed; this was `git fetch` + read-only `log`/`diff --stat`/`merge-base` only.
