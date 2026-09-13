# v26.9.1 Jira-Style Plan: AutoFDE Lab

## Define (Charter)

Two workstreams landed on `origin/master`'s HEAD (`61840ec`, PR #86, merged
2026-08-27) within the last 24 hours (since 2026-08-31), both still unmerged as of
this writing:

- **`feat/fortune5-safe-dfcm-sim`** — a Fortune-5-scale SAFe (Scaled Agile
  Framework) digital twin simulation for DfCM (Design for Cognitive/Continuous
  Manufacturing) portfolio planning. Two commits add a full SAFe backlog
  hierarchy (epics/features/stories/portfolio-kanban) as a simulatable model.
- **`adapt/aps-autofde-protocol`** — an APS (a protocol/ontology profile,
  "Autonomous Planning/Protocol Space") semantic adaptation: adds an RDF/OWL
  ontology profile, SHACL shape constraints, a reconstitution-trial fixture, a
  Chicago-style test suite, and a CI qualification workflow gating the profile
  on pull requests.

The v26.9.1 workstream charter, inferred from these branch names and commits, is:
**extend AutoFDE Lab's planning/verification substrate in two independent
directions — (1) a realistic enterprise-scale simulation environment for
validating DfCM decision-making at Fortune-5 SAFe portfolio scale, and (2) a
formal ontology/protocol profile (APS) that gives cross-agent planning artifacts
a verifiable, SHACL-constrained semantic contract with receipt-chain proof.**
Both are additive (no existing files modified in either branch's diff vs.
merge-base), so the workstreams are not in tension architecturally, but they do
represent two different investments competing for the same v26.9.1 release
window: simulation-realism vs. protocol-formalism.

Scope for this plan: bring both branches to a mergeable, CI-green state against
current `master`, sequence their merge, and define post-merge verification and
monitoring. Out of scope: designing new features beyond what each branch already
proposes; touching `main`/`master` or any other existing branch directly.

## Measure (Current State — Real Git Evidence)

All commit data below is from `git log`/`git branch -a` against a fresh clone of
`https://github.com/seanchatmangpt/autofde-lab.git`, with all remote branches
fetched (`git fetch origin "+refs/heads/*:refs/remotes/origin/*"`).

### Default branch

- `master` HEAD: `61840ec` — "Merge pull request #86 from
  seanchatmangpt/feat/continuous-plan-memory" (2026-08-27 18:28:59 -0700)

### Branches with commits since 2026-08-31 (last 24h at time of this plan)

Only two branches have commits after 2026-08-31 — confirmed by walking
`git log -1 --date=iso-strict` across all 44 remote branches and sorting by date;
no other branch has a commit newer than 2026-08-28:

| Branch | SHA | Date | Message |
|---|---|---|---|
| `feat/fortune5-safe-dfcm-sim` | `dff0536` | 2026-08-31 23:12:34 -0700 | model full SAFe backlog |
| `adapt/aps-autofde-protocol` | `aab070f` | 2026-08-31 22:59:38 -0700 | qualify protocol on PRs |

`feat/fortune5-safe-dfcm-sim` has the latest push overall across the whole
repository (`dff0536` at 23:12:34, 13 minutes after `adapt/aps-autofde-protocol`'s
last commit).

### `feat/fortune5-safe-dfcm-sim` — full commit list (branch tip back to merge-base)

```text
dff0536 2026-08-31 23:12:34 -0700 feat(sim): model full SAFe backlog hierarchy
82e8fc8 2026-08-31 23:07:10 -0700 feat(sim): add Fortune-5 SAFe DfCM digital twin
61840ec 2026-08-27 18:28:59 -0700 Merge pull request #86 (= master HEAD, merge-base)
```

- Ahead of `master`: 2 commits. Behind `master`: 0 commits (branches directly
  off current `master` HEAD — no rebase needed).
- Diff vs. merge-base: 10 files changed, 1125 insertions(+), 0 deletions — purely
  additive, all new files under `src/autofde_lab/simulation/fortune5_safe/`
  (`__init__`, `__main__`, `dfcm`, `engine`, `model`, `space`, `topology`),
  `tests/simulation/test_fortune5_safe.py`, and
  `docs/fortune5-safe-simulation.md`.

### `adapt/aps-autofde-protocol` — full commit list (branch tip back to merge-base)

```text
aab070f 2026-08-31 22:59:38 -0700 ci(aps): qualify protocol profile on pull requests
c9ad4d1 2026-08-31 22:59:04 -0700 style(aps): align verifier with quality gate
0a43968 2026-08-31 22:56:03 -0700 test(aps): verify protocol bridge and receipt chain
2fc44a2 2026-08-31 22:55:51 -0700 test(aps): add connected reconstitution trial fixture
52f2ff3 2026-08-31 22:55:41 -0700 feat(ontology): constrain APS protocol profile
24fa63e 2026-08-31 22:55:31 -0700 feat(ontology): add APS semantic profile
61840ec 2026-08-27 18:28:59 -0700 Merge pull request #86 (= master HEAD, merge-base)
```

- Ahead of `master`: 6 commits. Behind `master`: 0 commits (also branches
  directly off current `master` HEAD).
- Diff vs. merge-base: 5 files changed, 470 insertions(+), 0 deletions — purely
  additive: `ontology/aps-autofde-profile.ttl`,
  `ontology/shapes/aps-autofde-profile.shacl.ttl`,
  `tests/fixtures/aps/reconstitution-trial.ttl`,
  `tests/test_aps_protocol_profile_chicago.py`, and a new GitHub Actions
  workflow `.github/workflows/aps-protocol-profile.yml`.

### No file overlap

The two branches touch disjoint file sets (simulation code/tests/docs vs.
ontology/shapes/tests/CI workflow). No merge conflicts are expected between them
when both are eventually integrated into `master`.

### Adjacent context (not in the last-24h window, but relevant infrastructure)

- `.github/workflows/` already contains 29 workflows, including
  `continuous-planning-fortune5-crown.yml`, `fortune5-ggen.yml`, and
  `r80-forced-top25-fanout.yml` — prior Fortune-5/SAFe-flavored automation this
  new simulation branch extends conceptually.
- `ontology/` already has ~32 files/subdirectories — the APS branch adds one
  profile plus one SHACL shape file into an existing ontology-driven pattern
  (see repo-root `ggen.toml`, `ggen/`, `packs/` — RDF/SHACL-to-code generation
  is an established repo convention, so APS's approach is consistent with it).

## Explore (Options Implied by Branch Names/Commits)

1. **Sequential merge, simulation first** — merge
   `feat/fortune5-safe-dfcm-sim` (smaller diff, no CI workflow changes, lower
   integration risk) before `adapt/aps-autofde-protocol` (adds a new CI gate).
   Pro: lower-risk change lands first, establishing a clean baseline for the
   riskier CI-gate change. Con: does not reflect actual chronological order
   (APS's ontology/test commits started earlier at 22:55, though its CI-gate
   commit landed after fortune5's start).

2. **Sequential merge, protocol first** — merge `adapt/aps-autofde-protocol`
   first since it establishes a new verification primitive (SHACL-constrained
   receipt chain) that other simulation/planning work (including
   fortune5-safe-dfcm-sim's future consumption of planning artifacts) could
   validate against. Con: introduces a new required CI job
   (`aps-protocol-profile.yml`) before the simulation branch has been evaluated
   against it.

3. **Merge both independently, no cross-wiring** — since the two branches
   share zero files, they can each be merged straight into `master` in either
   order with no rebase step required (each is a fast-forward-compatible
   2-commit or 6-commit diff off current HEAD). This is the lowest-effort path
   and matches "no file overlap" from Measure.

4. **Combine into one integration branch first** — create a
   `integration/v26.9.1-fortune5-aps` branch merging both, run the full test
   suite once, and open a single PR. Pro: one CI run validates both together.
   Con: mixes two independently-reviewable concerns into one PR, weakening
   attribution and rollback granularity; this repo's existing
   `integration/all-relevant-20260819` and
   `integration/all-relevant-20260819` naming pattern shows this approach is
   already used elsewhere in the repo, but it trades review granularity for
   convenience.

**Recommended option: Option 3** (merge both independently, in either order) —
it has the least engineering overhead, matches the disjoint-file-set evidence
from Measure, and preserves independent attribution/rollback per workstream,
consistent with this repo's many small `feat/*`, `fix/*`, `adapt/*` branches
that are evidently merged one at a time via PR (see `master`'s PR #86 merge
commit as the pattern).

## Develop (Concrete Next Engineering Steps)

### `feat/fortune5-safe-dfcm-sim`

1. Rebase check: already 0 commits behind `master` — no rebase needed as of
   this plan's writing; re-verify immediately before merge since other
   branches may land on `master` in the interim.
2. Run the new test module directly: `pytest tests/simulation/test_fortune5_safe.py -v`
   to confirm the 92-line test file passes standalone (Chicago-style — real
   objects/state assertions per this repo's testing discipline, not mocked
   interactions; verify with a grep for
   `unittest.mock|Mock(|MagicMock|patch(|monkeypatch` over
   `tests/simulation/test_fortune5_safe.py` and confirm zero matches, or that
   any match is a named, justified exception).
3. Run the full existing simulation test directory
   (`pytest tests/simulation/ -v`) to confirm no regression against pre-existing
   simulation tests.
4. Lint/format check: `ruff check src/autofde_lab/simulation/fortune5_safe/` and
   `ruff format --check` (this repo enforces "deterministic Ruff formatting" per
   recent master commits `4677efe`/`b65d16a`) before opening a PR.
5. Confirm `docs/fortune5-safe-simulation.md` cross-references existing
   Fortune-5 CI workflows (`continuous-planning-fortune5-crown.yml`,
   `fortune5-ggen.yml`) if the new simulation is meant to be consumed by them —
   currently the branch's diff does not touch any `.github/workflows/` file, so
   confirm whether wiring the new simulation into those existing workflows is
   in scope for v26.9.1 or a follow-up.
6. Open a PR from `feat/fortune5-safe-dfcm-sim` into `master`, run the standard
   `pr-ci.yml`/`ci.yml` gates.

### `adapt/aps-autofde-protocol`

1. Rebase check: already 0 commits behind `master` as of this plan's writing —
   re-verify immediately before merge.
2. Validate the new SHACL shape file against the new ontology profile directly:
   confirm `ontology/aps-autofde-profile.ttl` validates cleanly against
   `ontology/shapes/aps-autofde-profile.shacl.ttl` using this repo's existing
   SHACL validation tooling (check `Justfile`/`ggen.toml` for an existing
   `just validate-shacl`-style target before writing a new one).
3. Run the new Chicago-style test suite:
   `pytest tests/test_aps_protocol_profile_chicago.py -v`, and independently
   confirm it exercises the real reconstitution-trial fixture
   (`tests/fixtures/aps/reconstitution-trial.ttl`) rather than a mocked
   receipt-chain object — per this repo's Chicago-testing convention, grep
   `unittest.mock|Mock(|MagicMock|patch(|monkeypatch` over
   `tests/test_aps_protocol_profile_chicago.py` and confirm zero matches.
4. Dry-run the new CI workflow (`aps-protocol-profile.yml`) locally if a local
   Actions runner (e.g. `act`) is available, or at minimum lint it with
   `actionlint` before merge, since it introduces a new required-check surface
   for future pull requests.
5. Confirm the new workflow's trigger scope (`on: pull_request`) does not
   conflict with or duplicate an existing quality gate already in
   `pr-ci.yml`/`ci.yml`.
6. Open a PR from `adapt/aps-autofde-protocol` into `master`, run the standard
   `pr-ci.yml`/`ci.yml` gates plus the new `aps-protocol-profile.yml` gate on
   its own PR (self-qualifying).

## Implement (Merge Order, Verification Gates, Rollout/Monitoring)

### Merge order

1. Merge `feat/fortune5-safe-dfcm-sim` into `master` first (smaller diff, no
   new CI surface, additive-only — lowest integration risk).
2. Re-fetch `master`, confirm `adapt/aps-autofde-protocol` still applies
   cleanly (no file overlap expected per Measure, but re-verify with
   `git merge-base` and a dry-run `git merge --no-commit --no-ff` before
   opening its PR).
3. Merge `adapt/aps-autofde-protocol` into `master` second — its new CI gate
   (`aps-protocol-profile.yml`) then becomes part of the standing pipeline for
   all subsequent PRs, including any future work that touches the fortune5-safe
   simulation, so sequencing it after the simulation merge avoids retroactively
   failing an already-in-flight simulation PR against a gate it was never
   designed against.

### Verification gates (per merge)

- Existing `ci.yml` and `pr-ci.yml` must pass green on each PR before merge.
- Chicago-style test-discipline verification: real `grep` sweep for
  `unittest.mock|Mock(|MagicMock|patch(|monkeypatch` across each branch's new
  test files, with zero matches (or named justified exceptions) — re-run this
  grep after merge against the merged `master` tree, not just pre-merge.
- Ruff formatting/lint check on the merged tree (`ruff check .` /
  `ruff format --check .`) to catch any interaction between the two branches'
  independently-formatted new files.
- For `adapt/aps-autofde-protocol` specifically: the new
  `aps-protocol-profile.yml` workflow must itself pass on its own introducing
  PR (self-qualification) before being trusted as a gate for later PRs.
- Full test suite (`pytest`) run once on `master` after both merges land, to
  catch any cross-branch interaction the disjoint-diff analysis in Measure
  could not surface (e.g. shared fixture-collection paths, `conftest.py`
  interactions).

### Rollout and monitoring

- No feature flags are evident in either diff — both are additive
  modules/ontology files with their own test coverage, so rollout is
  merge-and-monitor rather than staged/flagged.
- Post-merge monitoring: watch the next 2-3 scheduled runs of
  `continuous-planning-fortune5-crown.yml` and `fortune5-ggen.yml` (existing
  Fortune-5-flavored workflows) for any unexpected interaction with the new
  `fortune5_safe` simulation module, since both share the "Fortune-5" naming
  domain even though the new branch's diff does not directly wire into them.
- Post-merge monitoring for APS: watch the first several pull requests opened
  after `adapt/aps-autofde-protocol` merges to confirm the new
  `aps-protocol-profile.yml` gate does not produce false-positive failures on
  unrelated PRs (i.e., confirm its trigger/path-filter scope, if any, is
  correctly restricted to ontology/protocol-relevant changes, or is
  intentionally repo-wide).
- If either new CI gate proves too strict or too slow, the standing fix-forward
  policy applies: add a targeted follow-up commit narrowing the gate's scope or
  fixing the underlying issue — never revert via `git reset --hard` or drop the
  gate silently.
- This plan document itself should be revisited if a third branch appears with
  a commit timestamp inside the "last 24h" window relative to a later reading
  of this plan — the Measure section's branch list is a snapshot as of
  2026-09-01 and will go stale as new branches are pushed.

## Closure (2026-09-01)

Both branches merged, in the order this plan's Implement section recommended
(fortune5-sim first, aps-protocol second):

- `feat/fortune5-safe-dfcm-sim` → PR
  [#94](https://github.com/seanchatmangpt/autofde-lab/pull/94), merge `2bf2871f`. Its own
  Exact-head-qualification CI run initially failed on `ruff-check`/`ruff-format` pre-commit
  hooks (the branch's new files were never run through the repo-pinned ruff before this plan's
  own Develop section's "lint/format check" step was skipped) — fixed with a follow-up commit
  applying `uvx ruff@0.14.0` (the exact `.pre-commit-config.yaml`-pinned version), re-verified
  6/6 tests still pass, re-pushed, CI green on retry.
- `adapt/aps-autofde-protocol` → PR
  [#95](https://github.com/seanchatmangpt/autofde-lab/pull/95), merge `d2242c39`. All 4 checks
  passed on first run, including its own new self-qualifying `aps-protocol-profile.yml` gate.

Real, this-session evidence per branch (see `docs/STATUS.md` pass 21 for the full command
list): `pytest tests/simulation/test_fortune5_safe.py -v` → 6 passed;
`pytest tests/test_aps_protocol_profile_chicago.py -v` → 5 passed; independent
`pyshacl.validate()` of `ontology/aps-autofde-profile.ttl` against its shapes file →
**Conforms: True** (this goes beyond the test suite's own rdflib structural checks, which
this plan's Develop section had flagged as unconfirmed whether a real SHACL validator was
being exercised). Combined post-merge run on `master`:
`pytest tests/simulation/ tests/test_aps_protocol_profile_chicago.py
tests/agent/test_life_autonomic_case_study.py -v` → 14 passed, confirming the Measure
section's "no file overlap" prediction held under a real merge, not just a diff.

`README.md` and the repo documentation map were rewritten against this closed state in the
same pass — see `docs/STATUS.md` pass 21 and `README.md`'s own "What's new in v26.9.1"
section for the user-facing record.

## Last Updated: 2026-09-01
