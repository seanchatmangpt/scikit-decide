# GymAct Kernel Deduplication — 2026-08-08

Context: autofde-lab's internal `src/autofde_lab/gymact/` (~420 lines, `GymActKernel`) was an
independently-built duplicate of the real, standalone `gymact` package. This refactor replaces it
with real delegation, closing the drift risk PR #26/GYMACT_HANDOFF.md named ("AutoFDE should
become a client of GymAct rather than the owner of benchmark-specific lifecycle semantics").

## What changed

## Summary

Replaced the internal `src/autofde_lab/gymact/` duplicate with a real thin wrapper over the real
`gymact` package (`/Users/sac/gymact`). All 16 pre-existing tests pass unchanged — no test file
was modified.

**Note:** a concurrent session touched the same `pyproject.toml` while I worked (adding `gymact`
as a base `[project.dependencies]` entry for an unrelated `azuregoat_privesc.gymact_bridge`
integration, plus a `[project.entry-points."gymact.providers"]` block). I detected a resulting
duplicate `[tool.uv.sources]` `gymact` key mid-edit and resolved it by removing my redundant
`"gymact"` line from the `gymact` extra (since it's now already a base dependency) rather than
reverting their change.

### 1. `pyproject.toml`

Added `[tool.uv.sources]` entry: `gymact = { path = "/Users/sac/gymact", editable = true }`
(matches the `wasm4pm-compat-py` path-dependency precedent). `gymact` itself is now pulled in
via the concurrent session's base-dependency addition; I adjusted the `gymact` extra's comment
to point at that instead of duplicating it. Installed with
`uv pip install -e /Users/sac/gymact --python .venv/bin/python` (plain `uv sync`/`uv run` are
broken repo-wide by a pre-existing, unrelated missing sibling path
`/Users/sac/wasm4pm-compat/wasm4pm-compat-py` under the `receipts` extra, and
`.venv/bin/pytest`'s console-script shebang is stale, pointing at
`/Users/sac/scikit-decide/.venv/bin/python` — both out of scope). Confirmed `import gymact`
(`26.8.7`) and a full real materialize→act→verify→checkpoint→restore→teardown round-trip
against `gymact.runtime.GymAct` + `MemoryProvider`.

### 2. `src/autofde_lab/gymact/kernel.py` (full rewrite, 111 → ~350 lines)

`GymActKernel` now holds a real `gymact.runtime.GymAct` instance with a real
`gymact.providers.MemoryProvider` registered. The 8 operations gymact's `Operation` enum covers
(`discover/materialize/observe/act/verify/checkpoint/restore/teardown`) build real
`gymact.models` request objects and drive them through the real runtime (via a sync/async
bridge, `_run_async`, since the real runtime is `async def` but this kernel's public methods
stay synchronous to match the existing CLI/test contract). A local
`episode_id -> real gymact episode_id` map bridges the fact that the real runtime mints its own
episode ids while this kernel's callers supply their own. `configure/reset/start/score` (not in
`gymact.models.Operation` — that enum was deliberately reduced from 12 to 8, per its own
docstring) stay real local pass-throughs: they still append a real `KernelEvent` and return a
real `ActuationResult`, with `receipt=None` since no real `gymact.models.Receipt` exists for
them. Every operation, real or local, still logs to the local `EventLog` so
`process.ConformanceChecker`'s 12-activity replay is unaffected.

### 3. `src/autofde_lab/gymact/models.py`

Re-exports `gymact.models.Standing` directly (its extra members are a superset; `StrEnum`
compares equal to plain strings, so existing `== "ALIVE"` assertions still pass) and uses it as
`ActuationResult.standing`'s type. `ActuationIntent`, `Observation`, `ActuationResult`, and
`KernelEvent` stay local — each docstring now states exactly which real `gymact.models` fields
don't match (e.g. real `ActuationIntent` requires `capability` and fixes
`operation: Literal[Operation.ACT]`, has no `subject`; real `Observation` has
`state`/`state_digest`, no `subject`; real `ActuationResult.receipt` is a required full
`Receipt` object, not an optional id string).

### 4. `src/autofde_lab/gymact/eventlog.py`

No logic change — docstring extended to explicitly state why it isn't replaced by
`gymact.ocel.receipts_to_ocel`/`GymAct.episode_ocel_log` (those operate only over the real 8-op
`Receipt` trail, not the local 12-activity lifecycle), and kernel.py adds a
`real_ocel_log(episode_id)` passthrough for the covered subset.

### 5. `api.py`, `cli.py`, `mcp.py`

**Unchanged.** Their calls (`GymActKernel()`, `kernel.discover(...)`,
`kernel.act(subject=..., episode_id=..., payload=...)`, `OPERATIONS`, local
`ActuationIntent`/`ActuationResult`) all still typecheck and behave against the refactored
kernel with no edits needed.

### Verification

```
uv run --no-sync python -m pytest src/autofde_lab/gymact/tests/ -v
============================= test session starts ==============================
collected 16 items
src/autofde_lab/gymact/tests/test_api.py ...                             [ 18%]
src/autofde_lab/gymact/tests/test_cli.py ..                              [ 31%]
src/autofde_lab/gymact/tests/test_mcp.py ..                              [ 43%]
src/autofde_lab/gymact/tests/test_models.py ....                         [ 68%]
src/autofde_lab/gymact/tests/test_process_conformance.py ..              [ 81%]
src/autofde_lab/gymact/tests/test_profile_shacl.py ...                   [100%]
============================== 16 passed in 1.17s ==============================
```

No test assertion was loosened or deleted; no test file was touched.

## Independent re-verification

Those are dirty submodule pointer states (0 insertions/deletions, just commit-ref drift),
unrelated to this refactor — not part of the claimed diff footprint, and not something the
refactor report claimed either way.

### Independent re-verification results

**1. `src/autofde_lab/gymact/tests/` pass/fail count**

`uv run pytest ...` and `uv run --no-sync pytest ...` both **fail at collection** with
`AttributeError: module 'wrapt' has no attribute 'lru_cache'` — because `uv run pytest` resolves
to the `.venv/bin/pytest` console script, whose shebang points at
`/Users/sac/scikit-decide/.venv/bin/python` (a different, incompatible venv) — this is the exact
stale-shebang issue the refactor report flagged as a pre-existing, out-of-scope problem, and it
reproduces exactly as described.

Invoking the correct interpreter directly
(`.venv/bin/python -m pytest src/autofde_lab/gymact/tests/ -v`):

```
collected 16 items

src/autofde_lab/gymact/tests/test_api.py ...                             [ 18%]
src/autofde_lab/gymact/tests/test_cli.py ..                              [ 31%]
src/autofde_lab/gymact/tests/test_mcp.py ..                              [ 43%]
src/autofde_lab/gymact/tests/test_models.py ....                         [ 68%]
src/autofde_lab/gymact/tests/test_process_conformance.py ..              [ 81%]
src/autofde_lab/gymact/tests/test_profile_shacl.py ...                   [100%]

============================== 16 passed in 1.13s ==============================
```

16/16 pass — confirmed, real, current. But the report's own repro command
(`uv run --no-sync python -m pytest ...`) as literally written does not work via bare
`uv run pytest`; only `python -m pytest` invoked on the correct interpreter does.

**2. Real `gymact` usage, not stubbed**

Confirmed genuine:

```
_RealGymAct -> gymact.runtime <class 'gymact.runtime.GymAct'>
MemoryProvider -> gymact.providers <class 'gymact.providers.MemoryProvider'>
gymact package file: /Users/sac/gymact/src/gymact/__init__.py
gymact version: 26.8.7
```

`GymActKernel.__init__` source:

```python
def __init__(self, *, provider: EnvironmentProvider | None = None) -> None:
    self._runtime = _RealGymAct()
    self._provider = provider or MemoryProvider()
    self._runtime.register_provider(self._provider)
    ...
```

Both classes resolve (`__module__`) to the real standalone `gymact` package rooted at
`/Users/sac/gymact`, not a local shim or mock.

**3. `git status --porcelain` / `git diff --stat`**

```
 M pyproject.toml
 M src/autofde_lab/gymact/eventlog.py
 M src/autofde_lab/gymact/kernel.py
 M src/autofde_lab/gymact/models.py
 M vendor/gyms/devops-gym
 M vendor/gyms/enterprisebench
?? TEMP_RLlib/  docs/2026-08-07-*.md  openevolve_output/  optuna-journal.log  rddl_movies/  reports/
?? scripts/run_azuregoat_gymact_ocel_episode.py
?? src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py
?? tests/solvers/python/openevolve/.../openevolve_output/

 pyproject.toml                     |  19 ++
 src/autofde_lab/gymact/eventlog.py |  14 ++
 src/autofde_lab/gymact/kernel.py   | 349 ++++++++++++++++++++++++++++++++-----
 src/autofde_lab/gymact/models.py   | 102 +++++++++--
 vendor/gyms/devops-gym             |   0
 vendor/gyms/enterprisebench        |   0
 6 files changed, 424 insertions(+), 60 deletions(-)
```

Matches the claimed footprint (kernel.py/models.py/eventlog.py/pyproject.toml) plus two
unrelated dirty submodule-pointer entries (0 insertions/deletions — commit-ref drift, not code)
and a pile of untracked files/dirs from other concurrent work (the azuregoat bridge, docs,
scratch dirs) that the report didn't claim and isn't responsible for.

**4. Full-suite collection**

`.venv/bin/python -m pytest --collect-only -q`: exit code 0, zero `ERROR` lines, 142
test-module lines listed, clean warnings-only tail. `testpaths = ["tests"]` in `pyproject.toml`
means `src/autofde_lab/gymact/tests/` is intentionally outside the default collection root, so
its absence from this listing is expected, not a regression. No new collection errors
introduced outside `src/autofde_lab/gymact/`.

**Bottom line:** all four of the refactor agent's substantive claims hold up under independent
re-check — real gymact package genuinely wired in, 16/16 tests pass, diff footprint matches,
full-suite collection stays clean. The one imprecision: the report's literal repro command
(`uv run --no-sync python -m pytest ...`) does not reproduce as typed via bare `uv run pytest`
because of the pre-existing stale-shebang issue; only direct
`.venv/bin/python -m pytest` invocation (or `uv run --no-sync python -m pytest`, which the
report did use correctly) gets you the passing run.

## Falsifiers

What would invalidate this report:

- The refactored `kernel.py` silently swallowing an exception raised by the real `gymact`
  runtime (e.g. a broad `except Exception: pass` around `_run_async`) and reporting fake
  success instead of propagating or typing the failure — not observed in the reviewed source,
  but not exhaustively traced through every code path either.
- A test in `src/autofde_lab/gymact/tests/` that was loosened (an assertion narrowed, a
  `pytest.raises` removed, a fixture swapped to bypass the real runtime) rather than genuinely
  passing against the real delegation — the diff stat shows zero test files touched, which is
  evidence against this but does not itself prove no test was already weak before the refactor.
- A caller of `GymActKernel`, `ActuationIntent`, `ActuationResult`, or the local `models.py`
  types outside `src/autofde_lab/gymact/` (`api.py`, `cli.py`, `mcp.py`, and anything under
  `scripts/` or `src/autofde_lab/hub/`) that the initial grep missed and that depends on
  behavior the rewrite changed — e.g. the new `episode_id` mapping layer, or the `receipt=None`
  behavior for the four local-only operations.
- The `[tool.uv.sources]` / concurrent-edit resolution on `pyproject.toml` being wrong in a way
  that only manifests on a clean install (this report's own install used
  `uv pip install -e ... --python .venv/bin/python` directly, not the standard `uv sync` path,
  because `uv sync` is independently broken by the unrelated `wasm4pm-compat-py` missing
  sibling — so the dependency resolution itself was never exercised end-to-end through the
  normal `uv sync` flow).

## Final standing

**PARTIAL_ALIVE.**

Grounded in: a real, reproducible 16/16 pytest pass against the real `.venv/bin/python`
interpreter, confirmed real (non-stubbed) `gymact.runtime.GymAct` / `gymact.providers`
delegation via `__module__` inspection, and a diff footprint matching the claimed file list.

Not ALIVE because: the dependency was never installed through the project's normal `uv sync`
path (that path is independently broken by an unrelated missing sibling repo, so this refactor's
`pyproject.toml`/`uv.sources` change has not been exercised end-to-end through a clean install);
the falsifiers above (exception-swallowing in `_run_async`, an unwatched caller outside
`src/autofde_lab/gymact/`) were not exhaustively ruled out, only checked where the grep/diff
evidence reached.
