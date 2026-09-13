# Repository Stub / WIP Audit — 2026-08-08

Status: `PARTIAL_ALIVE`

## Scope admitted

Requested outcome: audit each accessible `seanchatmangpt/*` repository for explicit stubs, WIP markers, incomplete implementation markers, and placeholder execution surfaces; create a pull request per repository with findings.

This document records the first admitted audit receipt for the repository fleet and the blocking conditions encountered while attempting per-repository PR publication from the GitHub connector.

## Search indicators

The audit indicator set is intentionally lexical and conservative:

- `TODO`
- `FIXME`
- `WIP`
- `stub`
- `incomplete`
- `placeholder`
- `NotImplementedError`
- Rust `todo!`, `unimplemented!`
- placeholder panics or comments that explicitly declare missing implementation

## Repositories observed in the accessible owner listing

The GitHub connector returned 99 repositories for owner `seanchatmangpt` in the first owner listing page, with no second page results. The listing included old tutorial/fork/demo repositories and active architecture repositories. Because many repositories report `is_code_search_indexed=false` or `null`, code search cannot be treated as complete evidence for the fleet.

## Initial concrete finding: `seanchatmangpt/ggen`

Observed base: `main` at `c37b46015b8e5ab40be771d61aafe3d7c7af084c`.

A GitHub code search for `TODO` returned explicit TODO-bearing paths including:

| Path | Classification | Closure recommendation |
| --- | --- | --- |
| `docs/MASTER_TODO.md` | `PARTIAL_ALIVE` / declared open work ledger | Convert each surviving item into a typed issue or remove if obsolete. |
| `examples/archive/factory-paas/TODO_ROUTING.md` | `PARTIAL_ALIVE` / archived routing TODO | Preserve as archive only if intentionally historical; otherwise close or migrate. |
| `docs/FAKE_DETECTION_STRATEGY.md` | `PARTIAL_ALIVE` / fake-detection audit surface | Re-run against current repo state and convert strategy into executable verifier fixtures. |
| `scripts/find-fakes.sh` | `PARTIAL_ALIVE` / audit script surface | Verify this script still executes and emits machine-readable findings. |

False-positive note: several `todo-app` example/tutorial paths are examples, not incomplete work by themselves.

## Initial concrete finding: `seanchatmangpt/gymact`

Observed recursive tree endpoint was reachable for `main`; repository search-index status was unavailable/false via repository search metadata. Tree inspection alone proves path existence, not file content. No content-level assertion is made here without fetching and scanning blobs.

## Fleet-level finding

`BLOCKED`: Full per-repository PR publication was not completed in this run. Causes:

1. The GitHub connector owner listing exposed many repositories with code search unavailable or unknown.
2. A broad multi-repository code search for WIP/stub markers returned upstream 502 errors.
3. Private and unindexed repositories require blob-by-blob traversal rather than GitHub code search; that is higher-cost and must be routed through repository tree/object fetches.
4. This PR is therefore a control-plane audit receipt, not a complete per-repository closure.

## Required next closure action

For each repository:

1. Resolve default branch to exact SHA.
2. Fetch recursive tree.
3. Scan only source/docs/config text blobs under a bounded size threshold.
4. Exclude vendored, archived, generated, dependency, fixture, and tutorial false positives unless they are active execution surfaces.
5. Write `docs/audits/<date>-stubs-wip-audit.md` in that repository.
6. Open a draft PR from an `audit/stubs-wip-findings-<date>` branch.

## Standing

- Observed: repository listing; `ggen` TODO search result; `gymact` recursive tree availability.
- Executed: one audit branch and one audit document in `seanchatmangpt/autofde-lab`.
- Changed: documentation only.
- Verified: GitHub connector accepted branch creation and file creation.
- Not verified: full fleet scan; per-repository PR publication; local execution; CI.
