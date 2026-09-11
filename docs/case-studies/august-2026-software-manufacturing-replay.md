# Case study: replaying August 2026 as a software-manufacturing organization

## Question

Can the engineering behavior represented by a 24,340-commit month be compiled into
planning files so heterogeneous agents can enter equivalent worlds and reproduce
full-stack delivery behavior rather than merely imitate commit messages?

## Model

A commit is evidence of a repository transition, not the planning unit. The
compiler admits normalized historical events and groups them into episodes using an
explicit `episode`/`workstream`, PR number, branch/ref, or repository fallback.
Each episode becomes a deterministic partial-order planning file:

```text
historical events
  -> episode inference
  -> intent + engineering-surface inference
  -> dependency/causal edges
  -> planning file
  -> replay world
  -> agent selections
  -> deterministic simulation receipt
```

The surface vocabulary spans source, tests, GitHub, CI/CD, infrastructure as code,
cloud, containers, security, observability, docs, and release behavior. The plan
also records required authority classes, but those classes are descriptive. The
replay world cannot acquire or exercise external authority.

## Historical-count fence

The reported August total and the export evidence count are separate variables:

```text
reported_commit_count = 24,340
observed_commit_count = count(commit events in admitted export)
complete_history_observed = reported == observed
```

This is deliberate. GitHub search surfaces can be capped or incomplete. A compiler
that silently treats a partial search result as the whole month would manufacture
false evidence.

## Agent gym

`ReplayWorld.admissible_actions()` exposes only steps whose declared dependencies
are satisfied. An agent selects a step id; `apply()` records the transition. A
reference policy deterministically chooses the first admissible step until closure.
The resulting receipt is `ALIVE` only when every plan step has been completed and
always reports:

```json
{
  "authority": "NONE",
  "do_authority": false,
  "evidence_kind": "SIMULATION_RECEIPT"
}
```

This lets Claude, Codex, Gemini, symbolic planners, RL policies, or planner leagues
compete over the same planning file without conflating simulation with GitHub,
cloud, deployment, or release authority.

## 24,340-event scale court

The Chicago court constructs 24,340 normalized commit observations, compiles them
in forward and reversed input order, and requires identical corpus and plan
digests. The repeated transition compacts to one plan step while all 24,340 commit
SHAs remain in the historical trace. This validates scale and determinism without
pretending the synthetic scale court is the real August export.

## Real GitHub ingestion (2026-09-01)

`fetch_github_events(repo, since=..., kinds=...)` queries the real, locally-authenticated
`gh` CLI directly (`gh api`, no mocking) and normalizes the response into the same
`HistoricalEvent` shape the checked-in fixture uses. This is a real subprocess against a
real repository, not a synthetic corpus: replaying this session's own recent
`seanchatmangpt/autofde-lab` history compiled 16 real episodes (merges, pull requests,
workflow runs) from 110 real events, and one of those episodes replayed to
`state: ALIVE` through `ReplayWorld`.

Widening `GITHUB_FETCHABLE_KINDS` (currently `commit`, `pull_request`, `review`,
`workflow_run`, `release`, `issue`, `deployment`) is how the agent/planner frontier gains
more distinct real, actuatable step kinds — each fetchable kind that GitHub actually
returns data for becomes its own admissible plan-step type in `ReplayWorld`, not just more
commits. A real bug in the first pass of this ingestion (`--paginate --slurp` silently
returning zero events for an object-wrapped endpoint like `actions/runs`, rather than
erroring) was caught and fixed by comparing the tool's own output against an independent
`gh api ... --jq '.total_count'` call before trusting either — see
`test_fetch_github_events_workflow_run_kind_is_not_silently_empty` for the regression
court. Still observation-only: `authority: NONE`, `do_authority: false`, no endpoint used
performs a write.

CLI: `python -m autofde_lab.agent.software_manufacturing_history fetch <owner/repo>
<output.json> --since <ISO-8601> [--until <ISO-8601>] [--kinds ...]`.

## GymAct bridge: the plan as a real gym episode (2026-09-01)

`autofde_lab.agent.software_manufacturing_gymact_bridge` wraps `ReplayWorld` in a real
`gymact.providers.Environment`/`EnvironmentProvider` pair (`SoftwareManufacturingEnvironment`/
`SoftwareManufacturingProvider`), registered as a real, gymact-discoverable plugin
(`[project.entry-points."gymact.providers"]`, name `software_manufacturing`), structurally
matching this repo's own `azuregoat_privesc/gymact_bridge.py` reference integration. One
`Capability` per compiled plan step; `actuate()` refuses (typed `ActuationRefused`, never a
silent no-op) any step that is not currently admissible from the real dependency-cone state,
mirroring `ReplayWorld.apply()`'s own refusal exactly rather than re-deriving it.

Verified this session against the real checked-in fixture, driven entirely through the real
`gymact.runtime.GymAct` kernel (not by calling `ReplayWorld` directly): materialize → 14 real
`act()` calls closing every step → `verify(episode_id, {"state": "ALIVE"})` → checkpoint →
2 more acts → restore → re-observe confirms the restored state exactly. All receipts standing
`ALIVE`; `ConformanceChecker().check(operations)` confirms the operation sequence is a legal
GymAct lifecycle. A real bug was caught doing this: `Environment.observe()` originally had no
`"state"` field, and `GymAct.verify()` independently judges `expected` against a fresh
`observe()` read (never trusting a provider's own `verify()` self-report) — so the first pass
silently failed verification until `observe()` was made to include the same real
`ReplayWorld.receipt()` fields (`state`, `authority`, `do_authority`, `evidence_kind`,
`receipt_sha256`) that `verify()` and `checkpoint()` already exposed.

**Scope, stated precisely.** This is REPLAY mode only, in the vocabulary of a fuller
"August as a computational laboratory" architecture (world model → counterfactual episodes →
heterogeneous policies → real/simulated consequences → receipts → comparative learning): the
trajectory a materialized episode can take is exactly the admissible-action frontier the
compiled plan's own partial order already allows — no transition-probability model, no
counterfactual branching beyond that partial order, no policy-competition harness, no DfCM
possibility-frontier receipts, and no escalation to a real sandbox/BRCE execution path. Those
are each their own real design program (calibrating failure/repair/latency distributions from
the empirical GitHub corpus; a small stable action vocabulary decoupled from per-step
capability IRIs; running many policies against the same world/seed; information-partitioned
observation projections per role) — worth building, not attempted in this pass, and not
implied as done by this section.

## Next experiment

Materialize the complete August export across repositories and run multiple policies
against the resulting episode set. Compare trajectory closure, surface coverage,
repair frequency, dependency violations, information gain, and option preservation.
The benchmark unit is then an operating software-manufacturing organization, not an
isolated coding issue. The real-GitHub ingestion above is a step toward that: the same
`fetch_github_events` call, pointed at a wider `since`/repository set, is how "materialize
the complete August export" stops being a checked-in synthetic fixture and becomes a real,
replayable pull from the actual history.
