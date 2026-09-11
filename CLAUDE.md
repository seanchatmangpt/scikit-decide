# autofde-lab

AI framework for Reinforcement Learning, Automated Planning, and Scheduling —
a fork of Airbus AI Research's `scikit-decide`, renamed to `autofde-lab`
(`gh repo rename`, confirmed live; GitHub project management applied for real
this session, see `docs/STATUS.md`) as this project pivoted to be the
foundation layer of the Chatman Ecosystem portfolio. Within that portfolio
(`FORWARD_DEPLOYMENT.md`) — the "Forward Deployment OS," whose canonical
portfolio narrative lives in `seanchatmangpt/chatman-ecosystem` — this
repository is the foundation layer: the canonical decision, planning, and
integration control plane, the lawful selection surface between admitted
operational state and candidate plans.

**It computes candidate plans. It does not actuate.** A planner selects; a
broker authorizes; an executor performs; a verifier evaluates. Nothing here
carries ambient authority to change the world, and nothing here should be
given receipt, admission, or actuation semantics. Actuation runs through
OpenClaw, never through BRCE (which belongs to other systems in the
portfolio and has no role here).

The same law applies to gyms. `vendor/gyms/` (sregym, devops-gym,
enterprisebench, ...) are real, exact-pinned vendored checkouts for
**reference only** — read their source, cite it, audit/materialize their
git pin. This repo never imports or subprocess-launches them directly.
`gymact` (the real, standalone sibling package at `~/gymact`) is the one
real actuation surface for any gym; every real diagnosis/mitigation trial
goes through it. See `.claude/rules/gym-actuation-boundary.md`.

Repository: https://github.com/seanchatmangpt/autofde-lab | Upstream:
https://github.com/airbus/scikit-decide | Docs:
https://airbus.github.io/scikit-decide/

Check `docs/KNOWN_FACTS.md` before re-implementing domain-construction fallback
logic, re-deriving the actuation boundary, or manually re-running a "diff two
runs" idempotency check — read it first, verify against its cited pointer if you
need more, and add a dated entry if you learn something new that cost real
re-derivation time.

## Always in force

@.claude/rules/standing-law.md

@.claude/rules/absence-is-not-evidence.md

@.claude/rules/no-dual-bookkeeping.md

@.claude/rules/level4-completion-law.md

All four are imported, not merely referenced — every session needs them, and
each was written after a specific defect got through:

1. **standing-law** — the status vocabulary every claim carries.
2. **absence-is-not-evidence** — what may enter O* from O. A learned model
   that coerces `UNKNOWN` into whatever value suits a planner hands it a
   certainty the experiment never established; the resulting confident-wrong
   plan is an *admission* defect, not a planner defect. Written after a frozen
   crown scored 8/10 against a conjunction in which one factor could not fail.
3. **no-dual-bookkeeping** — where claims may live. Written after derived
   Python summary state drifted from the execution record three separate
   times, each caught only by adversarial audit.
4. **level4-completion-law** — what completion *is*. Written after edge counts
   and crown scores were reported as though they were standing.

They share one law: never manufacture semantics from absence, coincidence,
prediction, or a secondary representation when the primary evidence can carry
the relation itself.

Everything below is **path-gated**, not imported. Each `.claude/rules/*.md`
carries YAML `paths:` front-matter and loads only when a matching file is
read. This distinction is load-bearing and was got wrong once: an `@` import
is expanded into `CLAUDE.md` at session start, so splitting a long file into
six imports reorganises text without reducing anything. A rules file with no
`paths:` gate also loads unconditionally. The table below is a routing hint
for a human reader; the gates are what actually control loading.

## Working across the ecosystem

Cross-repo claims require the sibling repos' own doctrine, not just their
code. `--add-dir` grants file access but **not** instruction loading — that
needs an environment variable:

```bash
CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1 claude \
  --add-dir ~/mfw --add-dir ~/bcinr --add-dir ~/praxis \
  --add-dir ~/ggen --add-dir ~/ggen-create --add-dir ~/ggen-legacy \
  --add-dir ~/wasm4pm --add-dir ~/wasm4pm-compat
```

Without it, you read sibling code with none of its rules — the exact
condition that produced a false ecosystem-wide claim from a search that had
never looked at `~/bcinr`. Verify with `/memory` and `/context`, don't assume.

## Look this up when you are doing that

| When you are… | Read |
|---|---|
| reporting status, or writing any Explore-phase report to the user | `.claude/rules/explore-register.md` |
| about to `git push`, open/merge a PR, release, deploy docs, trigger long CI, or call the OpenClaw bridge | `.claude/rules/actuation-boundary.md` |
| adding or modifying a domain, solver, or C++ hub solver; or looking for where anything lives | `.claude/rules/architecture.md` |
| touching `vendor/gyms/**`, `src/autofde_lab/gymact/**`, `src/autofde_lab/reasoning/**`, or `src/autofde_lab/sota/**` — or working on gymact/sregym actuation at all | `.claude/rules/gym-actuation-boundary.md` |
| making any claim that spans `~/mfw`, `~/ggen`, `~/ggen-create`, `~/ggen-legacy`, or `~/bcinr` | `.claude/rules/ecosystem-boundary.md` **and** `docs/ecosystem-standing.md` |
| touching `fabric/pddl_engine.py`, `fabric/powl.py`, PDDL requirements, or the capability ontology | `.claude/rules/ecosystem-boundary.md` |
| reaching for a project skill or agent instead of re-deriving a workflow | `.claude/rules/project-tooling.md` |
| filing what you just did into the in-repo ledger | `docs/STATUS.md` |
| writing or reviewing any test | `.claude/rules/testing-chicago-style.md` |

## Four rules that do not fit in a table

These are the ones most likely to be violated by someone who read only this
page, so they stay inline.

1. **A solver/domain claim is `ALIVE` only with a Chicago-style test
   exercising `solve()` on a real domain, run this session.** Never
   "compiles," never "the happy path works." Queued CI, a merged PR, and a
   green synthetic check are not evidence — only an executed job against the
   exact commit is. This is the solver/domain instance of a repo-wide rule:
   see `.claude/rules/testing-chicago-style.md` for the general no-mocking
   discipline and its verification requirement.

2. **Projection is not execution.** `fabric/powl.py` writes
   `plan.powl.ttl`; that manufactures a document, it does not run a
   workflow. An earlier pass in this repo let the projector stand in for an
   executor and had to be retracted. As of 2026-08-06 no component in the
   portfolio executes a POWL plan end to end — see `docs/ecosystem-standing.md`.

3. **Never remove the PDDL requirements gate in `fabric/pddl_engine.py`.**
   The C++ backend parses `:derived-predicates`, `:constraints` and
   `:preferences` and implements none of them, silently — so planning would
   return a confident, plausible, *wrong* plan. A wrong plan that can be
   admitted downstream is strictly worse than a refusal.

4. **Capability claims must be ontology-backed.**
   `ontology/autofde-lab-capabilities.ttl` is generated
   (`python -m autofde_lab.fabric.ontology ontology/autofde-lab-capabilities.ttl`) —
   regenerate it, never hand-edit, and note that `tests/ecosystem/` fails if
   it drifts from the registry. This is an epistemic control, not
   documentation: a false ecosystem claim was made in this repo's history
   from a search that had simply never looked at one of the repositories.

## Build

`uv sync --extra=all -v`; `pre-commit run --all-files`.
Python 3.10+ per `pyproject.toml`; the verified working dev environment is
3.13.9 — treat 3.13 as current, not merely supported. CMake/C++20/pybind11
for the compiled extension.

**Known first-sync race on a genuinely fresh clone: retry once, don't
loop.** On a from-scratch clone (no prior `.venv`, no cached `uv.lock`
resolution), the *first* `uv sync --extra=all` can fail with
`AssertionError: Metadata mismatch in METADATA` raised from inside
scikit-build-core. Root cause: `uv` rewrites `uv.lock` in place during that
first sync (the lock has no cached resolution yet), and this repo's own
package version is computed from git's VCS dirty-bit twice during that same
sync (once for the sdist metadata, once for the wheel build) — the `uv.lock`
rewrite flips the working tree from clean to dirty between those two
computations, so the two metadata blocks disagree and scikit-build-core's
consistency assertion trips. An immediately repeated, identical `uv sync
--extra=all` always succeeds, because `uv.lock` is now stable and the
dirty-bit no longer flips mid-run. This is a real, reproducible one-time
race (confirmed on two separate fresh clones), not flaky infra — if the
first `uv sync --extra=all -v` fails with that exact assertion, re-run the
same command once before treating it as a real failure. Do not paper over a
*different* failure with a blind retry loop; this is a named, narrow
exception for this specific error signature only.

**Tests: use `.venv/bin/python -m pytest ...`, not `uv run pytest ...`.**
`uv run` re-checks the native build on every invocation (a full CMake/Ninja
pass, tens of seconds to minutes on an unchanged tree) before pytest even
starts; `.venv/bin/python -m pytest` skips that check entirely. Reach for
`uv run` only when dependencies or build config actually changed.

Two local test commands, both defined in `Justfile`, matching
`.github/workflows/pr-ci.yml` / `ci.yml`'s own job routing 1:1 so they never
drift from what CI asserts:

- `just test` — the hot loop for routine dev work: **unit-weight tests only,
  ~5.9-6.0s measured over several runs, `-n 4` pytest-xdist workers** (swept
  `{4,6,8,12,auto}`, 4 wins consistently — more workers get *slower* since no
  test here exceeds 5s but each worker repays full import startup cost).
  Ignores the native C++ solvers, RL/native-heavy python solvers
  (`tests/solvers/cpp`, `tests/solvers/python`), `tests/scheduling`,
  `tests/ecosystem` (cross-repo crown), **`tests/domains` and
  `tests/flight_planning` entirely** (not because their tests are slow
  individually, but because collecting them pays for
  torch_geometric/unified-planning/cartopy/gymnasium/openap/pygeodesy —
  `tests/domains` alone measured ~7s just to *collect*), the real-`terraform`-binary
  `tests/autofde/test_terraform_guards.py`, the two real-MCP-server
  (`fastmcp` `Client`) tests `tests/fabric/test_dspy_mcp_planner_loop_chicago.py`
  and `tests/fabric/test_mcp_ocel_instrumentation_chicago.py` (~5.9s alone —
  the single largest item found when this pass profiled the hot loop with
  `--durations`), the
  fresh-subprocess-per-test `tests/powl/test_import_separation.py`, one
  `--deselect` for `test_up_bridge_domain_rl` (real `ray.rllib` DQN training,
  silently free on macOS only via an unrelated `libomp` skip — pulled out
  structurally so it doesn't ride the hot path on Linux/CI), the three
  real-subprocess-LLM-server Chicago tests, and the two WASM tests
  (separately-tracked WIP: packaged archive is corrupt). Nothing here is
  dropped from coverage — everything excluded still runs, unrestricted, in
  `test-full`. Full rationale and the exact exclusion list live as comments
  in the `Justfile` itself; don't let this paragraph drift from it.
- `just test-full` — everything, the same four partitions `ci.yml`'s
  `integration` job runs. Minutes, not seconds — run before finishing a
  branch, not on every edit.
- `uv run pytest --nbmake notebooks -v` for notebooks (unaffected by the
  above; not part of either Justfile target).

Whole-suite collection previously failed on a `test_pomcp.py` basename
collision (`tests/solvers/cpp` vs `tests/solvers/python`) and a bare-`conftest`
module-name collision (`tests/conftest.py` vs
`tests/solvers/python/{openevolve,autoregressive}/conftest.py`) — fixed by
`--import-mode=importlib`, **not** `__init__.py` markers: those were tried
first, fixed both collisions, and broke Ray/RLlib worker unpickling and
shadowed the real `openevolve` package in the same session — see
`docs/STATUS.md` Pass 6. The flag is passed explicitly where needed
(`.venv/bin/python -m pytest tests --collect-only -q --import-mode=importlib`
for a whole-suite check), **not** set as a `pyproject.toml` default — it's
~2.2x slower than the default mode and neither `just test` nor
`just test-full` ever needs it (see the Build section above and the
`Justfile`'s own comments). `.claude/rules/standing-law.md` records the
corrected history; re-verify before citing it, per that file's own
instruction.

## See also

- `docs/ecosystem-standing.md` — cross-repository standing ledger: per-stage
  `ALIVE`/`BLOCKED`/`UNSUPPORTED`, the per-transition proof that nothing
  executes a POWL plan, and repair plans RP-1…RP-7. Read before making any
  cross-repo claim.
- `docs/STATUS.md` — the in-repo WIP ledger and the worked example of the
  measured-win / recorded-negative discipline.
- `FORWARD_DEPLOYMENT.md` — this repo's role in the portfolio; the
  `A = μ(O*)`, `R = receipt(A)` law the rules files instantiate locally.
- `docs/agentic-fabric.md` — full design of the CLI/MCP/A2A/DSPy layer.
- `docs/chatman-ecosystem-wasm.md` — the WASM adapter surface, using an
  `ALIVE`/`REFUSED`/`BUILD_BROKEN` vocabulary that explicitly rejects
  `BLOCKED` — narrower than the standing law here; don't conflate them.
- `docs/guide/chatman-clean-session.md` — `ChatmanCleanSessionDomain`;
  documents BRCE as the portfolio's actuation DO-boundary, not this repo's.
- `docs/` (general) — explanation and projections; never an authority for
  standing or proof claims.
- `~/CLAUDE.md`, `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md` — personal and
  global defaults that `.claude/rules/` restates in this repo's vocabulary.
