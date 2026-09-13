# STANDING MATRIX

Per-boundary standing for the **Persistent Agent Laboratory** milestone at commit
`e32e8705659d420432986f8919c23786cfd90438` (range `1ef12de..e32e870`), dated 2026-08-06.

Vocabulary is `.claude/rules/standing-law.md`: `ALIVE`, `PARTIAL_ALIVE`, `BLOCKED:<reason>`,
`BUILD_BROKEN`, `UNKNOWN`, `UNSUPPORTED`, plus `NOT_RUN` for a boundary that was never
exercised.

## Read this before reading the table

**Every row below is a `technicalStanding` claim.** No component in this repository computes
`organizationalStanding` — there is no accountable customer acceptance recorded anywhere in the
tree — so `organizationalStanding` is `UNKNOWN` for every row without exception, and
`enterpriseStanding`, which requires both dimensions admitted, is `UNKNOWN` for every row as a
consequence. The three dimensions are not collapsed and a green technical row never implies the
other two.

## Technical standing by boundary

| Boundary | Standing | Witness or blocker |
|---|---|---|
| Integrated suite, pre-compression | `ALIVE` | 675 passed, 4 skipped, 0 failed, exit 0 |
| Integrated suite, post-compression | `UNKNOWN` | Compression in progress; not re-run whole |
| Whole-suite pytest collection | `BUILD_BROKEN` | 4 collection errors, see KNOWN_LIMITATIONS |
| Terraform formatting | `ALIVE` | `fmt -check -recursive` exit 0 |
| Terraform configuration validity | `ALIVE` | `Success! The configuration is valid.` |
| Terraform contract tests (mocked) | `ALIVE` | `terraform test` 24 passed, 0 failed |
| Terraform refusal guards | `ALIVE` | observed printing `pass` individually |
| Real Azure apply | `NOT_RUN` | `BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION` |
| Real Azure apply (second, independent) | `NOT_RUN` | `BLOCKED:AZURE_CLI_ABSENT` (`az` absent) |
| Test compression pass | `PARTIAL_ALIVE` | One suite pair 176 → 73; others outstanding |
| `tests/domains/python/test_plado_domain.py` | `BUILD_BROKEN` | 4 `*_sb3[*-llg]` params fail |
| Fault matrix | `NOT_RUN` | Absent at this commit; zero occurrences in tree |
| Self-manufacturing loop | `NOT_RUN` | No part exists; zero occurrences in tree |
| Distribution name / packaging | see note below | `name = "scikit-decide"` in `pyproject.toml` |
| Release version identifier | `UNKNOWN` | `dynamic = ["version"]`, zero git tags |
| Clean-checkout green | `NOT_RUN` | Not exercised for this commit |
| Any published artifact | `NOT_RUN` | Nothing tagged, built, packaged, or published |

Note on the packaging row: its full standing string is
`BLOCKED:FORK_DISTRIBUTION_NAME_COLLIDES_WITH_UPSTREAM_PYPI`. `scikit-decide` is Airbus's
published PyPI distribution and this repository is a fork; a distinct distribution name is a
prerequisite for any outward artifact.

## Two rows that a circulating draft got wrong

A draft standing table for this release listed the fault matrix and the self-manufacturing loop
as `PARTIAL_ALIVE`. Both are recorded above as `NOT_RUN`, and the correction is kept visible
rather than edited away.

- **Fault matrix.** `PARTIAL_ALIVE` asserts a bounded working checkpoint exists. At `e32e870`,
  `tests/autofde/` contains exactly three files — `test_explore_boundary.py`,
  `test_terraform_guards.py`, `test_work_graph_projection.py` — and a search of `src/`,
  `tests/`, `docs/`, and `infra/` for `fault_matrix` and `fault matrix` returns zero hits.
  There is no checkpoint to be partial about. It is being built in a separate effort, which is
  a statement about the future, not a standing.
- **Self-manufacturing loop.** The chain `CAPABILITY_ABSENT` → generate work → manufacture →
  admit → resume has no implemented stage. A search for `CAPABILITY_ABSENT` and for
  `self-manufactur`/`self_manufactur` across `src/`, `tests/`, `docs/`, and `infra/` returns
  zero hits. `PARTIAL_ALIVE` on an absent capability is the specific error the standing law
  exists to prevent.

`NOT_RUN` is the honest status for both: the boundary was never exercised because there is
nothing to exercise.

## Explore versus exploit

`src/autofde_lab/autofde/`, `infra/azure/`, `infra/github/`, `docs/autofde/`, `tests/autofde/`,
and `demo/` are EXPLORE surfaces. Per [../autofde/EXPLORE.md](../autofde/EXPLORE.md), no
standing row produced under them transfers to the AutoFDE product — including the green
Terraform rows above, which describe **Azure deployment contracts and mocked infrastructure
validation** in this laboratory and nothing beyond it.

## See also

- [RELEASE_NOTES.md](RELEASE_NOTES.md) — what shipped, what did not, and the release gate.
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) — the failures behind the red rows.
- [release-manifest.json](release-manifest.json) — this matrix in machine-readable form.
- [../autofde/EXPLORE.md](../autofde/EXPLORE.md) — the explore boundary.
- `.claude/rules/standing-law.md` — the vocabulary and the three standing dimensions.
