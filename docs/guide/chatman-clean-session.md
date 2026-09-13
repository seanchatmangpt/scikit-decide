# Chatman Clean-Session interoperability

`ChatmanCleanSessionDomain` exposes the Clean-Session Environment Prime as a
scikit-decide deterministic planning domain. It preserves the framework's
capability-composition contract while keeping consequential execution outside
the planning model.

## Boundary

```text
TaskEnvelope + RouteSpec[]
        ↓
ChatmanCleanSessionDomain          SELECT / CONSTRUCT only
        ↓
solver-generated SessionAction[]
        ↓
execute_actions(..., broker=BRCE)  exclusive DO boundary
        ↓
BrokerReceipt[]
        ↓
ExecutionReceipt + standing
```

The domain models:

```text
parse → route → admit → diagnose/repair → construct → actuate
→ observe consequence → verify → receipt → replay/hook → standing
```

`ACTUATE` is a modeled planning edge, not ambient authority. During actual
execution, `execute_actions` refuses the edge unless a broker is supplied. The
broker must return a receipt bound to the exact deterministic intent identity.
Failures, refusals, unsupported capabilities, build failures, and blocked
execution remain typed standings and are also receipted.

## scikit-decide contract

The domain subclasses `DeterministicPlanningDomain` and implements:

- deterministic initialization;
- state-dependent applicable actions;
- deterministic transitions;
- transition costs;
- goal and observation spaces;
- terminal-state detection.

It is registered as the `ChatmanCleanSession` domain entry point. Compatible
scikit-decide planners can therefore select among environment-manufacturing
routes. A failed edge remains route evidence; it does not classify the task
until all relevant routes have been attempted or ruled out.

## Replay

`replay_execution` never repeats a command directly. It constructs a new
`ActuationIntent` containing `replay_of=<prior execution receipt>` and sends it
through the broker, producing a new broker receipt and execution receipt.

## Schemas

- `schemas/chatman-clean-session-task.schema.json`
- `schemas/chatman-clean-session-receipt.schema.json`

These JSON Schemas provide bidirectional, language-neutral exchange surfaces for
star-toml, ggen, BRCE, process-evidence, and other Chatman ecosystem components.
`ExecutionReceipt.from_mapping` re-admits a received document by recomputing task,
state, broker-intent, broker-receipt, action-lane, and execution-receipt identities.
