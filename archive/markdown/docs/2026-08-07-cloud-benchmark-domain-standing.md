# Cloud-Security Planning Domain Standing (AzureGoat / TerraGoat / CloudGoat / Kubernetes-Goat)

AzureGoat, TerraGoat, CloudGoat, and Kubernetes-Goat are real cloud pentest/misconfiguration
benchmark vendors (deliberately-vulnerable Azure, Terraform, AWS, and Kubernetes environments
respectively), wired here as sosa/PROV-style planning domains and solved with the real Astar
C++ solver. What was measured: real repeated solves, 2026-08-07, on this machine, no CI, no
mocks.

## Standing Table (evidence: 3 real Astar runs per domain, fresh domain_factory each run)

| domain | runs_attempted | runs_solved | plan_length min/max | cost | standing |
|---|---|---|---|---|---|
| azuregoat_privesc | 3 | 3 | 10 / 10 | 10.0 / 10.0 / 10.0 (deterministic) | **ALIVE** |
| terragoat | 3 | 3 | 8 / 8 | 8.0 / 8.0 / 8.0 (deterministic) | **ALIVE** |
| cloudgoat_iam_privesc | 3 | 3 | 6 / 6 | not captured (`sample_action`/`step` path, no per-step Value extracted — reported `None`, not fabricated) | **ALIVE** |
| k8s_goat_rbac_escalation | 3 | 3 | 5 / 5 | not captured (same reason) | **ALIVE** |

All four domains solved 3/3 runs each, with `plan_length` identical across all 3 runs per
domain (no variance) — that satisfies the stated ALIVE bar (3/3 solved, deterministic plan
length, `error: None` throughout). None qualifies as PARTIAL_ALIVE (no run failures, no
length/cost variance) or BLOCKED (no construction/solve/goal failures, no error strings to
quote).

One caveat on `cloudgoat_iam_privesc` and `k8s_goat_rbac_escalation`: their cost figure is
`None` because the harness exercised a different call path (`solver.sample_action`/`domain.step`
loop) than `azuregoat_privesc`/`terragoat` (`solver.get_plan`), not because a run failed — this
is an instrumentation gap in the measurement script, not a solve defect, and does not by itself
demote standing since `solved`/`plan_length`/`error` are all clean 3/3.

## Reliability and "is it real" — grounded in these numbers only

By the measured criteria (solve rate and plan-length determinism), **no domain is more or less
reliable than any other** — all four are tied at 3/3 solved with zero plan-length variance and
zero errors; nothing in this dataset differentiates "most reliable" beyond that tie. The only
measured secondary signal is wall-clock timing: `azuregoat_privesc` and `terragoat` show
monotonically decreasing per-run times (2.79–3.43 ms and 8.08–8.59 ms respectively, consistent
with ordinary warm-up), while `cloudgoat_iam_privesc` and `k8s_goat_rbac_escalation` each show
a timing jump on run 3 (4.20 ms vs ~3.1 ms, and 3.83 ms vs ~2.96 ms) — but this is a timing
artifact, not a solve-outcome signal, and there is no data here to explain its cause. On the
specific question of whether any domain "is not yet real" — relies on a hand-transcribed
fixture rather than the actual vendor checkout — **the provided measurements contain no
evidence either way**: the notes describe only a cost-extraction code path difference
(`get_plan` vs `sample_action`/`step`), not fixture-vs-vendor-checkout provenance for any
domain. Answering that question honestly would require the discovery/construction logs (what
`domain_factory` actually loaded for each domain), which are not part of this dataset —
reporting a verdict on fixture-vs-real without them would be UNVERIFIED, and none is asserted
here.

## Falsifiers

What would invalidate this report:

- A domain silently using a hand-transcribed fixture instead of the real vendored
  attack-manual (AzureGoat/CloudGoat) or Terraform file (TerraGoat) — the construction/discovery
  logs from `domain_factory` were not captured in this run and would be needed to rule this out.
- A "solved" run that reaches a state satisfying the goal predicate but not the manual's actual
  documented endpoint (goal-predicate under-specification masking a shallow or wrong solve).
- Nondeterministic Astar output masked by only running 3 times — 3/3 identical plan lengths is
  evidence against variance at this sample size, not proof of full determinism across all seeds
  or tie-breaking orders.
- The `cost: None` fields for `cloudgoat_iam_privesc` and `k8s_goat_rbac_escalation` turning out
  to reflect a real solver defect on that path, rather than the claimed instrumentation gap
  (`sample_action`/`step` not extracting per-step Value) — this claim itself rests on reading the
  harness code path, not on an independent re-run that forces `get_plan` on those two domains.
- Any of the four `domain_factory` calls silently catching and swallowing a construction
  exception rather than raising, which would make "3/3 solved" describe a degenerate or
  trivially-true domain instead of the intended benchmark.

## Final Standing

- AzureGoatPrivesc: ALIVE, 3/3 real Astar solves, plan length 10 (deterministic), cost 10.0 all
  three runs.
- TerraGoat: ALIVE, 3/3 real Astar solves, plan length 8 (deterministic), cost 8.0 all three
  runs.
- CloudGoatIamPrivesc: ALIVE, 3/3 real Astar solves, plan length 6 (deterministic); cost not
  captured due to a `sample_action`/`step` instrumentation gap, not a solve failure.
- K8sGoatRbacEscalation: ALIVE, 3/3 real Astar solves, plan length 5 (deterministic); cost not
  captured due to the same instrumentation gap.
