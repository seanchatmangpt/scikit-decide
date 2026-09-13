# GymAct

GymAct is a ggen-manufactured, transport-neutral actuation protocol for executable benchmark and gym environments.

It is intentionally designed from the **gym's lifecycle**, not from AutoFDE's current implementation. A gym presents a world, a scenario, an episode, observations, actions, effects, terminal conditions, scores, and cleanup obligations. GymAct normalizes those semantics and then projects them into concrete transports.

## Stable semantic lifecycle

```text
discover
  ↓
materialize
  ↓
configure
  ↓
reset
  ↓
start
  ↓
observe ⇄ act
  ↓
verify
  ↓
score
  ↓
teardown
```

`checkpoint` and `restore` are recovery operations available to profiles that support them.

The crucial distinction is:

```text
actuation acknowledgement != observed effect != verified objective != score
```

A transport may report that an action was accepted. GymAct does not promote that acknowledgement into a verified consequence.

## Four gym interaction models

The current ForwardBench corpus collapses into four semantic families:

| Interaction model | Current adapter families | Characteristic loop |
|---|---|---|
| `EPISODIC_STEP` | CUBE, Gymnasium, BrowserGym | reset → observe ⇄ act → terminal |
| `TASK_HARNESS` | Harbor, native command runners | materialize → run task → verify |
| `TOOL_SESSION` | MCP | connect/discover → call tools → observe |
| `RECONCILIATION` | Kubernetes, Terraform | observe desired/current → apply → watch convergence → verify |

Those are semantics, not implementations. A future transport can expose the same GymAct lifecycle over MCP, A2A, HTTP, BPMN, WIT/WASM, a Rust library, or another orchestration surface.

## Authority

GymAct never grants authority.

Every actuation request carries an optional `authority_ref`. Operations are classified as `READ`, `PREPARE`, `DO`, or `VERIFY`. An executor MUST refuse consequential `DO` operations when the selected gym or environment requires authority and no admissible authority reference exists.

The protocol therefore remains usable by AutoFDE/BRCE without coupling GymAct itself to AutoFDE.

## ggen manufacture

`ggen.toml` combines:

- the GymAct operation ontology;
- interaction profiles;
- the ForwardBench benchmark graph in `../docs/papers/papers.ttl`;
- observed ForwardBench lock overlays.

From those graphs ggen manufactures:

- `protocol.json` — canonical operation vocabulary;
- `profiles.json` — semantic interaction profiles;
- `subjects.json` — all known benchmark subjects mapped to GymAct profiles;
- `mcp-tools.json` — generic GymAct MCP tool surface;
- `a2a-skills.json` — generic A2A skill surface;
- `gymact.bpmn` — executable BPMN-shaped lifecycle;
- `rust/lib.rs` — transport-neutral Rust actuation ABI;
- `wit/gymact.wit` — WASM component boundary.

No per-benchmark MCP server or BPMN flow is hand-authored.

## Generate

```bash
cd gymact
ggen sync run
```

The generated tree is intentionally disposable. The semantic source is RDF + templates.

## Library direction

GymAct is structured so it can become an independent library/repository later. AutoFDE should consume the generated GymAct subject registry and submit `ActuationIntent`s; it should not own benchmark-specific lifecycle semantics.

The future split is:

```text
papers.ttl / benchmark ontology
          ↓
        GymAct
  semantic actuation ABI
          ↓
        ggen
  ┌───────┼───────────┬──────────┬─────────┐
  ▼       ▼           ▼          ▼         ▼
 Rust    MCP         BPMN        A2A       WIT
  │
  ▼
executor / authority boundary
```

## Current standing

This change establishes and validates the abstraction and its projections. It does **not** claim that all vendored gyms have reached scenario execution. Existing ForwardBench standings remain authoritative.
