# KNOWN LIMITATIONS

Limitations of the **Persistent Agent Laboratory** milestone at commit
`e32e8705659d420432986f8919c23786cfd90438`, dated 2026-08-06.

Each entry names what is wrong, what was actually observed, and — where it matters — what was
*not* established. Statuses use `.claude/rules/standing-law.md` vocabulary. Every entry is a
technical claim; `organizationalStanding` is `UNKNOWN` throughout (see
[STANDING_MATRIX.md](STANDING_MATRIX.md)).

## 1. Whole-suite pytest collection is BUILD_BROKEN

`BUILD_BROKEN` — 4 known collection errors. Run new suites by path; do not rely on whole-suite
collection.

- `tests/solvers/python/test_pomcp.py` collides on basename with
  `tests/solvers/cpp/test_pomcp.py`; there are no package markers to disambiguate them.
- `tests/test_self_play_dspy_advanced_planning_chicago.py` fails to import.
- `tests/test_self_play_dspy_all_domains_chicago.py` fails to import.
- `tests/test_self_play_dspy_turbofieldfare_chicago.py` fails to import.

The three import failures are in the Chicago-test files referenced by `docs/STATUS.md`'s
"close WIP with Chicago-style tests" pass. Surfaced here so that pass is not read as
"Chicago-test infrastructure is healthy across the board."

## 2. Four failing params in `test_plado_domain.py` — attribution is open

`tests/domains/python/test_plado_domain.py` has 4 failing parameters matching `*_sb3[*-llg]`:

```text
RuntimeError: scatter(): Expected self.dtype to be equal to src.dtype
  at hub/solver/stable_baselines/autoregressive/common/distributions.py:135
```

Two separate statements, and the distinction is load-bearing:

- **Not attributable to this milestone.** No commit in `1ef12de..e32e870` touches
  `src/autofde_lab/hub/`, and no module changed in that range appears anywhere in the traceback.
  This is a positive finding from the commit range and the traceback.
- **Not proven pre-existing.** `UNKNOWN`. Establishing that the failure predates `1ef12de`
  requires building and running the control at that commit in its own environment, which was
  not done. Absence of a plausible cause in the range is evidence against attribution; it is
  not a demonstration that the failure existed before.

The correct reading is: this milestone has no identified causal connection to the failure, and
the pre-existence hypothesis is untested. Do not record it as "pre-existing" until the control
build has been run.

## 3. Real Azure apply was never run — two independent blockers

`NOT_RUN`. Both of the following hold, and either alone is sufficient:

- `BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION`
- `BLOCKED:AZURE_CLI_ABSENT` — `az` is not installed in this environment.

What *was* exercised is Azure deployment contracts and mocked infrastructure validation:
`terraform fmt -check -recursive` exit 0, `terraform validate` returning
`Success! The configuration is valid.`, and `terraform test` at 24 passed / 0 failed with
mocked providers, with refusal guards observed printing `pass` individually. None of that is
evidence about any live Azure environment, subscription, tenant, or resource.

## 4. Fault matrix is absent

`NOT_RUN`. At this commit `tests/autofde/` contains exactly `test_explore_boundary.py`,
`test_terraform_guards.py`, and `test_work_graph_projection.py`. A search of `src/`, `tests/`,
`docs/`, and `infra/` for `fault_matrix` and `fault matrix` returns zero hits. Work on it is
proceeding in a separate effort; that is a plan, not a standing. It is not `PARTIAL_ALIVE`,
because there is no bounded working checkpoint for the partial status to describe.

## 5. Self-manufacturing loop is absent

`NOT_RUN`. The chain `CAPABILITY_ABSENT` → generate work → manufacture → admit → resume has no
implemented stage. A search of `src/`, `tests/`, `docs/`, and `infra/` for `CAPABILITY_ABSENT`
and for `self-manufactur` / `self_manufactur` returns zero hits.

## 6. Test compression is incomplete, and the baseline is stale

`PARTIAL_ALIVE`. The 675 passed / 4 skipped / 0 failed / exit 0 integrated result is the
**pre-compression** baseline across
`tests/{powl,agent,ocel,adapters,ecosystem,fabric,autofde}` plus
`tests/domains/python/test_breach_clock_unit.py`. Four compression commits landed after
measurements began (`0e09151`, `dfc3c8f`, `60d8767`, `e32e870`), so the baseline does not
describe the suite as it now stands. No post-compression suite count is reported here, and any
figure presented as one should be treated as unsubstantiated.

The compression gate — falsifiers preserved, collapsed redraws mutation-proven, aggregate tests
anti-vacuous — is not recorded as met. Item-count reduction alone does not satisfy it, since
deleting a falsifier also reduces the count.

## 7. No release version, and packaging is blocked

- The release version is `UNKNOWN`. `pyproject.toml:28` declares `dynamic = ["version"]`, the
  repository has zero git tags, and a build would currently derive `0.1.dev768+gd81479000`.
  The string `26.8.6` belongs to a different project (`ggen`) and does not apply here.
- `BLOCKED:FORK_DISTRIBUTION_NAME_COLLIDES_WITH_UPSTREAM_PYPI` — **resolved** as of the
  AutoFDE Lab rename (`docs/migration/AUTOFDE_LAB_RENAME.md`). `pyproject.toml` now declares
  `name = "autofde-lab"` and `repository = "https://github.com/seanchatmangpt/autofde-lab"`;
  it no longer collides with Airbus's `scikit-decide` PyPI distribution. Left in place, marked
  resolved rather than deleted, per this repo's ledger discipline of correcting entries in
  place instead of silently rewriting history.

## 8. Clean-checkout green has not been run

`NOT_RUN` for this commit. One of the six release-gate conditions in
[RELEASE_NOTES.md](RELEASE_NOTES.md) is therefore unmet by observation rather than by failure.

## 9. Every AutoFDE surface is EXPLORE

`src/autofde_lab/autofde/`, `infra/azure/`, `infra/github/`, `docs/autofde/`, `tests/autofde/`,
and `demo/` are explore surfaces. Per [../autofde/EXPLORE.md](../autofde/EXPLORE.md), no
standing row produced under them transfers to the AutoFDE product, which ships from a different
repository and must re-establish its own evidence there.

## See also

- [RELEASE_NOTES.md](RELEASE_NOTES.md) — milestone contents and the release gate.
- [STANDING_MATRIX.md](STANDING_MATRIX.md) — per-boundary standing.
- [release-manifest.json](release-manifest.json) — machine-readable standing.
- [../autofde/EXPLORE.md](../autofde/EXPLORE.md) — the explore boundary.
- [../STATUS.md](../STATUS.md) — the in-repo WIP ledger and its row conventions.
- `.claude/rules/standing-law.md` — standing vocabulary and the three dimensions.
