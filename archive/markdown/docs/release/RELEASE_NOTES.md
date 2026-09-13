# RELEASE NOTES

Milestone: **Persistent Agent Laboratory**.
Commit range: `1ef12de..e32e870` (13 commits). Head: `e32e8705659d420432986f8919c23786cfd90438`,
dated 2026-08-06.

This document records what changed and what did not. Nothing here has been tagged, built,
packaged, or published; this is documentation of a commit range, not of a release artifact.

## The release version is unresolved

There is no version number for this milestone, and inventing one would be a false claim.

- `pyproject.toml:28` declares `dynamic = ["version"]`. The version is derived at build time
  from git history, not written down anywhere in the tree.
- This repository has **zero git tags**. `git describe --tags --long` returns
  `fatal: No names found, cannot describe anything.`
- The version a build would currently derive is `0.1.dev768+gd81479000` — a development
  identifier, not a release identifier.
- The string `26.8.6` has been seen in circulation for this milestone. It belongs to a
  different project (`ggen`) and does not describe this repository. It is not used here.

Until a tag exists and a distribution name is settled (see the blocking prerequisite below),
the milestone is referred to by name and by commit range only.

## Blocking release prerequisite: distribution name collides with Airbus's package — RESOLVED

This repository is a fork. At the time this note was first filed, `origin` was
`https://github.com/seanchatmangpt/scikit-decide` while `pyproject.toml` still declared:

```toml
name = "scikit-decide"
# [project.urls]
repository = "https://github.com/airbus/scikit-decide"
```

`scikit-decide` is Airbus's published PyPI distribution; building or uploading an artifact from
this tree under that name would have placed fork content behind an upstream project's identity.

The AutoFDE Lab rename (`docs/migration/AUTOFDE_LAB_RENAME.md`) resolved this: `pyproject.toml`
now declares `name = "autofde-lab"` and `repository = "https://github.com/seanchatmangpt/autofde-lab"`.

Standing: was `BLOCKED:FORK_DISTRIBUTION_NAME_COLLIDES_WITH_UPSTREAM_PYPI`, now resolved. Entry
kept rather than deleted, per this repo's ledger discipline.

This is a prerequisite, not a cosmetic cleanup. A distinct distribution name — and matching
project URLs — is required before any artifact leaves this tree by any channel. No packaging
step should be attempted until it is resolved.

## The release gate

The gate for this milestone is not a pytest item count. Item counts fall when falsifiers are
deleted, so a count target rewards the failure it is supposed to detect. The gate is:

1. All distinct falsifiers preserved.
2. All collapsed redraws mutation-proven.
3. All aggregate tests anti-vacuous.
4. Admitted suite green.
5. Clean checkout green.
6. Acceptable wall-clock.

None of these six is currently recorded as met end to end; test compression (below) is still in
progress, and clean-checkout green has not been run for this commit.

## What shipped in `1ef12de..e32e870`

Read from the commit log, not from a plan.

### AutoFDE surfaces (EXPLORE — see [../autofde/EXPLORE.md](../autofde/EXPLORE.md))

- `db34caf` — defined the explore boundary and the operating model as documents.
- `8804504` — admitted phase graph, GitHub projection, independent reconstruction
  (`src/autofde_lab/autofde/phase_graph.py`, `github_projection.py`, `reconstruct.py`).
- `27863af` — declarative GitHub project management generated from the graph
  (`infra/github/`).
- `297f042` — refusal-first ephemeral Azure incident-response demo environment
  (`infra/azure/`).
- `99ddc50` — the round-trip law, every falsifier, and the extraction boundary, under
  `tests/autofde/`.

Every one of these surfaces is EXPLORE. Per `docs/autofde/EXPLORE.md`, no standing row produced
under an AutoFDE surface in this repository transfers to the AutoFDE product.

### Adapters and ledger

- `dc7324d` — Azure adapter expanded into a per-surface subpackage of typed refusals.
- `39bb569` — ledger-to-OCEL sink, with refusals instead of repairs.
- `5292a9d` — the two ledgers reconciled; thread objects, activity label, and time.
- `ff9bda3` — submodules exposed lazily; drift control widened, then the ontology.

### Test compression (in progress)

- `0e09151`, `dfc3c8f`, `60d8767`, `e32e870` — ERRC compression passes over
  `tests/powl`, `tests/ocel`, `tests/agent`, `tests/adapters`, `tests/autofde`.

Compression is **in progress**. No final suite count is reported here, because one does not
exist yet. One measured suite pair went 176 → 73 items:

| File | Before | After |
|---|---:|---:|
| `tests/autofde/test_explore_boundary.py` | 45 | 5 |
| `tests/autofde/test_terraform_guards.py` | 32 | 10 |
| `tests/adapters/test_azure_adapters.py` | 38 | 18 |
| `tests/adapters/test_adapters.py` | 28 | 9 |
| `tests/autofde/test_work_graph_projection.py` | 33 | 31 |

## What did NOT ship

Given equal prominence deliberately. These are absent, not partial.

- **Fault matrix** — `NOT_RUN`. Being built in a separate effort. At `e32e870`,
  `tests/autofde/` contains exactly `test_explore_boundary.py`, `test_terraform_guards.py`,
  `test_work_graph_projection.py`. A repository-wide search for `fault_matrix` / `fault matrix`
  returns zero hits.
- **Self-manufacturing loop** (`CAPABILITY_ABSENT` → generate work → manufacture → admit →
  resume) — `NOT_RUN`. No part of it exists. A repository-wide search for `CAPABILITY_ABSENT`
  and for `self-manufactur`/`self_manufactur` returns zero hits in `src/`, `tests/`, `docs/`,
  and `infra/`.
- **Real Azure apply** — `NOT_RUN`, two independent blockers:
  `BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION` and `BLOCKED:AZURE_CLI_ABSENT` (`az` is not
  installed). Either one alone is sufficient to prevent it.
- **Whole-suite collection** — `BUILD_BROKEN`, 4 known errors. See
  [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
- **Any packaged or published artifact** — none exists, and none may be produced while the
  distribution-name prerequisite above is open.

What the Terraform work covers is **Azure deployment contracts and mocked infrastructure
validation**. It is not evidence about any live Azure environment.

## Verified results cited by this document

| Check | Result |
|---|---|
| Integrated run (pre-compression baseline) | 675 passed, 4 skipped, 0 failed, exit 0 |
| `terraform fmt -check -recursive` | exit 0 |
| `terraform validate` | `Success! The configuration is valid.` |
| `terraform test` (mocked providers) | 24 passed, 0 failed |
| Refusal guards | observed printing `pass` individually |

The integrated run covered `tests/{powl,agent,ocel,adapters,ecosystem,fabric,autofde}` plus
`tests/domains/python/test_breach_clock_unit.py`. It is the **pre-compression** baseline; it
does not describe the suite as it stands after the compression commits above.

## Standing dimensions

Every standing row in this release set is a **technical** claim. No component in this
repository computes `organizationalStanding`; it therefore remains `UNKNOWN` throughout, and
`enterpriseStanding`, which requires both, is `UNKNOWN` as a consequence. Do not re-read any
green row here as organizational or enterprise standing.

## See also

- [STANDING_MATRIX.md](STANDING_MATRIX.md) — per-boundary standing for this commit.
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) — failures, blockers, and unproven controls.
- [release-manifest.json](release-manifest.json) — the machine-readable form of this set.
- [../autofde/EXPLORE.md](../autofde/EXPLORE.md) — the explore boundary binding every AutoFDE
  surface named above.
- [../STATUS.md](../STATUS.md) — the in-repo WIP ledger.
- [../ecosystem-standing.md](../ecosystem-standing.md) — cross-repository standing.
- `.claude/rules/standing-law.md` — the standing vocabulary used throughout.
