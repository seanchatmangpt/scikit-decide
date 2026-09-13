# Standing law — the vocabulary every claim must carry

Every claim about this repo's state gets one of these, **scoped per
boundary** — a change is rarely one status end to end:

- `ALIVE` — the declared consequence works and the required evidence (a
  command actually run this session, output observed) is present.
- `PARTIAL_ALIVE` — a bounded working checkpoint exists but the larger claim
  does not follow from it yet.
- `BLOCKED:<reason>` — a named external prerequisite prevents lawful
  progress (e.g. `BLOCKED:UPSTREAM_ACTIONS_OUTAGE`). Name the exact blocker,
  not "blocked."
- `BUILD_BROKEN` — the relevant build or test suite fails.
- `UNKNOWN` — observation is insufficient to classify standing. Not the same
  as `UNSUPPORTED`.
- `UNSUPPORTED` — the required capability or dependency is absent
  (environment gate, missing optional extra), not incomplete work.

A solver/domain claim is `ALIVE` only with a Chicago-style test exercising
`solve()` on a real domain, run this session — never "compiles" or "the
happy path works." Queued CI, a merged PR, or a green synthetic check are not
evidence; only an executed job against the exact commit is. See
`docs/STATUS.md` for the working ledger convention this maps to: **measured
win** (command run, output quoted, passed), **recorded negative** (attempted,
genuinely blocked, blocker named precisely), **deferred/scoped** (a plan
exists, nothing under it executed yet — treat every line as unverified until
it appears in a ledger with a witness).

## Three standing dimensions

The vocabulary above answers *what state*. It does not answer *whose standing*. Split every
claim across three dimensions, each carrying its own status from the list above:

- `technicalStanding` — may become `ALIVE` on a manufactured **and independently verified**
  artifact.
- `organizationalStanding` — remains `UNKNOWN` or `BLOCKED:<reason>` without accountable
  customer acceptance. Deployment, file creation, and receipt verification do not move it.
- `enterpriseStanding` — becomes `ALIVE` **only** when both of the above are admitted.

A green technical row never implies enterprise standing. This is the same class of error as a
green in-repo row implying a closed cross-repo consequence — the distinction `docs/STATUS.md`
already draws between a measured win and a closed chain, one dimension further out.

**Stated honestly: as of this session no component computes `organizationalStanding`.** This is
a vocabulary introduced ahead of its evidence, so that claims made while the FDE rail is built
are not silently over-read. Every existing standing claim in this repo and in both ledgers is a
`technicalStanding` claim. Do not re-read any of them as enterprise standing.

See `.claude/rules/fde-authority-boundary.md` for who may issue what.

### Former standing exception — resolved 2026-08-07

`uv run pytest tests --collect-only -q` previously failed collection outright
(`BUILD_BROKEN` by this section's own vocabulary), for reasons recorded here
across 2026-08-06 and earlier:

- `tests/solvers/python/test_pomcp.py` collided on basename with
  `tests/solvers/cpp/test_pomcp.py` (no package markers to disambiguate).
- `tests/test_self_play_dspy_advanced_planning_chicago.py`,
  `_all_domains_chicago.py`, `_turbofieldfare_chicago.py` — all three failed
  to import, via a *different* mechanism than first assumed: a bare-`conftest`
  module-name collision between `tests/conftest.py` and
  `tests/solvers/python/{openevolve,autoregressive}/conftest.py` (both lacked
  `__init__.py`, so pytest's prepend import mode gave them the same bare
  module name `conftest`, and whichever collected first shadowed the other).

**Fixed 2026-08-07, then corrected same day** (`docs/STATUS.md` Pass 6 has the
full account — read that, not this summary, if the mechanism matters): the
first fix added `__init__.py` to `tests/solvers/`, `tests/solvers/cpp/`,
`tests/solvers/python/`, `tests/solvers/python/openevolve/`, and
`tests/solvers/python/autoregressive/`, which disambiguated both collisions
but broke two other things the same session — real `ray.rllib` actor workers
unpickling test-defined classes by their now-dotted module name, and
`tests/solvers/python/openevolve/__init__.py` shadowing the real installed
`openevolve` PyPI package. **All five `__init__.py` files were removed.**
The actual, current fix is `--import-mode=importlib` (no `sys.path`
insertion, so no shadowing is possible by construction) — passed explicitly,
**not** a global `pyproject.toml` default, because it's measurably slower
than the default "prepend" mode (~2.2x, confirmed live on `just test`) and
neither `Justfile` target ever needs it: `just test`'s `--ignore`s already
exclude every file involved in either collision, and `just test-full` runs
each partition in its own pytest process, which never combines the
colliding files in one collection pass either. It's only needed for a
combined `pytest tests` invocation — e.g. this section's own verification
command, `.venv/bin/python -m pytest tests --collect-only -q
--import-mode=importlib`, re-verified this session: zero collection errors,
whole-suite collection is `ALIVE`. An exported `PYTHONPATH` in the
`Justfile` fixes a separate, unrelated issue: Ray's spawned worker
processes need it explicitly, since they don't inherit pytest's in-process
`sys.path` mutation.

Separately, joblib and pyarrow were missing from the venv entirely (not
corrupt — absent), causing `tests/domains` and `tests/scheduling` collection
errors; fixed by installing both, then a full `uv sync --extra=all` to also
land `torch`, `stable-baselines3`, `torch-geometric`, `openap`, `pygeodesy`,
`fsspec`, and the rest of the `domains`/`solvers` extras that were likewise
absent (not a stale-lock or corruption issue — the venv had simply never been
synced with `--extra=all` in this checkout). Don't claim green collection
without re-running the command above — this entry documents what was true as
of 2026-08-07, not a permanent guarantee.

## See also

- `CLAUDE.md` — the index; this file is `@`-imported there because every
  session needs it.
- `docs/STATUS.md` — the in-repo ledger applying this vocabulary.
- `docs/ecosystem-standing.md` — the cross-repo ledger applying it wider.
- `.claude/rules/fde-authority-boundary.md` — who may issue which kind of grant, and why
  organizational standing cannot be self-certified.
