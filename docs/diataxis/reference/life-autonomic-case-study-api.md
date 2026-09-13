# Life Autonomic Case Study Reference

This page documents the public surface of
`src/autofde_lab/agent/life_autonomic_case_study.py`: its module-level constants,
dataclasses, functions, CLI entrypoint, and the test surface that verifies it. For the
narrative explanation of why this case study exists and what it demonstrates, see
[`docs/case-studies/life-autonomic-controller.md`](../case-studies/life-autonomic-controller.md).

The module is SELECT/CONSTRUCT only. It never actuates, sends a message, or grants
authority. Every candidate plan carries `required_authority_classes == ()`, and the
receipt it emits always sets `authority="NONE"`, `do_authority=False`, and
`evidence_kind="PLANNING_EVIDENCE_ONLY"`.

## Module-level constants

- `GOAL` — `"stabilize-week"`. Default goal for `admit_life_observations` and the
  goal used to build the candidate frontier.
- `CONSTRAINT_DIGEST` — `"life-case-study-policy-v1"`. Constraint digest carried by
  both `PlanningContext` and every `PlanApplicability` in this module.
- `SEMANTIC_REVISION` — `"life-case-study-v1"`. Semantic revision carried by both
  `PlanningContext` and every `PlanApplicability` in this module.
- `PLANNING_CAPABILITY` — `"bounded-life-planning"`. The single required capability
  asserted by `admit_life_observations` and by every candidate plan's
  `PlanApplicability`.

## `LifeObservation`

```python
@dataclass(frozen=True, slots=True)
class LifeObservation:
    fact: str
    source_ref: str
    admitted: bool
```

One explicitly admitted or non-admitted fact observation. Frozen and slotted.

- `fact` — the fact string this observation names.
- `source_ref` — an opaque reference to where the observation came from.
- `admitted` — whether this fact is explicitly admitted. Only `admitted=True`
  observations become facts in the resulting `PlanningContext`.

## `LifeCaseStudyReceipt`

```python
@dataclass(frozen=True, slots=True)
class LifeCaseStudyReceipt:
    schema: str
    subject: str
    observation_digest: str
    frontier_keys: tuple[str, ...]
    exact_reuse_disposition: str
    repair_disposition: str
    repair_affected_paths: tuple[str, ...]
    continue_disposition: str
    fresh_goal_disposition: str
    authority: str
    do_authority: bool
    evidence_kind: str
```

Deterministic planning evidence. Explicitly not an execution receipt.

- `schema: str` — schema URN for this receipt shape
  (`"urn:autofde-lab:life-autonomic-case-study-receipt:1"` when produced by
  `run_case_study`).
- `subject: str` — the goal this receipt is about.
- `observation_digest: str` — SHA-256 digest of the full observation set (admitted
  and non-admitted), via `sha256()` from `autofde_lab.fabric.canonical`.
- `frontier_keys: tuple[str, ...]` — the `PlanCache.remember()` keys for each
  candidate plan in the frontier, in frontier order.
- `exact_reuse_disposition: str` — `.value` of the `PlanDisposition` returned by
  the exact-reuse `planner.decide()` call.
- `repair_disposition: str` — `.value` of the `PlanDisposition` returned by the
  repair `planner.decide()` call.
- `repair_affected_paths: tuple[str, ...]` — sorted, slash-joined node paths (e.g.
  `"1"`, `"3"`) from the repair decision's `affected` set.
- `continue_disposition: str` — `.value` of the `PlanDisposition` returned by the
  continuation `planner.decide()` call.
- `fresh_goal_disposition: str` — `.value` of the `PlanDisposition` returned by the
  fresh-goal `planner.decide()` call.
- `authority: str` — always `"NONE"` for this case study.
- `do_authority: bool` — always `False` for this case study.
- `evidence_kind: str` — always `"PLANNING_EVIDENCE_ONLY"` for this case study.

### `payload()`

```python
def payload(self) -> dict[str, object]:
```

Returns a plain `dict` of every field above (with `frontier_keys` and
`repair_affected_paths` converted to `list`), in insertion order. Used as the input to
the receipt's hash; does **not** include `receipt_sha256` itself.

### `receipt_sha256` (property)

```python
@property
def receipt_sha256(self) -> str:
```

`sha256(self.payload())` — the SHA-256 digest of `payload()`'s dict, computed via
`autofde_lab.fabric.canonical.sha256`.

### `as_dict()`

```python
def as_dict(self) -> dict[str, object]:
```

Returns `{**self.payload(), "receipt_sha256": self.receipt_sha256}` — every payload
field plus the digest itself. This is what `main()` serializes to JSON.

## `admit_life_observations`

```python
def admit_life_observations(
    observations: Iterable[LifeObservation],
    *,
    goal: str = GOAL,
) -> PlanningContext:
```

Projects only explicitly admitted positive facts into the planning view. Iterates the
given `observations`, keeps a `frozenset` of `item.fact` for every `item` where
`item.admitted` is `True`, and constructs a `PlanningContext` with:

- `goal` — the `goal` keyword argument (default `GOAL`).
- `facts` — the frozenset of admitted facts.
- `capabilities` — `frozenset({PLANNING_CAPABILITY})`.
- `constraint_digest` — `CONSTRAINT_DIGEST`.
- `semantic_revision` — `SEMANTIC_REVISION`.

A `LifeObservation` with `admitted=False` never contributes its `fact` to the returned
context, regardless of what the fact string says.

## `build_candidate_frontier`

```python
def build_candidate_frontier() -> tuple[PlanArtifact, ...]:
```

Returns three lawful `PlanArtifact` candidates, in this fixed order, rather than
selecting one winner. Each is built by the module-private `_plan(ordering, objective)`
over four `Atom` activities: `preserve-income-option`, `prepare-career-window`,
`advance-education-option`, `publish-household-brief` (indices 0-3 respectively). The
`ordering` argument controls which `OrderEdge`s connect those activities:

- `balanced` / objective `preserve-parallel-optionality` — edges `(0,3)`, `(1,3)`,
  `(2,3)`.
- `income-protect` / objective `protect-income-continuity` — edges `(0,1)`, `(0,2)`,
  `(1,3)`, `(2,3)`.
- `career-window` / objective `protect-time-bounded-career-window` — edges `(1,0)`,
  `(1,2)`, `(0,3)`, `(2,3)`.

Every candidate shares the same `applicability` (`goal=GOAL`,
`required_capabilities=frozenset({PLANNING_CAPABILITY})`,
`constraint_digest=CONSTRAINT_DIGEST`, `semantic_revision=SEMANTIC_REVISION`),
`planner="life-autonomic-case-study"`, `family_id="life-autonomic-week"`, and
`required_authority_classes=()`. `planner_parameters` always includes
`"selection_authority": "NONE"` alongside `ordering` and `objective`.
`dependency_keys` maps each single-node path `(0,)`..`(3,)` to one `fact:` key
(`fact:income-option-open`, `fact:career-window-open`, `fact:education-option-open`,
`fact:household-brief-due` respectively); `downstream` maps nodes `(0,)`, `(1,)`,
`(2,)` each to `{(3,)}`.

## `run_case_study`

```python
def run_case_study() -> LifeCaseStudyReceipt:
```

Executes the bounded planning experiment against the real `ContinuousPlanner` kernel
and returns replayable evidence. The sequence, in order:

1. Constructs five `LifeObservation`s: `income-option-open`, `career-window-open`,
   `education-option-open`, and `household-brief-due` (all `admitted=True`), plus
   `unverified-side-project` (`admitted=False`).
2. Calls `admit_life_observations(observations)` to build the base `PlanningContext`.
3. Calls `build_candidate_frontier()` to get the three-plan frontier.
4. Creates a `PlanCache()` and a `ContinuousPlanner(cache)`, then `cache.remember(plan)`
   for each frontier plan, collecting the returned keys as `frontier_keys`. The first
   frontier plan (`balanced`) becomes `active_plan`.
5. **Exact reuse**: `planner.decide(context, exact_key=frontier_keys[0])`. Expected
   disposition: `EXACT_REUSE`.
6. **Repair**: builds `career_window_closed`, a copy of `context` with
   `"career-window-open"` removed from `facts`, then calls
   `planner.decide(career_window_closed, active_plan=active_plan,
   previous_context=context)`. Expected disposition: `REPAIR`, with `affected` node
   paths exactly `("1", "3")` — the `career-window` node and its downstream
   `household-brief` node.
7. **Continuation**: builds `unrelated_delta`, a copy of `context` with
   `"weather-noted"` added to `facts`, then calls
   `planner.decide(unrelated_delta, active_plan=active_plan,
   previous_context=context)`. Expected disposition: `CONTINUE`.
8. **Fresh plan**: builds `new_goal`, a copy of `context` with
   `goal="different-weekly-goal"`, then calls `planner.decide(new_goal)` (no
   `active_plan`, no `exact_key`). Expected disposition: `FRESH_PLAN`.
9. Returns a `LifeCaseStudyReceipt` with
   `schema="urn:autofde-lab:life-autonomic-case-study-receipt:1"`, `subject=GOAL`,
   `observation_digest=sha256(_observation_payload(observations))`, `frontier_keys`
   from step 4, the four `.disposition.value` strings from steps 5-8,
   `repair_affected_paths` sorted and slash-joined from step 6's `affected`,
   `authority="NONE"`, `do_authority=False`, `evidence_kind="PLANNING_EVIDENCE_ONLY"`.

These exact dispositions and the `("1", "3")` affected-path pair are asserted, not just
described here — see [Test surface reference](#test-surface-reference) below and run:

```bash
.venv/bin/python -m pytest -vv tests/agent/test_life_autonomic_case_study.py
```

which reports 3 passed on this repository's merged state (PR #92, merge `6d0a3aed`).

## `main()` / CLI entrypoint

```python
def main() -> None:
    print(json.dumps(run_case_study().as_dict(), sort_keys=True, indent=2))
```

Invoked via:

```bash
PYTHONPATH=src python -m autofde_lab.agent.life_autonomic_case_study
```

Prints `run_case_study().as_dict()` as canonical JSON — keys sorted, two-space indent.
The printed object includes `receipt_sha256`, since `as_dict()` adds it on top of
`payload()`.

## Kernel this case study composes

`life_autonomic_case_study.py` does not implement its own planner; it composes the
existing continuous-planning kernel in `autofde_lab.agent.continuous_planning`, whose
own module docstring states it is "SELECT/CONSTRUCT only" and that it "never actuates,
grants authority, brokers execution, or manufactures an execution receipt." The types
and functions this case study calls directly are `PlanningContext`, `PlanArtifact`,
`PlanApplicability`, `PlanCache`, `ContinuousPlanner` (and its `decide()` method),
`ContinuousPlanDecision`, and `PlanDisposition`; `admit_plan` and `AdmissionCode` are
part of the same kernel surface but are not called directly by this module. Full
reference for that kernel belongs in its own reference page, not here — this page
covers only the case-study module's own surface.

## Test surface reference

`tests/agent/test_life_autonomic_case_study.py` contains three test functions:

- `test_case_study_executes_real_planning_kernel_and_replays` — asserts two
  `run_case_study()` calls produce identical `receipt_sha256`, `observation_digest`,
  and `frontier_keys` (3 unique keys); the four dispositions are exactly
  `EXACT_REUSE`, `REPAIR`, `CONTINUE`, `FRESH_PLAN`; and
  `repair_affected_paths == ("1", "3")`.
- `test_unknown_observation_is_not_silently_admitted` — given one admitted and one
  non-admitted `LifeObservation`, asserts `admit_life_observations` includes the
  admitted fact and excludes the non-admitted one from `context.facts`.
- `test_frontier_is_candidate_only_and_non_actuating` — asserts `run_case_study()`'s
  receipt has `authority == "NONE"`, `do_authority is False`,
  `evidence_kind == "PLANNING_EVIDENCE_ONLY"`; and that every frontier plan has
  `required_authority_classes == ()` and no `execute`, `grant`, or `actuate`
  attribute.
