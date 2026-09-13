# AutoFDE Lab SOTA Factory

## Prime objective

The SOTA factory exists to produce **AutoFDE Lab results that beat a published benchmark frontier**.
It does not reproduce or validate competitor runs. A published score is treated as a target observation:

```text
SOTA_SURPASSED(B) iff Score_Lab(B) > PublishedFrontier(B)
```

for maximize metrics, with the inequality reversed for minimize metrics.

The Lab's own score must still come from the declared benchmark population and evaluator. A one-task
100% result is useful evidence about that architecture point, but it cannot produce `SOTA_SURPASSED`
for a 34-task target until the 34-task population is declared and completed.

`SOTA_SURPASSED` is a score standing, not the final factory standing. `DONE` additionally requires the
complete population, evaluator identity, frontier-source identity, and terminal evidence references for
every task in the winning architecture. See `SOTA-FACTORY-80-20-ERRC.md`.

## Boundary

`autofde_lab.sota_factory` is **SELECT / LEARN only**. It has no subprocess, Kubernetes, cloud,
model-server, GymAct actuation, or benchmark-execution path. It manufactures experiment identities and
ingests terminal results produced through the governed execution boundary.

```text
Published frontier target
        |
        v
BenchmarkTarget ----> DecisionSpace × ExperimentBasis
                           |
                           v
                   ExperimentCompiler
                           |
                           v
                    ExperimentPlan[]
                           |
                    [external DO path]
                           |
                           v
                      TrialResult[]
                           |
           +---------------+----------------+
           |                                |
           v                                v
       ScoreLaw                      LearningCompiler
           |                                |
           v                                v
       Scoreboard                  shared failure clusters
           |                                |
           +-------------> next_batch <-----+
                              |
                              v
                  DefinitionOfDone court
```

## DecisionBasis

The first-class architecture dimensions are:

```text
Model
× Planner / decision loop
× ToolPolicy
× RepairPolicy
× ReplanningPolicy
× VerificationPolicy
× ProjectionPolicy
× MemoryPolicy
× BudgetPolicy
```

The current system is represented as one ordinary point in this space. Existing behavior should be
extracted into named choices before new choices are invented. A benchmark must not be coupled to one
agent implementation.

`DecisionSpace` uses declarative compatibility rules rather than hidden Python predicates. This keeps
invalid combinations inspectable and serializable.

## Design for Combinatorial Maximalism

The factory represents the lawful architecture space combinatorially but does not blindly execute or
materialize its Cartesian product.

The compiler provides four selection rails:

- `BASELINE_FIRST` — freeze and measure the current architecture.
- `ONE_FACTOR_AT_A_TIME` — discriminating variants one DecisionBasis dimension from baseline.
- `PAIRWISE_COVERING` — the default maximalist rail. It constructs the admitted baseline plus every
  lawful one-factor and two-factor substitution around that baseline, then deterministically covers
  those interactions under an explicit architecture budget. It does **not** materialize the full
  Cartesian DecisionSpace first.
- `FULL_FACTORIAL` — explicit bounded exhaustive enumeration when the complete space is small enough.

For dimension cardinalities `k_i`, pairwise design construction is bounded by:

```text
O(Σ k_i + Σ(i<j) k_i*k_j)
```

rather than:

```text
O(∏ k_i)
```

The admitted baseline is a required seed of the pairwise design: maximalism may explore away from
current behavior, but it may not optimize current behavior out of the experiment before measuring it.

`candidate_limit` has two deliberately different meanings:

- under `FULL_FACTORIAL`, it bounds complete Cartesian materialization;
- under `PAIRWISE_COVERING`, it bounds the polynomial second-order candidate design.

If the second-order design itself exceeds its explicit budget, compilation refuses with
`REFUSED:PAIRWISE_DESIGN_TOO_LARGE` rather than silently claiming complete interaction coverage.

## Scoring and safe pruning

For binary E2E benchmark success, the current score is a lower bound:

```text
S = scale × passes / N
S_max = scale × (passes + (N - attempted)) / N
```

An architecture may be removed from further execution once its optimistic ceiling cannot exceed the
published frontier. This is score-law pruning, not a heuristic guess.

The scoreboard orders the primary benchmark score before cost. Cost, latency, tokens, model size, and
actuation count remain secondary unless a benchmark or authority policy explicitly makes them hard
constraints.

## Definition of Done

`DefinitionOfDone` is an evidence court distinct from `ScoreLaw`.

```text
DONE(B) :=
    PopulationDeclared(B)
  ∧ EvaluatorBound(B)
  ∧ FrontierSourceBound(B)
  ∧ ∃A. SOTA_SURPASSED(A,B)
  ∧ EvidenceBoundEveryWinnerTask(A,B)
```

This prevents a numerically winning but unreceipted result from terminating the factory.

## Failure learning

Failures are typed and clustered. The learning compiler only routes evidence; it does not invent a
repair from a string:

```text
MODEL               -> vary model
PLANNER             -> vary planner
TOOL_POLICY         -> vary tool_policy
REPAIR_POLICY       -> vary repair_policy
REPLANNING_POLICY   -> vary replanning_policy
PROJECTION          -> vary projection_policy
VERIFICATION/ORACLE -> vary verification_policy
BUDGET              -> vary budget
WORLD_MODEL          -> GymAct/world repair
AUTHORITY            -> authority boundary
DEPENDENCY           -> dependency/availability boundary
EXECUTION            -> execution boundary
UNKNOWN              -> discriminating probe required
```

Repair leverage is measured as `Δscore / Δrepair`.

## Identity law

Every experiment plan is content-addressed from benchmark revision + task + architecture digest.
Every result ingested by the factory must match a compiled plan's task, benchmark revision, and
architecture digest. Result mutation under an existing plan ID is refused.

## CLI

No packaged console script is added. Use the module entry point:

```bash
python -m autofde_lab.sota_factory compile examples/sota_factory/kubernetes-ported-current.json > plans.jsonl
python -m autofde_lab.sota_factory next examples/sota_factory/kubernetes-ported-current.json --results results.jsonl --batch-size 8
python -m autofde_lab.sota_factory status examples/sota_factory/kubernetes-ported-current.json --results results.jsonl
```

`compile` and `next` emit candidate experiment plans. They do not execute them.

## Ontology

- `ontology/sota-factory.ttl` — canonical SOTA-factory vocabulary.
- `ontology/shapes/sota-factory.shacl.ttl` — structural constraints.
- Existing `lab`, `planning`, `evidence`, `standing`, and `manufacture` ontologies remain the
  constitutional basis and are imported rather than duplicated.
