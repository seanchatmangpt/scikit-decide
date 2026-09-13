# Appendix J. Ninety-Day Agentic Architecture Plan

Use this template in role proposals, interviews, and onboarding. Replace generic milestones with one exact workflow.

## Role and sponsor

```text
Role:
Executive sponsor:
Technical sponsor:
Workflow owner:
Security/governance partners:
Operating team:
```

## Subject

```text
Workflow:
Current system boundary:
Users:
Customer or business consequence:
Known constraints:
Excluded scope:
```

## Outcome contract

> Given **[admitted observations and systems]**, the team will produce **[bounded operating outcome]** within **[time/cost/quality boundary]**, with **[authority model]**, validated by **[evidence]**, and recorded through **[receipt path]**.

## Baseline

Record before construction:

- current cycle time;
- volume;
- labor and review time;
- infrastructure or model cost;
- error and exception rates;
- customer or employee outcome;
- number of handoffs;
- existing automation;
- incident history;
- current authority process.

If the baseline is unavailable, month one must create it.

## Admission criteria

The workflow is admitted only if:

- the subject and owner are exact;
- required data can be accessed lawfully;
- a production or staging tool path exists;
- acceptance criteria are measurable;
- high-consequence actions have an authority path;
- representative and negative fixtures can be collected;
- the cost of a bounded pilot is acceptable;
- an operating team can own the result.

## Day 0–30: Observe and admit

### Activities

1. Interview outcome owner and frontline operators.
2. Map the current task graph.
3. Trace data and tool access.
4. Identify irreversible transitions.
5. Collect common and exceptional cases.
6. Measure baseline.
7. Inventory existing model and automation work.
8. Identify repeated intelligence expense.
9. Select the narrow pilot.
10. Agree on acceptance and refusal criteria.

### Deliverables

- current-state architecture;
- authority map;
- baseline report;
- scenario corpus;
- risk register;
- exact pilot subject;
- acceptance specification;
- decision record approving construction.

### Day-30 receipt

```yaml
standing: SUBJECT_ADMITTED
subject: "exact workflow and scope"
observed: "systems, costs, and failures"
approved: "pilot construction"
blocked: "unresolved dependencies"
```

## Day 31–60: Construct and validate

### Architecture path

```text
Observation
    → normalization
    → admission
    → semantic module
    → planner/workflow policy
    → candidate artifact or intent
    → validator
    → approval boundary
    → staging action
    → receipt
    → cache
```

Use only the layers required by the workflow.

### Activities

1. Define canonical state and schemas.
2. Implement or expose tools through controlled interfaces.
3. Create semantic modules with evaluation examples.
4. Add deterministic workflow or formal planning where decisions require it.
5. Build common-case and negative fixtures.
6. Add typed refusal.
7. Implement cost and latency instrumentation.
8. Cache validated common cases.
9. Run staging execution.
10. Conduct security, user, and operator review.

### Deliverables

- bounded working slice;
- automated and human evaluation report;
- negative-fixture report;
- total-system cost model;
- permission and approval implementation;
- staging receipts;
- operating runbook;
- production decision recommendation.

### Day-60 receipt

```yaml
standing: VALIDATION_ALIVE
subject: "exact staging subject and revision"
commands:
  - "verification command"
result: "observed behavior"
limitations:
  - "unsupported case"
production_decision: "approve | repair | refuse"
```

## Day 61–90: Controlled actuation

### Activities

1. Restrict launch to admitted subjects.
2. Execute through the authorized broker.
3. Monitor cost, quality, and exceptions.
4. Compare against baseline.
5. Investigate every consequential failure.
6. Repair narrow causes and add permanent fixtures.
7. Train the operating team.
8. Define cache invalidation and policy maintenance.
9. Identify reusable platform components.
10. Present the next-quarter decision.

### Deliverables

- production receipts;
- baseline comparison;
- exception and incident report;
- human-review measurement;
- user and operator feedback;
- reusable component inventory;
- governance and operating ownership;
- next-workflow ranking;
- quarter-two roadmap.

### Day-90 receipt

```yaml
standing: OUTCOME_ALIVE
subject: "exact production scope"
baseline: "before"
result: "after"
total_cost: "including review and infrastructure"
authority: "who approved and executed"
replay: "how the result can be inspected"
falsifiers:
  - "condition that would invalidate the claim"
```

## Executive scorecard

| Measure | Baseline | Day 90 | Target | Standing |
|---|---:|---:|---:|---|
| Cycle time |  |  |  |  |
| Accepted outcomes |  |  |  |  |
| Human review minutes |  |  |  |  |
| Error/exception rate |  |  |  |  |
| Total unit cost |  |  |  |  |
| Reused-policy rate |  |  |  |  |
| Authority violations |  |  | 0 |  |
| Replay completeness |  |  | 100% |  |

## Pilot falsifiers

The pilot should be stopped or redesigned if:

- representative inputs cannot be admitted;
- evaluation cannot distinguish acceptable behavior;
- total review cost exceeds the current process;
- required authority cannot be established;
- exceptions dominate the common path;
- users reject the workflow for substantive reasons;
- data or security constraints are violated;
- the selected outcome lacks economic consequence.

Stopping a bad pilot with an exact receipt is a successful architectural result.

## Quarter-two options

Do not assume automatic scale. Choose among:

- deepen the same workflow;
- expand to a neighboring scenario;
- extract a shared platform capability;
- improve evaluation and reliability;
- reduce cost through caching;
- redesign organizational roles;
- pause pending a blocker;
- refuse expansion.

The first ninety days should make this decision easier, not merely make the demonstration larger.
