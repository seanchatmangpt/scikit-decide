# SOTA Factory: Definition of Done -> 80/20 ERRC -> Combinatorial Maximalism

## 1. Definition of Done

The factory is not done because an architecture looks promising, because a tracer task passes, or because a partial score is numerically above a published frontier.

For benchmark target `b`:

```text
DONE(b) :=
    PopulationDeclared(b)
  ∧ EvaluatorBound(b)
  ∧ FrontierSourceBound(b)
  ∧ ∃a. ScoreStanding(a,b) = SOTA_SURPASSED
  ∧ EvidenceBoundEveryWinnerTask(a,b)
```

For maximize metrics:

```text
SOTA_SURPASSED(a,b) := Score_Lab(a,b) > PublishedFrontier(b)
```

with the inequality reversed for minimize metrics.

The portfolio-level destination is:

```text
DONE(P) := ∀ b ∈ P : DONE(b)
```

where `P` is the admitted set of benchmark targets. A benchmark is a row in the experimental matrix, not a bespoke implementation branch.

## 2. Work backwards from DONE

If terminal standing requires a complete, comparable, evidence-bound score, then the factory needs only the machinery that causally contributes to that proof:

```text
DONE
  <- evidence-bound winning score
  <- complete benchmark evaluation of a winning architecture
  <- frontier-viable architecture selection
  <- discriminating bounded experiments
  <- lawful DecisionBasis combinations
  <- canonical GymAct benchmark/world basis
```

This reverses the conventional implementation order. The factory does not begin by adding agents, prompts, planners, or benchmark-specific loops. It begins from the proof obligation and manufactures only the experiments needed to discharge it.

## 3. Combinatorial maximalism law

Let the DecisionBasis dimensions be `D1 ... Dn` with cardinalities `k1 ... kn`.

The represented architecture space is:

```text
Ω_D = D1 × D2 × ... × Dn
|Ω_D| = ∏ ki
```

The factory SHOULD maximize represented lawful optionality while minimizing executed experiments.

Therefore:

> **Represent combinatorially. Search selectively. Compile aggressively.**

The default pairwise rail MUST NOT materialize `Ω_D`.

Instead, around an admitted baseline `d0`, construct the second-order discriminating basis:

```text
C2(d0) =
    {d0}
  ∪ {lawful one-factor substitutions}
  ∪ {lawful two-factor substitutions}
```

Its construction cost is polynomial:

```text
O(Σ ki + Σ(i<j) ki*kj)
```

rather than exponential/product-space materialization:

```text
O(∏ ki)
```

A deterministic greedy covering design then selects at most `M` architectures from `C2(d0)` for execution.

`FULL_FACTORIAL` remains an explicit bounded falsification rail for small spaces. It is never the default answer to a large possibility space.

## 4. 80/20 ERRC

### ELIMINATE

- Blind Cartesian materialization before pairwise selection.
- Benchmark-specific private world models that compete with GymAct truth.
- Planner-specific direct commitment paths.
- Re-running a full benchmark population for an architecture whose optimistic score ceiling can no longer beat the frontier.
- Repeated generalized cognition for already admitted HOT signatures.
- Treating source-file existence, partial task success, or a naked score as terminal SOTA proof.

### REDUCE

- Architecture executions from `∏ ki` toward a bounded second-order covering set.
- Full-population evaluation before an architecture has survived cheap discriminating probes.
- Token, model, repair, and actuation spend on dominated candidates.
- Handwritten per-benchmark orchestration.
- Duplicate repairs whose failure signatures share one latent basis defect.
- Planner/model coupling to any one benchmark adapter.

### RAISE

- Pairwise interaction coverage per executed architecture.
- Benchmark/world closure in GymAct and solution closure in DecisionBasis.
- Identity binding: benchmark revision + task + architecture + experiment + evidence.
- Independent evaluator fidelity and explicit frontier provenance.
- Repair applicability and realized cross-system leverage.
- Typed failure clustering, falsification, adversarial perturbation, and projection-loss detection.
- Reuse of admitted repairs across every applicable benchmark/architecture combination.

### CREATE

- A polynomial second-order architecture compiler that never requires Cartesian materialization for the default pairwise rail.
- An executable Definition-of-Done court distinct from score standing.
- Safe optimistic-ceiling pruning.
- Adaptive experiment batches over frontier-viable architectures only.
- Shared failure-to-basis routing:

```text
WORLD_MODEL / PROJECTION -> GymAct basis repair
MODEL / PLANNER / POLICY -> DecisionBasis repair
AUTHORITY / EXECUTION    -> governed execution boundary repair
UNKNOWN                  -> discriminating probe
```

- Portfolio scheduling where benchmark target is another experimental dimension rather than another software fork.

## 5. The 80/20 experiment loop

The useful loop is:

```text
GymBasis × DecisionBasis × ExperimentBasis
                |
                v
       bounded covering design
                |
                v
       governed external execution
                |
                v
          terminal evidence
                |
       +--------+---------+
       |                  |
       v                  v
 optimistic ceiling   failure clusters
       |                  |
       v                  v
 safe pruning       shared basis repair
       |                  |
       +--------> regenerate
                |
                v
      complete winner evaluation
                |
                v
        DefinitionOfDone court
```

For binary success over `N` tasks:

```text
S      = scale * passes / N
S_max  = scale * (passes + (N - attempted)) / N
```

If `S_max <= frontier`, further execution of that architecture is eliminated.

The early experiment objective is not "finish every architecture." It is:

```text
maximize information gained per unit cost
subject to preserving every architecture still capable of beating SOTA
```

## 6. Repair leverage

A failure should not be repaired at the cell level if it can be lifted into a shared basis law.

Measure both:

```text
RepairApplicability(r) = number of systems to which r structurally applies
RepairRealizedLeverage(r) = number of unchanged systems rerun/improved by r
```

and score economics:

```text
Leverage(r) = ΔScore / ΔRepair
```

The preferred repair is the smallest lawful change with the widest demonstrated applicability, not the largest local patch.

## 7. Acceptance conditions for combinatorial maximalism

The framework is accepted only if all of the following remain true:

1. A DecisionSpace with a Cartesian upper bound larger than `candidate_limit` can still compile under `PAIRWISE_COVERING` without materializing that Cartesian product.
2. The same space still refuses under bounded `FULL_FACTORIAL`.
3. The admitted baseline is present in the pairwise experiment set.
4. Compatibility laws exclude illegal one-factor and two-factor combinations.
5. If the polynomial pairwise design itself exceeds its explicit design budget, the compiler refuses rather than silently claiming complete pairwise coverage.
6. `SOTA_SURPASSED` cannot be inferred from incomplete benchmark population coverage.
7. `DONE` additionally requires evaluator binding, frontier-source binding, and evidence references for every winner task.
8. The SOTA factory remains SELECT/LEARN only; it gains no direct DO path.

## 8. Strategic consequence

The factory should grow by adding basis options, laws, benchmark rows, and evidence—not by multiplying bespoke orchestration code.

The intended derivative is:

```text
∂Infrastructure / ∂Benchmarks ≈ 0
∂Infrastructure / ∂DecisionSystems ≈ 0
```

while:

```text
ΔBasis -> every applicable generated experiment/system
```

That is the 80/20 expression of combinatorial maximalist SOTA: enormous lawful optionality, bounded experiment manufacture, shared learning, and an evidence court that refuses to confuse a promising result with done.
