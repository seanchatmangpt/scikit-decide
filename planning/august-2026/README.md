# August 2026 software-manufacturing planning corpus

This directory is the reproducible planning-file surface for reconstructing the
August 2026 engineering trajectory as software-manufacturing episodes.

The historical headline is **24,340 reported commits**. The compiler deliberately
keeps that reported total separate from `observed_commit_count`. The checked-in
example contains only the evidence in `history/full-stack-example.json`, so its
materialized manifest correctly says the complete 24,340-commit history has **not**
been observed. A future complete export can be compiled without changing the plan
or replay schemas.

## Files

- `history/full-stack-example.json` — normalized GitHub/delivery observations across
  source, tests, IaC/cloud, containers, security, observability, CI/CD, docs, PR,
  merge, release, and default-branch containment.
- `materialized/manifest.json` — corpus identity, reported-versus-observed counts,
  repository/surface coverage, and planning digests.
- `materialized/august-full-stack-example.plan.json` — deterministic partial-order
  planning file manufactured from the normalized observations.

## Compile

```bash
PYTHONPATH=src python -m autofde_lab.agent.software_manufacturing_history compile \
  planning/august-2026/history/full-stack-example.json \
  /tmp/august-plans \
  --period 2026-08 \
  --reported-commit-count 24340
```

## Replay

```bash
PYTHONPATH=src python -m autofde_lab.agent.software_manufacturing_history replay \
  /tmp/august-plans/august-full-stack-example.plan.json
```

Replay is a powerless gym. Required authority classes in a plan are descriptive
observations only; the replay receipt always carries `do_authority=false`.

## Complete-history materialization

Export normalized events for the full period using stable event ids, timestamps,
repository identity, event kind, branch/PR/workstream identity, commit SHA when
applicable, changed paths, causal parents, and optional intent/objective metadata.
Then compile that export with `--reported-commit-count 24340`.

Only when `observed_commit_count == 24340` will the corpus set
`complete_history_observed=true`. This prevents a partial GitHub search result from
being promoted into a false reconstruction of the month.
