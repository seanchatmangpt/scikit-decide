# Model a Bounded Subject with Continuous Planning

This guide adapts the pattern from the autonomic-life planning case study
(`src/autofde_lab/agent/life_autonomic_case_study.py`) to a subject of your
own choosing. It assumes you already know the basics of `ContinuousPlanner`,
`PlanningContext`, and `PlanArtifact` from the tutorial. For the design
rationale behind the case study itself, see
[the case-study explanation doc](../case-studies/life-autonomic-controller.md)
-- this guide does not repeat that material.

Everything here stays SELECT/CONSTRUCT only: no message is sent, no calendar
is changed, no authority is granted. `authority` is always `"NONE"`,
`do_authority` is always `False`, and any receipt you emit should carry
`evidence_kind = "PLANNING_EVIDENCE_ONLY"`.

## 1. Define your own observation set

Reuse `LifeObservation` (`fact`, `source_ref`, `admitted`) for a different
subject than `stabilize-week`. Each observation names one fact, cites where
that fact came from, and states whether it is explicitly admitted:

```python
from autofde_lab.agent.life_autonomic_case_study import LifeObservation

observations = (
    LifeObservation("budget-review-open", "case:budget-observation", True),
    LifeObservation("vendor-contract-open", "case:vendor-observation", True),
    LifeObservation("audit-window-open", "case:audit-observation", True),
    LifeObservation("quarterly-brief-due", "case:brief-observation", True),
    LifeObservation("unverified-rumor", "case:unknown-observation", False),
)
```

Do not build your own dataclass unless the case study's three fields
(`fact`, `source_ref`, `admitted`) genuinely cannot carry your subject.
`LifeObservation` is frozen and slotted; it carries no execution semantics.

## 2. Admit only explicit positive facts

Call `admit_life_observations` with your own `goal`, or build a
`PlanningContext` directly if your subject needs different capabilities or a
different constraint digest. `admit_life_observations` projects only facts
where `admitted` is `True`:

```python
from autofde_lab.agent.life_autonomic_case_study import admit_life_observations

context = admit_life_observations(observations, goal="stabilize-quarter")
```

For a subject that needs its own capability set or constraint digest instead
of the case study's `bounded-life-planning` / `life-case-study-policy-v1`,
build `PlanningContext` directly:

```python
from autofde_lab.agent.continuous_planning import PlanningContext

context = PlanningContext(
    goal="stabilize-quarter",
    facts=frozenset(item.fact for item in observations if item.admitted),
    capabilities=frozenset({"bounded-quarter-planning"}),
    constraint_digest="quarter-case-study-policy-v1",
    semantic_revision="quarter-case-study-v1",
)
```

**Verify the non-admission fence.** Every subject must reject the same class
of defect this repo's `absence-is-not-evidence.md` law names: a fact that was
never explicitly admitted must not appear in `context.facts`, and it must
not be silently converted into a negative fact either. Copy the assertion
shape from
`test_unknown_observation_is_not_silently_admitted`
(`tests/agent/test_life_autonomic_case_study.py`):

```python
assert "budget-review-open" in context.facts
assert "unverified-rumor" not in context.facts
```

## 3. Build a candidate frontier of 2+ reversible plans

Use `build_candidate_frontier`'s pattern: construct several
`PlanArtifact` values that share a `goal`, `family_id`, and
`required_capabilities`, but differ in ordering or objective. Never collapse
to a single "winning" plan -- the case study preserves three.

```python
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder
from autofde_lab.agent.continuous_planning import PlanApplicability, PlanArtifact

def _quarter_model(ordering: str) -> PartialOrder:
    activities = (
        Atom("close-budget-review"),
        Atom("finalize-vendor-contract"),
        Atom("complete-audit"),
        Atom("publish-quarterly-brief"),
    )
    if ordering == "balanced":
        edges = frozenset({OrderEdge(0, 3), OrderEdge(1, 3), OrderEdge(2, 3)})
    elif ordering == "vendor-first":
        edges = frozenset(
            {OrderEdge(1, 0), OrderEdge(1, 2), OrderEdge(0, 3), OrderEdge(2, 3)}
        )
    else:
        raise ValueError(f"unknown ordering: {ordering}")
    return PartialOrder(activities, edges)

def _quarter_plan(ordering: str, objective: str) -> PlanArtifact:
    return PlanArtifact(
        model=_quarter_model(ordering),
        applicability=PlanApplicability(
            goal="stabilize-quarter",
            required_capabilities=frozenset({"bounded-quarter-planning"}),
            constraint_digest="quarter-case-study-policy-v1",
            semantic_revision="quarter-case-study-v1",
        ),
        planner="quarter-case-study",
        planner_parameters={
            "ordering": ordering,
            "objective": objective,
            "selection_authority": "NONE",
        },
        dependency_keys={
            (0,): frozenset({"fact:budget-review-open"}),
            (1,): frozenset({"fact:vendor-contract-open"}),
            (2,): frozenset({"fact:audit-window-open"}),
            (3,): frozenset({"fact:quarterly-brief-due"}),
        },
        downstream={
            (0,): frozenset({(3,)}),
            (1,): frozenset({(3,)}),
            (2,): frozenset({(3,)}),
        },
        family_id="quarter-planning-week",
        required_authority_classes=(),
    )
```

**When to add a fourth ordering versus reuse an existing one:** add a new
ordering only when it encodes a genuinely different priority tradeoff among
your dependency nodes (as `income-protect` versus `career-window` do in the
case study). If two orderings would produce the same downstream repair cone
for every delta you care about, they are not distinct candidates -- reuse
one of them instead of inflating the frontier.

## 4. Exercise the four real transitions

All four transitions run against the real `ContinuousPlanner`, not a
simulated one. Seed a `PlanCache` with your frontier first:

```python
from autofde_lab.agent.continuous_planning import ContinuousPlanner, PlanCache

cache = PlanCache()
frontier = (_quarter_plan("balanced", "preserve-parallel-optionality"),
            _quarter_plan("vendor-first", "protect-vendor-window"))
frontier_keys = tuple(cache.remember(plan) for plan in frontier)
active_plan = frontier[0]
planner = ContinuousPlanner(cache)
```

**Exact reuse** -- ask for the exact cached key with no delta:

```python
exact = planner.decide(context, exact_key=frontier_keys[0])
assert exact.disposition.value == "EXACT_REUSE"
```

**Local repair** -- close one fact, pass both `active_plan` and
`previous_context` so the planner can compute the delta:

```python
vendor_closed = PlanningContext(
    goal=context.goal,
    facts=context.facts - {"vendor-contract-open"},
    capabilities=context.capabilities,
    constraint_digest=context.constraint_digest,
    semantic_revision=context.semantic_revision,
)
repair = planner.decide(vendor_closed, active_plan=active_plan, previous_context=context)
assert repair.disposition.value == "REPAIR"
# repair.affected is the delta-local repair cone -- check it names only the
# node paths whose dependency_keys intersected the changed fact, plus their
# downstream nodes. It must not include unrelated nodes.
```

**Irrelevant-delta continuation** -- add a fact nothing depends on:

```python
unrelated = PlanningContext(
    goal=context.goal,
    facts=context.facts | {"weather-noted"},
    capabilities=context.capabilities,
    constraint_digest=context.constraint_digest,
    semantic_revision=context.semantic_revision,
)
continuation = planner.decide(unrelated, active_plan=active_plan, previous_context=context)
assert continuation.disposition.value == "CONTINUE"
```

**Fresh-goal routing** -- change `goal` and call `decide` with no
`active_plan`:

```python
new_goal = PlanningContext(
    goal="different-quarterly-goal",
    facts=context.facts,
    capabilities=context.capabilities,
    constraint_digest=context.constraint_digest,
    semantic_revision=context.semantic_revision,
)
fresh = planner.decide(new_goal)
assert fresh.disposition.value == "FRESH_PLAN"
assert fresh.plan is None
```

## 5. Keep the receipt PLANNING_EVIDENCE_ONLY

Model your receipt on `LifeCaseStudyReceipt`: `authority` fixed at
`"NONE"`, `do_authority` fixed at `False`, `evidence_kind` fixed at
`"PLANNING_EVIDENCE_ONLY"`. Do **not**:

- add `execute`, `grant`, or `actuate` methods to `PlanArtifact` or any
  subclass of it;
- set `do_authority=True`;
- populate `required_authority_classes` with anything non-empty, unless you
  are also building the authority-envelope and actuation boundary this repo
  does not have (see `.claude/rules/gym-actuation-boundary.md` for where
  real actuation lives -- it is not here).

Verify the fence the same way `test_frontier_is_candidate_only_and_non_actuating`
does:

```python
for plan in frontier:
    assert plan.required_authority_classes == ()
    assert not hasattr(plan, "execute")
    assert not hasattr(plan, "grant")
    assert not hasattr(plan, "actuate")
```

## 6. Add your own Chicago-style test

Write a real test module under `tests/agent/`, exercising the real
`ContinuousPlanner` and your real `PlanningContext`/`PlanArtifact` values --
no mocks, no stubs. Use
`tests/agent/test_life_autonomic_case_study.py`'s three tests as the
template:

1. **Determinism/replay** -- run your case-study function twice, assert the
   receipt digest, observation digest, and frontier keys are identical both
   times (see `test_case_study_executes_real_planning_kernel_and_replays`).
2. **Admission fencing** -- assert an admitted fact is in `context.facts`
   and a non-admitted fact is not (see
   `test_unknown_observation_is_not_silently_admitted`).
3. **Non-actuation fencing** -- assert `authority == "NONE"`,
   `do_authority is False`, `evidence_kind == "PLANNING_EVIDENCE_ONLY"`, and
   that no candidate plan carries `execute`/`grant`/`actuate` (see
   `test_frontier_is_candidate_only_and_non_actuating`).

Run it for real before claiming anything works:

```bash
PYTHONPATH=src python -m pytest -vv tests/agent/test_your_new_case_study.py
```

The autonomic-life case study's own three tests are the standing evidence
this pattern is real, not hypothetical:

```bash
PYTHONPATH=src python -m pytest -vv tests/agent/test_life_autonomic_case_study.py
```

At time of writing that command reports 3 passed (PR #92, merge
`6d0a3aed`). Do not cite that number for your own new test module -- run
your own command and cite your own output.

## 7. Troubleshooting

**An admission failure.** `admit_plan(plan, context)` returns a
`PlanAdmission` with `admitted: bool` and `codes: tuple[AdmissionCode, ...]`.
`AdmissionCode` is a `StrEnum` with these members:

| Code | Meaning |
|---|---|
| `ADMITTED` | the plan is applicable to this context |
| `GOAL_MISMATCH` | `plan.applicability.goal != context.goal` |
| `REQUIRED_FACT_MISSING` | a fact the plan requires is absent from `context.facts` |
| `FORBIDDEN_FACT_PRESENT` | a fact the plan forbids is present in `context.facts` |
| `CAPABILITY_MISSING` | `context.capabilities` does not cover `required_capabilities` |
| `CONSTRAINT_MISMATCH` | `constraint_digest` differs between plan and context |
| `SEMANTIC_REVISION_MISMATCH` | `semantic_revision` differs between plan and context |

If `ContinuousPlanner.decide` returns `FRESH_PLAN` when you expected
`EXACT_REUSE`, `CACHED_REUSE`, or `REPAIR`, check these codes first --
a mismatched `constraint_digest` or `semantic_revision` between your
candidate plans and your context is the most common cause, since both
must match exactly (this is a content-addressed equality check, not a
fuzzy one).

**`receipt_sha256` differs between runs of the same subject.** This means
some part of your payload is not deterministically ordered. Check for:

- an unsorted `list()` built from a `set` or `frozenset` -- the case study
  sorts `repair_affected_paths` explicitly with
  `tuple(sorted(_path_text(path) for path in repair.affected))`, because
  `repair.affected` is a `frozenset[NodePath]` with no guaranteed iteration
  order;
- dict key order depending on insertion order in a code path that isn't
  deterministic (e.g. built from a `set` iteration) -- `sha256` in
  `autofde_lab.fabric.canonical` canonicalizes JSON, but only what you hand
  it as a payload; if you build the payload from unordered collections
  without sorting first, the payload itself differs between runs even
  though the *meaning* doesn't;
- non-deterministic ordering in `PlanCache.remember` calls -- frontier keys
  are recorded in the order you call `remember`, so build your frontier
  tuple in a fixed, literal order (as `build_candidate_frontier` does),
  never from an unordered iteration.

## See also

- [Autonomic Life Planning Case Study](../case-studies/life-autonomic-controller.md)
  -- the explanation doc this guide's pattern is drawn from.
- `src/autofde_lab/agent/life_autonomic_case_study.py` -- the real source
  every code snippet in this guide adapts.
- `tests/agent/test_life_autonomic_case_study.py` -- the real test module
  this guide's step 6 templates from.
- `src/autofde_lab/agent/continuous_planning.py` -- the kernel this guide's
  API calls (`ContinuousPlanner`, `PlanningContext`, `PlanArtifact`,
  `PlanCache`, `AdmissionCode`, `admit_plan`, `affected_paths`,
  `ObservationDelta`).
