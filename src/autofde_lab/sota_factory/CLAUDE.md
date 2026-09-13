# Role

SELECT/LEARN control plane for the AutoFDE Lab SOTA factory. It represents published frontier targets,
DecisionBasis architecture spaces, ExperimentBasis conditions, deterministic experiment plans, terminal
result ingestion, aggregate score/frontier standing, failure clustering, and next-batch selection.

# Authority

- Treat a published frontier number as an external target observation to beat.
- Manufacture deterministic candidate experiment identities from lawful architecture combinations.
- Ingest terminal results that match a compiled benchmark/task/architecture identity.
- Derive the Lab's own benchmark score and `SOTA_SURPASSED` standing.
- Prune an architecture when its mathematically optimistic remaining score cannot beat the target.
- Route typed failures to the DecisionBasis dimension or external subsystem that can actually change them.

# Non-authority

- **No DO path.** Do not launch agents, model servers, subprocesses, Kubernetes, cloud APIs, GymAct
  actuation, or benchmark evaluators here.
- Does not reproduce, audit, or validate competitor runs. The published score is a target constant.
- Does not invent repairs. A failure cluster creates a bounded learning signal; evidence must establish the
  actual repair elsewhere.
- Does not promote cost, latency, tokens, or model size above benchmark score unless explicitly configured
  as a hard constraint outside this package.

# Invariants

1. Primary objective for maximize benchmarks: `Score_Lab(B) > PublishedFrontier(B)`.
2. `SOTA_SURPASSED` requires the Lab's **declared complete task population** to have terminal results. A
   one-task 100% observation for a 34-task benchmark remains `INCOMPLETE_EVALUATION`.
3. Every result must match a compiled `plan_id`, `task_id`, benchmark revision, and architecture digest.
   Drift or result mutation is a typed refusal via `ValueError` with a `REFUSED:*` code.
4. DecisionBasis dimensions are first-class: model, planner, tool, repair, replanning, verification,
   projection, memory, and budget.
5. Search is combinatorial in representation and selective in execution. Use compatibility laws and
   bounded selectors rather than blindly executing a Cartesian product.
6. Failure routing preserves causal boundaries: authority/dependency/execution/world defects are not
   disguised as agent tuning.
7. The current implementation is an ordinary DecisionBasis point, never a privileged architecture.

# Verification

```bash
python -m pytest -q tests/sota_factory
python -m autofde_lab.sota_factory compile examples/sota_factory/kubernetes-ported-current.json
```

The example intentionally declares only the currently known task while recording an expected population
of 34, so it cannot produce `SOTA_SURPASSED` until the complete benchmark task population is loaded.
