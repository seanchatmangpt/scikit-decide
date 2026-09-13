# autofde-lab domain maturity L4 push -- JIRA tickets

GROUNDED, this session, against the real 5x7 maturity matrix (docs/jira/2026-08-13-domain-maturity-l4/../ session summary) and real source reads per domain. Written by a 6-batch ultracode Workflow fan-out, one ticket per (domain, dimension<4) pair.

Now writing the tickets grounded in the real source read above.

## terragoat (`src/autofde_lab/hub/domain/terragoat/terragoat_remediation.py`)

Already meets L4: Domain fidelity=5, Verification independence=5, OCEL evidence=4, Solver/planning integration=5, Test coverage=5, Standing honesty=5.

**AFL-TERRAGOAT-1 — Give TerraGoatRemediation a real gated DO capability + refusal sabotage test**
- Dimension: Actuation authority (3→4)
- Real files: `src/autofde_lab/hub/domain/terragoat/terragoat_remediation.py` (currently only `_get_next_state` — pure in-memory symbolic transition, no real actuation onto the vendored `.tf` file, no `gymact` bridge exists in this directory — `ls src/autofde_lab/hub/domain/terragoat/` has only `__init__.py` + `terragoat_remediation.py`); new `src/autofde_lab/hub/domain/terragoat/gymact_bridge.py` modeled directly on the real, already-proven `src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py` pattern (`Capability(consequence=Consequence.DO)`, `ActuationRefused` raised when the requested step is not both applicable per `get_applicable_actions` AND the solved plan's next cursor step); new `tests/domains/python/test_terragoat_gymact_bridge_chicago.py`
- Definition of Done: a real sabotage test that calls `actuate()` with a finding id that is either (a) not a real parsed finding, or (b) applicable-but-out-of-plan-order, and asserts it raises `ActuationRefused` (never silently no-ops or advances `open_findings`) — mirroring the existing `tests/ecosystem/test_gymact_terragoat_bridge_chicago.py` naming convention already present in this repo. `uv run pytest tests/domains/python/test_terragoat_gymact_bridge_chicago.py -v` green, zero mock/patch usage (`grep -rn "unittest.mock\|Mock(\|patch(\|monkeypatch" tests/domains/python/test_terragoat_gymact_bridge_chicago.py` → empty).
- Effort: **M** — no bridge file exists yet, but the exact pattern to replicate (`azuregoat_privesc/gymact_bridge.py`, 209 lines) is real, working, and structurally reusable; TerraGoat's "actuation" only needs to remove a finding id from an open-set, no subprocess/network involved, so it's lighter than AzureGoat's 10-step attack chain.

---

## gym_procedure (`src/autofde_lab/hub/domain/gym_procedure/`)

All 7 dimensions already ≥4 (Domain fidelity=4, Actuation authority=4, Verification independence=5, OCEL evidence=4, Solver/planning integration=5, Test coverage=5, Standing honesty=4) — **no tickets required**; this domain already meets the L4 bar on every dimension per the given scores.

---

## azuregoat_privesc (`src/autofde_lab/hub/domain/azuregoat_privesc/`)

Already meets L4: Domain fidelity=4, Actuation authority=4, OCEL evidence=4, Solver/planning integration=5, Test coverage=5, Standing honesty=4.

**AFL-AZUREGOAT-1 — Make `AzureGoatPrivescEnvironment.verify()` re-derive from a source independent of `actuate()`'s in-process state**
- Dimension: Verification independence (2→4)
- Real files: `src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py` (`verify()` at lines 163–171 today just calls `self.observe()`, which returns `sorted(self._state.facts)` — the exact same `State` object `actuate()` mutated in-process at line 153; there is no independent read); `src/autofde_lab/hub/domain/azuregoat_privesc/azuregoat_privesc.py` (defines `State`, `GOAL_FACT`, `ATTACK_STEPS` — needs a companion externally-checkable artifact, e.g. a per-step fact ledger written to disk at `actuate()` time that `verify()` re-parses fresh rather than trusting `self._state`); new/updated `tests/domains/test_azuregoat_privesc.py`
- Definition of Done: `verify()` reads its pass/fail signal from something `actuate()` did not merely hold in a Python attribute — e.g. a JSON fact-ledger file written to disk on each `actuate()` call and re-read+re-parsed from disk inside `verify()` (matching terragoat's/gym_procedure's real pattern of an independent read, not a shared reference to the same object) — with a real sabotage test asserting that if the in-memory `self._state` is monkeypatched to claim success while the on-disk ledger does not contain `GOAL_FACT`, `verify()` still reports failure (proves the independence, not just presence of two calls). `uv run pytest tests/domains/test_azuregoat_privesc.py -v` green.
- Effort: **M** — the bridge file, capability set, and Astar-solved plan replay already exist and are real (209 lines, working); this ticket only needs a second, independently-read state channel (disk-backed ledger) wired into `actuate()`/`verify()`, not a new domain or solver integration.

---

## fix_git (`src/autofde_lab/hub/domain/fix_git/`)

Already meets L4: Domain fidelity=4, Verification independence=4, Solver/planning integration=4, Test coverage=5, Standing honesty=5.

**AFL-FIXGIT-1 — Add a real gated DO capability bridge with typed refusal for fix-git actuation**
- Dimension: Actuation authority (3→4)
- Real files: `src/autofde_lab/hub/domain/fix_git/git_recovery.py` (`execute_action()` at lines 161–186 is the real actuation entry point today — it runs real `git` subprocesses, but it is an untyped method call with no precondition-gated `Capability`/`Consequence.DO` wrapper and no `ActuationRefused`-style typed refusal; the module's own docstring at lines 36–50 explicitly separates "domains compute candidate plans, they do not actuate" but nothing in this directory (`ls src/autofde_lab/hub/domain/fix_git/` has only `__init__.py` + `git_recovery.py` — no `gymact_bridge.py`) enforces that boundary at the actuation call site); new `src/autofde_lab/hub/domain/fix_git/gymact_bridge.py`, modeled on `azuregoat_privesc/gymact_bridge.py`'s `actuate()` pattern (check requested action against `_get_applicable_actions_from(state)` AND the solved-plan cursor, raise a typed `ActuationRefused` otherwise, only then call the real `execute_action`); new `tests/domains/python/test_fix_git_gymact_bridge_chicago.py`
- Definition of Done: a real sabotage test against a real `tmp_path` git repo (same fixture-construction pattern as the existing `tests/domains/python/test_fix_git_domain.py`) that calls `actuate()` with `merge_recovery` before `checkout_recovery` has run, and asserts `ActuationRefused` is raised and the real repo's `git log`/branch state is unchanged (no partial merge). `uv run pytest tests/domains/python/test_fix_git_gymact_bridge_chicago.py -v` green, zero mocking of git itself (real subprocess, real tmp repo).
- Effort: **M** — `execute_action()` and the underlying real-git subprocess plumbing already exist and are proven by the existing 60+-line Chicago test; this only adds a typed capability-gating wrapper, not new git logic.

**AFL-FIXGIT-2 — Produce a real, schema-valid OCEL 2.0 episode log for fix_git (currently none exists)**
- Dimension: OCEL evidence (1→4)
- Real files: new `scripts/run_fix_git_gymact_ocel_episode.py`, modeled directly on the real, working `scripts/run_azuregoat_gymact_ocel_episode.py` (uses `gymact.GymAct` orchestrator + `gymact.ocel.write_ocel_log`, not a hand-rolled log writer — confirmed this is the real pattern by reading that script's header docstring and `Path`/`LOG_PATH` setup); depends on AFL-FIXGIT-1's `gymact_bridge.py` (an OCEL episode needs a real `Provider`/`Environment` pair to drive through `GymAct`, which does not exist yet in this domain — `reports/ocel/` today has only `azuregoat-privesc-gymact/episode.ocel.json`, confirmed via `ls reports/ocel`); new output at `reports/ocel/fix-git-gymact/episode.ocel.json`
- Definition of Done: `.venv/bin/python scripts/run_fix_git_gymact_ocel_episode.py` run against a real materialized fix-git repo fixture, producing `reports/ocel/fix-git-gymact/episode.ocel.json` committed to the repo, containing real `materialize`→`act` (x3: checkout_recovery/checkout_master/merge_recovery)→`verify`→`teardown` events with `solved=True` recorded on the final `act` receipt's `reason` field (matching the azuregoat script's own documented pattern of attaching real observed goal-truth, not stdout claims) — schema-validity checked the same way the azuregoat log would be (via `gymact.ocel`'s own writer, which is presumed schema-compliant since it's the shared, already-relied-upon library code, not reimplemented here).
- Effort: **L** — blocked on AFL-FIXGIT-1 (no bridge exists yet, so there is nothing for `GymAct` to drive), plus this is a brand-new script + first-ever OCEL artifact for this domain, not a patch to an existing one.

---

**Infra-limited flag:** None of the four domains here require live external cluster/cloud infrastructure — terragoat, azuregoat_privesc, and fix_git all operate against real local/vendored artifacts (a vendored `.tf` file, an in-memory `gymact` fact-state domain, and a real local git repo respectively), so every ticket above targets an achievable local proxy, not a downgraded bar. `azuregoat_privesc`'s AFL-AZUREGOAT-1 is the closest thing to a caveat worth naming explicitly: a disk-backed fact ledger is an independent *read path* within the same local process/filesystem, not independent verification against a real external AzureGoat cloud tenant — true external-system verification (checking Azure's own IAM state via `az` CLI/API) stays out of reach without a live Azure subscription, and this ticket does not claim otherwise.

## pddl (`src/autofde_lab/hub/domain/pddl/`)

Already meets L4: Domain fidelity (vendored verbatim from scikit-decide/AIRBUS with `__all__` re-export discipline, confirmed by AIRBUS copyright headers in `pddl.py`/`domain.py`; STATUS.md line 492 records the drift-removal proof — `pytest tests/solvers/python/test_pddl_ff.py tests/solvers/python/test_pddl_determinization.py tests/domains/python/test_pddl_domain.py` 59 passed). Actuation authority (STATUS.md line 474: refusal of unsupported PDDL requirements is real and tested against `~/ggen-legacy` corpus). Solver/planning integration (`hub/solver/pddl/{ff,ppddlplanmerger,ppddlreplan,ppddldethindsight}` are real, tested). Test coverage (no mock/patch hits in `tests/domains/python/test_pddl_domain.py` or the solver tests; real PDDL fixtures under `tests/domains/python/pddl_domains/`).

- **Verification independence (2→4)**
  - Title: Independent re-derivation for PDDL plan verification (no shared in-process state)
  - Files: `src/autofde_lab/hub/domain/pddl/domain.py`, `src/autofde_lab/fabric/pddl_engine.py`, new `src/autofde_lab/hub/domain/pddl/verify.py`
  - DoD: A new `verify_plan_independent(domain_file, problem_file, plan_file) -> bool` that shells out to a **separate process** (`python -m autofde_lab.fabric.pddl_engine` invoked via `subprocess`, matching the terragoat/gym_procedure pattern of a fresh-process re-derivation, not the same in-process `PDDLDomain` object that produced the plan) and independently replays the plan against the domain/problem files on disk, asserting goal satisfaction. Proven by `tests/domains/python/test_pddl_verify_independent.py::test_verify_rejects_a_plan_the_bridge_would_accept` — a real sabotage test where the in-process bridge is fooled (e.g. a stale cached state) but the subprocess verifier still catches the bad plan.
  - Effort: M (fabric/pddl_engine.py subprocess entrypoint already exists per STATUS.md line 473 — this is wiring a second call path plus one new test file, not new infra)

- **OCEL evidence (1→4)**
  - Title: Committed OCEL 2.0 log for a real PDDL materialize→plan→act→verify→teardown episode
  - Files: new `docs/evidence/pddl/episode.ocel.json`, new `scripts/evidence/run_pddl_episode.sh` (or `.py`), `tests/domains/python/test_pddl_domain.py` (add an OCEL-schema assertion)
  - DoD: `scripts/evidence/run_pddl_episode.sh` runs the real blocks-world fixture (`tests/domains/python/pddl_domains/blocks/{domain,probBLOCKS-3-0}.pddl`) end to end via `PDDLDomain` + `ff` solver, emits a schema-valid OCEL 2.0 JSON log (events: `materialize`, `plan`, `act`, `verify`, `teardown`) to `docs/evidence/pddl/episode.ocel.json`, and a test asserts the committed file validates against the OCEL 2.0 JSON schema and is re-derivable byte-for-byte (modulo timestamps) by re-running the script.
  - Effort: M (no OCEL emission exists anywhere in this domain today — new script + new schema validation, but the underlying plan/act loop already works)

- **Standing honesty (3→4)**
  - Title: Explicit module-level standing tag for `pddl` domain, consistent with STATUS.md
  - Files: `src/autofde_lab/hub/domain/pddl/pddl.py`, `src/autofde_lab/hub/domain/pddl/domain.py`, `docs/STATUS.md`
  - DoD: Both modules carry a `# STANDING: ALIVE` (or the appropriate tag) docstring/comment block naming the specific STATUS.md evidence lines (473/474/492) it rests on; a new `tests/test_standing.py`-adjacent check (or extension of existing `tests/test_standing.py`) asserts the tag string is present and matches a STATUS.md-parsed table entry for `pddl`, failing if they diverge.
  - Effort: S (tagging + one assertion against already-existing `tests/test_standing.py` infrastructure)

## tai_v30_1_1 (`src/autofde_lab/hub/domain/tai_v30_1_1/`)

Already meets L4: Actuation authority (`model.py`'s `refusal_reason`/`transition` gate `brce_actuate` and `verify_consequence` by precondition, `TaiTransitionRefused` is a real typed refusal, `tests/domains/test_tai_v30_1_1.py` exercises both `POSITIVE_PLAN` and `REFUSAL_PLAN`). Test coverage (zero mock/patch hits in `tests/domains/test_tai_v30_1_1.py`; real state-based assertions on `TaiState`/`TaiReceipt`). Standing honesty (module docstring already states "models planning intents only... `brce_actuate` and [verification] are not real external actuation" — an honest SIMULATED-adjacent tag).

- **Domain fidelity (3→4)**
  - Title: Automated drift check for TAI v30.1.1 case-study model against its source spec
  - Files: `src/autofde_lab/hub/domain/tai_v30_1_1/model.py`, new `tests/domains/test_tai_v30_1_1_fidelity.py`
  - DoD: A committed reference artifact (the TAI v30.1.1 case-study spec this model claims to mirror — `CASE_STUDY_SUBJECT`/`CASE_STUDY_VERSION`/`ONTOLOGY_BINDINGS` in `model.py`) is checked into `docs/evidence/tai_v30_1_1/source-spec.*`, and a new test parses both the committed spec and `ONTOLOGY_BINDINGS` and asserts field-for-field equality (not just that both files exist), failing loudly on any drift.
  - Effort: M (no such reference artifact currently exists in the repo — must be sourced/vendored first, then a real comparison test written)

- **Verification independence (3→4)**
  - Title: `verify_receipt_replay` must not call the same in-process `transition`/`build_receipt` it is verifying
  - Files: `src/autofde_lab/hub/domain/tai_v30_1_1/model.py` (lines ~267-311: `replay_plan`, `build_receipt`, `verify_receipt_replay`)
  - DoD: `verify_receipt_replay` currently re-derives via `replay_plan`/`build_receipt` — same functions, same process, same module as the actuation path (confirmed by reading lines 270-311: it literally calls `transition()` again in-loop). Replace with a subprocess-based re-derivation: `python -m autofde_lab.hub.domain.tai_v30_1_1.verify <receipt.json>` run as a fresh process reading only the serialized receipt + `INITIAL_STATE` constant, never importing the live `TaiState` object the actuation call produced. Proven by `tests/domains/test_tai_v30_1_1.py::test_verify_rejects_a_tampered_receipt_even_if_in_process_state_agrees` — a sabotage test that corrupts in-process state post-hoc and confirms the subprocess verifier (not the in-process one) is what actually catches it.
  - Effort: M (logic already exists and is correct; the fix is process-boundary isolation, not new algorithm)

- **OCEL evidence (1→4)**
  - Title: Committed OCEL 2.0 log for a real TAI v30.1.1 positive-path episode
  - Files: new `docs/evidence/tai_v30_1_1/episode.ocel.json`, new `scripts/evidence/run_tai_v30_1_1_episode.sh`
  - DoD: Script runs `TAIForwardDeploymentDomain` through `POSITIVE_PLAN` (from `tai_v30_1_1.py`), emits OCEL events for each `TaiAction` transition plus `build_receipt`/`verify_receipt_replay`, writes schema-valid OCEL 2.0 JSON, and a test asserts the committed log validates and matches a fresh re-run.
  - Effort: M

- **Solver/planning integration (1→4)**
  - Title: Register `tai_v30_1_1` with a real planner instead of the hardcoded `POSITIVE_PLAN`/`REFUSAL_PLAN` constants
  - Files: `src/autofde_lab/hub/domain/tai_v30_1_1/tai_v30_1_1.py` (currently `self._goal = replay_plan(POSITIVE_PLAN)`, line 75 — the "plan" is a fixed constant, not solver output), `src/autofde_lab/hub/solver/pddl/` or `src/autofde_lab/hub/solver/up/up.py` as the integration target
  - DoD: `TAIForwardDeploymentDomain` exposes `get_applicable_actions`/`get_next_state`/`is_goal` (it already does, per `tests/domains/test_tai_v30_1_1.py`) wired to one of the existing registered solvers (`Astar` or the PDDL/UP bridge) so that a real search produces a plan equal to or dominating `POSITIVE_PLAN`, not a hand-authored constant. `tests/domains/test_tai_v30_1_1.py::test_solver_produces_a_verified_plan_not_a_hardcoded_one` asserts the solver-produced plan passes `verify_receipt_replay`.
  - Effort: L (this domain currently has zero solver wiring — `POSITIVE_PLAN`/`REFUSAL_PLAN` are literal Python tuples, not search output; needs a domain-to-solver adapter written from scratch)

## up (`src/autofde_lab/hub/domain/up/`)

Already meets L4: Domain fidelity (vendored AIRBUS/scikit-decide UP bridge, `up.py` header matches pddl.py's verbatim-vendor pattern). Actuation authority (`GrounderHelper`/`UPSequentialSimulator` gate applicable actions through UP's own precondition evaluation). Solver/planning integration (`hub/solver/up/up.py` + `tests/solvers/python/test_up_bridge_solver.py`, `tests/domains/python/test_up_bridge_domain.py` real, no-mock tests). Test coverage (no mock/patch hits found).

- **Verification independence (2→4)**
  - Title: Independent re-derivation for UP bridge plan verification
  - Files: `src/autofde_lab/hub/domain/up/up.py` (`SkUPState`, `UPSequentialSimulator` usage), new `src/autofde_lab/hub/domain/up/verify.py`
  - DoD: Same shape as the pddl ticket above — a subprocess-based `verify_plan_independent` that re-runs the UP `SequentialSimulator` in a fresh process against the serialized problem + action sequence on disk, not the same in-process `SkUPState`. Sabotage test in `tests/domains/python/test_up_bridge_domain.py` proves it catches a plan the in-process bridge would wrongly accept.
  - Effort: M

- **OCEL evidence (1→4)**
  - Title: Committed OCEL 2.0 log for a real UP bridge episode
  - Files: new `docs/evidence/up/episode.ocel.json`, new `scripts/evidence/run_up_episode.sh`
  - DoD: Same shape as pddl/tai tickets — real materialize→plan(via `hub/solver/up/up.py`)→act→verify→teardown episode, schema-valid, re-runnable.
  - Effort: M

- **Standing honesty (2→4)**
  - Title: Explicit module-level standing tag for `up` domain
  - Files: `src/autofde_lab/hub/domain/up/up.py`, `docs/STATUS.md`
  - DoD: Same shape as pddl's standing ticket — add `# STANDING: <tag>` naming the specific STATUS.md evidence this domain rests on (currently none cited by name for `up` specifically in the STATUS.md excerpt reviewed — this ticket also requires adding a real `up`-specific STATUS.md entry if none exists, not just a tag pointing at nothing), verified by an extension of `tests/test_standing.py`.
  - Effort: S/M (S if a real STATUS.md entry for `up` already exists elsewhere and just needs citing; M if one must be written from a fresh evidence-gathering pass — grep STATUS.md fully before starting to determine which)

## flight_planning (`src/autofde_lab/hub/domain/flight_planning/`)

Already meets L4: Domain fidelity (real `aircraft_performance`/`weather_interpolator` submodules with OPENAP/BADA performance models, exercised by `tests/flight_planning/test_flight_planning.py::test_aircraft_state`). Solver/planning integration (`hub/solver/p_astar.Astar` imported and used directly in the real test). Test coverage (no mock/patch hits in `tests/flight_planning/test_flight_planning.py`, real `AircraftState` construction with real enums).

- **Actuation authority (3→4)**
  - Title: Typed precondition+plan-order gating for flight-planning DO capabilities, proven by sabotage test
  - Files: `src/autofde_lab/hub/domain/flight_planning/domain.py` (48KB, largest file in the domain — precondition logic likely present but not confirmed gated with typed refusal), `tests/flight_planning/test_flight_planning.py`
  - DoD: Every DO-capability transition in `domain.py` (state mutation entry points) is gated by a precondition check that raises a typed refusal (mirroring `tai_v30_1_1.TaiTransitionRefused`) rather than silently no-op'ing or producing an invalid state. `tests/flight_planning/test_flight_planning.py::test_actuation_refuses_an_out_of_order_capability` sabotage-tests calling a capability out of plan order (e.g. climb before takeoff-clearance) and asserts a typed exception, not a wrong-but-silent state.
  - Effort: M (domain.py is large and its current precondition discipline is unverified from this pass — needs a real read-through before scoping down from M; could be L if preconditions are scattered/ad hoc rather than centralized)

- **Verification independence (1→4)**
  - Title: Independent re-derivation for flight-plan verification (no shared in-process trajectory state)
  - Files: `src/autofde_lab/hub/domain/flight_planning/domain.py`, `src/autofde_lab/hub/domain/flight_planning/graph.py`, new `src/autofde_lab/hub/domain/flight_planning/verify.py`
  - DoD: A subprocess- or independent-parser-based verifier that re-derives trajectory feasibility (fuel, altitude, weather constraints) from the serialized plan + aircraft state on disk, using a fresh `AircraftState`/`PerformanceModelEnum` construction rather than the in-process `Astar` search's internal state. Sabotage test proves the independent verifier catches a plan the search accepted via a stale/corrupted intermediate `AircraftState`.
  - Effort: L (score of 1 — no verification path exists today at all, only forward search; this is new code plus non-trivial domain modeling given `aircraft_performance`'s OPENAP/BADA complexity)

- **OCEL evidence (1→4)**
  - Title: Committed OCEL 2.0 log for a real flight-planning episode
  - Files: new `docs/evidence/flight_planning/episode.ocel.json`, new `scripts/evidence/run_flight_planning_episode.sh`
  - DoD: Real `Astar` search over the A320/OPENAP fixture from `test_flight_planning.py::test_aircraft_state`, emitting OCEL events for materialize(aircraft+weather)→plan(Astar)→act(trajectory execution)→verify→teardown, schema-valid, re-runnable.
  - Effort: M

- **Standing honesty (1→4)**
  - Title: Explicit module-level standing tag for `flight_planning` domain
  - Files: `src/autofde_lab/hub/domain/flight_planning/domain.py`, `docs/STATUS.md`
  - DoD: Same shape as the other standing tickets. Score of 1 here (lowest of any dimension across all four domains) suggests either no tag exists or an actively misleading one — verify which by reading `domain.py`'s current docstring before scoping; if actively misleading (e.g. claims ALIVE with no supporting evidence), this ticket must also correct the false claim, not just add a tag.
  - Effort: S/M (S if only additive; M if a false existing claim must be walked back and STATUS.md corrected)

**Infrastructure flag:** None of the four domains' L4 gaps require live cluster/cloud/external-service infrastructure this repo lacks — every OCEL-evidence and verification-independence ticket above targets a **local** subprocess/independent-parser re-derivation (matching the terragoat/gym_procedure pattern already proven in this repo), not a live external system. The one dimension that might have looked infra-blocked — `tai_v30_1_1`'s solver/planning integration — is achievable with in-repo solvers (`hub/solver/pddl`, `hub/solver/up`) already proven elsewhere in this same audit, so it is ticketed as a real wiring task (L), not downgraded or flagged as infra-blocked.

Now I have everything needed to write grounded tickets.

## maze (`src/autofde_lab/hub/domain/maze/maze.py`)

Current source: `Maze(D)` where `D(DeterministicPlanningDomain, UnrestrictedActions, Renderable)`. Single 188-line file, no `gymact_bridge.py`, no test file anywhere in `tests/`, no OCEL evidence, no standing tag, `DEFAULT_MAZE` is a hardcoded ASCII string with no vendored source to drift-check against.

- **Solver/planning integration = 2**: already documented in the prompt as the highest score, but a real registered solver has not been proven against `Maze` specifically — no citation exists of `Astar`/`load_registered_solver("Astar")` being run on `Maze`. Below L4, ticket below.

**MAZE-1: Add a real drift-check target for `DEFAULT_MAZE` fidelity**
- File(s): `src/autofde_lab/hub/domain/maze/maze.py` (the hardcoded `DEFAULT_MAZE` ASCII string, lines 26-48), new `tests/domains/python/test_maze_fidelity_chicago.py`
- Problem: `DEFAULT_MAZE` is a hand-authored ASCII art string with no cited upstream/vendored source (unlike `azuregoat_privesc`/`terragoat`, which transcribe a real vendored artifact). There is nothing to check "fidelity" against today — L4 requires an automated check against a real external source, not a one-time hand transcription.
- Definition of Done: Either (a) cite and vendor a real external maze-generation source (e.g. a fixed-seed maze generator or a named published maze corpus) under `vendor/`, and add `test_maze_fidelity_chicago.py` asserting `Maze(DEFAULT_MAZE)._maze` byte-for-byte matches a fresh parse of the vendored file every run; or (b) if no real external source exists, downgrade `DEFAULT_MAZE` explicitly to "synthetic fixture, not modeling an external domain" in the module docstring and standing tag (this makes Domain fidelity N/A-at-L4-honestly rather than falsely claimed) — pick (a) if this domain is meant to model any real published maze env (e.g. `gymnasium`'s `FrozenLake`/`maze-navigation` corpora), otherwise (b). `pytest tests/domains/python/test_maze_fidelity_chicago.py -v` passes with a real diff-based assertion, not a vacuous `assert True`.
- Estimate: M (no existing test infra for this domain, need to establish the drift pattern from scratch; smaller if (b) is chosen — then it's S, a docstring/status edit only).

**MAZE-2: Build a real `gymact_bridge.py` with typed refusal for `Maze`**
- File(s): new `src/autofde_lab/hub/domain/maze/gymact_bridge.py`, modeled on `src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py` (209 lines, real pattern: `Capability`/`Consequence.DO`, plan-cursor + `get_applicable_actions` double-check, `ActuationRefused` on mismatch)
- Problem: `Maze`/`D(..., UnrestrictedActions, ...)` currently exposes `_get_next_state`/`_get_transition_value` directly with zero actuation-authority gating — any action is silently applied via `_get_next_state`'s fallback-to-`memory` behavior (an invalid move is silently absorbed as a no-op cost-2 penalty, never refused). There is no `Capability`/precondition/plan-order gate anywhere in this domain.
- Definition of Done: `gymact_bridge.py` exposes each of the 4 `Action` values as a `gymact.models.Capability` (`Consequence.DO`), `actuate()` raises `ActuationRefused` when the requested action is not the real solved-plan's next step from current state (mirroring `azuregoat_privesc`'s cursor+precondition double-check). A real sabotage test (new `tests/ecosystem/test_gymact_maze_bridge_chicago.py`, modeled on `test_gymact_terragoat_bridge_chicago.py`) asserts: (1) an out-of-plan-order but structurally-valid move raises `ActuationRefused`; (2) the correct next-step move succeeds and changes real state. `pytest tests/ecosystem/test_gymact_maze_bridge_chicago.py -v` green, zero mocks (`grep -rn "unittest.mock\|Mock(\|patch(" tests/ecosystem/test_gymact_maze_bridge_chicago.py` → empty.
- Estimate: L (zero existing bridge file; needs a real solver run to derive the reference plan, matching `azuregoat_privesc`'s `materialize()` pattern of calling `Astar.solve()` for real).

**MAZE-3: Independent verification of goal-reached state**
- File(s): `src/autofde_lab/hub/domain/maze/gymact_bridge.py` (new, from MAZE-2)'s `verify()` method
- Problem: No `verify()` exists at all today. Domain fidelity to the "verification independence" bar (re-derive from a source other than the same in-process state `actuate()` wrote) requires an independent re-derivation — e.g. re-parsing `DEFAULT_MAZE`'s goal cell (`x`) fresh from the string and comparing against the *returned* observation, not trusting `self._goal` cached at `__init__`.
- Definition of Done: `verify()` re-parses `maze_str` fresh (not reading `self._goal`) to locate the `x` goal cell, and compares that fresh parse against the actuate-returned state. A sabotage test corrupts `self._goal` in-memory post-actuation and confirms `verify()` still returns the correct real answer (proving it doesn't trust the mutated in-process cache). `pytest tests/ecosystem/test_gymact_maze_bridge_chicago.py::test_verify_independent_of_cached_goal -v` passes.
- Estimate: M (depends on MAZE-2 existing first; the re-parse logic itself is small, but the sabotage test needs real state mutation).

**MAZE-4: Real OCEL 2.0 evidence log from a live episode**
- File(s): new `docs/evidence/maze/episode.ocel.json`, new `scripts/produce_maze_episode.py` (or similar, matching `docs/papers/evidence/terraform-plan/terragoat-alicloud-episode.ocel.json`'s pattern and whatever script produced it)
- Problem: Zero OCEL evidence exists for `maze` anywhere in `docs/evidence/` or `docs/papers/evidence/`.
- Definition of Done: A committed, schema-valid OCEL 2.0 JSON log at `docs/evidence/maze/episode.ocel.json` recording a real `materialize()->act()->verify()->teardown()` episode (from MAZE-2's bridge), produced by a re-runnable script committed alongside it. `python scripts/produce_maze_episode.py` regenerates byte-identical (or hash-checked) output; a schema-validation test (e.g. `jsonschema` against the OCEL 2.0 spec, or reuse whatever validator `terragoat-alicloud-episode.ocel.json` was checked with) passes.
- Estimate: M (depends on MAZE-2's bridge existing; OCEL emission plumbing likely reusable from `terragoat`'s pattern).

**MAZE-5: Test coverage from zero**
- File(s): new `tests/domains/python/test_maze_domain_chicago.py`
- Problem: No test file exists anywhere for `maze` (confirmed via `find`/`grep` above returning nothing under `tests/`).
- Definition of Done: Real, mock-free tests instantiating `Maze()` directly and asserting on real returned state: `_get_next_state` blocked-by-wall behavior, `_get_transition_value` cost=2 on wall-hit vs cost=1 on valid move, `_is_terminal` true only at real goal cell, full solve-to-goal via `Astar` (`autofde_lab.utils.load_registered_solver("Astar")`) reaching a real terminal state. `grep -rn "unittest.mock\|Mock(\|patch(\|monkeypatch" tests/domains/python/test_maze_domain_chicago.py` → empty; `pytest tests/domains/python/test_maze_domain_chicago.py -v` all green.
- Estimate: M (straightforward Chicago-style tests against a real, already-simple domain; no new production code needed, just tests).

**MAZE-6: Standing honesty tag**
- File(s): `src/autofde_lab/hub/domain/maze/maze.py` module docstring (top of file), `src/autofde_lab/hub/domain/maze/__init__.py`, `docs/STATUS.md`
- Problem: No ALIVE/PARTIAL_ALIVE/BLOCKED/SIMULATED tag exists anywhere in this module or in `docs/STATUS.md` for `maze`.
- Definition of Done: A module-level docstring line, e.g. `"""Standing: PARTIAL_ALIVE — real domain/solver integration, no gymact actuation bridge yet (see MAZE-2)."""`, added and cross-referenced by exact string in a new `docs/STATUS.md` entry (matching the file's own stated convention: "Where this sheet and the code disagree, the code is the witness"). A grep (`grep -n "Standing:" src/autofde_lab/hub/domain/maze/maze.py`) returns the real tag, and it matches `docs/STATUS.md`'s entry for `maze` verbatim.
- Estimate: S (once MAZE-2 through MAZE-5 land, since the honest tag depends on their real state — filing this ticket now but its DoD is only truthfully closeable after the others, or immediately as SIMULATED/PARTIAL_ALIVE if filed today).

## simple_grid_world (`src/autofde_lab/hub/domain/simple_grid_world/simple_grid_world.py`)

Current source: `SimpleGridWorld(D)`, 90-line file, no `Renderable` mixin (unlike `maze`), no `gymact_bridge.py`, no test file, `_get_next_state` clamps to grid bounds (never returns invalid state — no wall model at all), no OCEL, no standing tag.

**SGW-1: Domain fidelity — name and cite the real environment being modeled**
- File(s): `src/autofde_lab/hub/domain/simple_grid_world/simple_grid_world.py` module docstring, new `tests/domains/python/test_simple_grid_world_fidelity_chicago.py`
- Problem: `SimpleGridWorld` has no docstring at all describing what real environment (if any) it models — it's a bare `num_cols x num_rows` clamped grid with a fixed corner goal. There's no cited external source to drift-check against, same gap as `MAZE-1`.
- Definition of Done: Either (a) cite a real external reference this is meant to reproduce (e.g. a specific `gymnasium`/OpenAI Gym `GridWorld` env or a named textbook MDP), vendor it, and add a real byte/behavior-diff test against it; or (b) explicitly document in the module docstring that this is a synthetic minimal-MDP fixture with no external referent, and mark Domain fidelity honestly as N/A rather than claim L4. `pytest tests/domains/python/test_simple_grid_world_fidelity_chicago.py -v` passes with a real assertion (not `assert True`).
- Estimate: S–M (smaller than MAZE-1 since there's less parsing logic to check; S if choosing (b), M if a real reference is vendored).

**SGW-2: Build a real `gymact_bridge.py` with typed refusal**
- File(s): new `src/autofde_lab/hub/domain/simple_grid_world/gymact_bridge.py`, modeled on `azuregoat_privesc/gymact_bridge.py`
- Problem: No bridge file exists. `_get_next_state` silently clamps out-of-bounds moves to the boundary (no wall/precondition concept at all — every action is always "applicable"), so there is no natural precondition gate to build actuation authority on; the ticket must add an explicit plan-order gate since the domain itself has no invalid-action concept.
- Definition of Done: `gymact_bridge.py` exposes the 4 `Action` values as `Capability(Consequence.DO)`, `actuate()` raises `ActuationRefused` when the action is not the current step of a real solved plan (plan-cursor check only, since there's no precondition check to double against — document this explicitly as a narrower gate than `azuregoat_privesc`'s double-check, given the domain's own unrestricted-action nature). New `tests/ecosystem/test_gymact_simple_grid_world_bridge_chicago.py` sabotage-tests an out-of-order move raising `ActuationRefused` and the correct next move succeeding with real state change. `pytest tests/ecosystem/test_gymact_simple_grid_world_bridge_chicago.py -v` green, zero mocks confirmed by grep.
- Estimate: L (zero existing bridge; same solver-run requirement as MAZE-2, plus the domain's own lack of a precondition concept means the refusal semantics need to be reasoned through from scratch, not just copied).

**SGW-3: Independent verification of goal-reached state**
- File(s): `gymact_bridge.py` (from SGW-2)'s `verify()`
- Problem: No `verify()` exists. The goal `State(x=num_cols-1, y=num_rows-1)` is a simple formula (not parsed from a string like `maze`), so "verification independence" here means re-deriving the goal from `self.num_cols`/`self.num_rows` constructor args fresh at verify-time, not from any cached `_get_goals_()` call result, plus reading the actuate-returned state rather than any in-process cursor variable.
- Definition of Done: `verify()` recomputes `(num_cols-1, num_rows-1)` independently and compares to the real observation returned by the last `actuate()` call (not a cached field). Sabotage test corrupts an in-process cached goal attribute post-actuation and confirms `verify()` is unaffected. `pytest .../test_verify_independent_of_cached_state -v` passes.
- Estimate: S–M (simpler than MAZE-3 since the goal is a formula, not a parsed artifact — S once SGW-2 lands).

**SGW-4: Real OCEL 2.0 evidence log**
- File(s): new `docs/evidence/simple_grid_world/episode.ocel.json`, new `scripts/produce_simple_grid_world_episode.py`
- Problem: Zero OCEL evidence exists.
- Definition of Done: Same shape as MAZE-4 — committed, schema-valid OCEL 2.0 log from a real `materialize->act->verify->teardown` run of SGW-2's bridge, regenerable via a committed script. `python scripts/produce_simple_grid_world_episode.py` re-runnable; schema validation passes.
- Estimate: M (depends on SGW-2; likely near-identical plumbing to MAZE-4 once one of the two is built — build MAZE-4 first and this becomes S by reuse).

**SGW-5: Test coverage from zero**
- File(s): new `tests/domains/python/test_simple_grid_world_domain_chicago.py`
- Problem: No test file exists anywhere for `simple_grid_world`.
- Definition of Done: Real Chicago-style tests: boundary-clamping behavior at all 4 edges (`_get_next_state` at `x=0`/`y=0`/`x=num_cols-1`/`y=num_rows-1`), transition cost=1 for valid moves (note: cost=2 "wall hit" branch is dead code in this domain since clamping means `next_state == memory` only at boundaries, which should be asserted explicitly as a real finding), `_is_terminal` true only at the real goal corner, and a full solve-to-goal via a real registered solver (`Astar` or `simple_greedy`) reaching a real terminal state for a non-trivial `num_cols/num_rows`. `grep -rn "unittest.mock\|Mock(\|patch(\|monkeypatch"` on the new file → empty; `pytest -v` all green.
- Estimate: M (same shape as MAZE-5; also surfaces the dead-code cost=2 branch as a real finding worth flagging in the PR, not silently ignored).

**SGW-6: Standing honesty tag**
- File(s): `src/autofde_lab/hub/domain/simple_grid_world/simple_grid_world.py` docstring, `docs/STATUS.md`
- Problem: No standing tag exists.
- Definition of Done: Same shape as MAZE-6 — a module-level `Standing:` docstring line cross-referenced verbatim in `docs/STATUS.md`.
- Estimate: S.

---

**Already-meets-L4 dimensions**: none for either domain — both `maze` and `simple_grid_world` score 1-2 on every one of the 7 dimensions per the prompt's grounded audit, so all 7 required a ticket for both domains (Solver/planning integration=2 still ticketed above since a registered-solver run has not been proven against either domain specifically in committed evidence, only inferred from the sibling `azuregoat_privesc` pattern).

**Infrastructure flag**: neither domain requires live external infra to reach L4 — both are pure in-process MDPs (no cluster/cloud dependency, unlike e.g. `terragoat`/`azuregoat_privesc`, which model real cloud attack surfaces). The achievable L4 bar for both is fully local: real vendored-source drift check (or an honest synthetic-fixture downgrade), a real `gymact_bridge.py` with plan-cursor refusal, fresh-re-derivation `verify()`, a local OCEL log from a real local episode, and real pytest coverage — all buildable without any live infra. No proxy-ticket downgrade needed.

Good — real reference patterns exist (`docs/papers/evidence/terraform-plan/terragoat-alicloud-episode.ocel.json`, `gym_procedure/standalone_verifier.py`, `azuregoat_privesc/gymact_bridge.py`). Now producing the tickets.

## plado

Real source: `src/autofde_lab/hub/domain/plado/plado.py` (1228 lines, `BasePladoDomain`/`PladoPddlDomain`/`PladoPPddlDomain`), `src/autofde_lab/hub/domain/plado/llg_encoder.py` (1231 lines), tests in `tests/domains/python/test_plado_domain.py`. This is a scikit-decide-style in-process simulation domain wrapping the vendored `plado` PDDL/PPDDL semantics library (`plado.semantics.task.Task`, `applicable_actions_generator`, `successor_generator`) — no `gymact_bridge.py`, no `verify()`, no OCEL emission anywhere in the module.

- Domain fidelity=4 — already meets L4.
- Actuation authority=4 — already meets L4.
- Test coverage=4 — already meets L4.
- **Verification independence=2**
  - **Title:** AFDE-PLADO-1: Independent goal re-derivation for plado episodes
  - **Files:** new `src/autofde_lab/hub/domain/plado/gymact_bridge.py`; reference pattern `src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py`'s `verify()`; use `src/autofde_lab/hub/domain/gym_procedure/standalone_verifier.py` as the independence contract (observer identity must differ from actuator).
  - **DoD:** A `verify()` that re-parses the PDDL/PPDDL problem file fresh (a second `plado.parser.parse_and_normalize` call in a distinct process or at minimum a distinct `Task`/`GoalChecker` instance never touched by the in-process `SuccessorGenerator` that ran the plan) and checks goal-atom membership against that independent parse, not against the same `BasePladoDomain` instance's mutated state. `pytest tests/domains/python/test_plado_domain.py::test_verify_independent_reparse` (new test) passes and asserts the verifier's `Task`/`GoalChecker` object identity is distinct from the actor's.
  - **Effort:** M (plado's semantics objects are cheap to re-instantiate from the same PDDL files already on disk under `tests/domains/python/pddl_domains/`; no new external dependency, but requires threading a domain/problem file path through to a new bridge module).
- **OCEL evidence=1**
  - **Title:** AFDE-PLADO-2: Real OCEL 2.0 episode log for a materialize→solve→act→verify→teardown run
  - **Files:** new `src/autofde_lab/hub/domain/plado/gymact_bridge.py` (emit events), new `scripts/` runner script (pattern: whatever produced `docs/papers/evidence/terraform-plan/terragoat-alicloud-episode.ocel.json`), new `docs/papers/evidence/plado/blocksworld-episode.ocel.json`.
  - **DoD:** A committed, schema-valid OCEL 2.0 JSON log (validated against the same schema/validator terragoat's episode file passes) at `docs/papers/evidence/plado/blocksworld-episode.ocel.json`, produced by a real run of `tests/domains/python/pddl_domains/blocks/domain.pddl` + `probBLOCKS-3-0.pddl` through solve (e.g. `Astar`) → actuate each step → verify → teardown, wired to a re-runnable script (e.g. `python scripts/run_plado_episode.py`) that anyone can execute to regenerate the same log shape.
  - **Effort:** L (no OCEL emission exists anywhere in plado today; requires both the bridge from the ticket above and new event-schema wiring).
- **Solver/planning integration=3**
  - **Title:** AFDE-PLADO-3: Registered-solver verified plan, not just a unit-checkpoint run
  - **Files:** `src/autofde_lab/hub/domain/plado/plado.py`, `tests/domains/python/test_plado_domain.py` (already imports `Astar`, `RayRLlib`, `StableBaseline` — confirms solvers run against `PladoPddlDomain`, but no test asserts a verified/replayed plan reaches the goal independently).
  - **DoD:** New test `test_plado_domain.py::test_astar_plan_reaches_goal_independently_verified` — runs `Astar` to completion on `blocksworld_domain_problem_paths`, replays the resulting action sequence through a *fresh* `PladoPddlDomain` instance (not the solver's own), and asserts goal satisfaction via the independent `GoalChecker` from the verification-independence ticket above, not via the solver's internal termination flag.
  - **Effort:** M (Astar and the domain already exist and are already exercised in tests; this is composing existing pieces plus the new verify path, not new solver integration).
- **Standing honesty=2**
  - **Title:** AFDE-PLADO-4: Module-level ALIVE/PARTIAL_ALIVE/BLOCKED tag matching STATUS.md
  - **Files:** `src/autofde_lab/hub/domain/plado/plado.py` (module docstring, currently has no standing tag — contrast with `cloudgoat_iam_privesc.py`'s explicit "Everything here is simulation" docstring), `docs/STATUS.md` (already references "plado/PDDL IR unimplemented branches (~15 `NotImplementedError` dispatch gaps)" at line 507 and "Skipped tests gated on unavailable dependencies (... `plado`...)" at line 520 — the module itself states none of this).
  - **DoD:** Module docstring in `plado.py` states an explicit standing tag (`PARTIAL_ALIVE` given the ~15 `NotImplementedError` gaps STATUS.md already documents) with a one-line reason and cross-reference to `docs/STATUS.md`'s existing entries; `grep -c "PARTIAL_ALIVE\|ALIVE\|BLOCKED\|SIMULATED" src/autofde_lab/hub/domain/plado/plado.py` ≥ 1.
  - **Effort:** S (docstring-only change; the honest content — 15 `NotImplementedError` gaps — is already documented in STATUS.md, just not propagated into the module).

## chatman_clean_session

Real source: `src/autofde_lab/hub/domain/chatman_clean_session/{domain.py,execution.py,model.py}` (1001 lines total). Genuinely has a `Broker` protocol with `actuate(intent) -> BrokerReceipt`, `_admit_broker_standing`, and `ActuationRefused` (execution.py:27-45) — real typed refusal machinery, matching the already-high Actuation authority=4 and Test coverage=5 scores. No `verify()`/independent re-derivation function exists in any of the three files, and no OCEL emission.

- Actuation authority=4 — already meets L4.
- Test coverage=5 — already meets L4.
- **Domain fidelity=2**
  - **Title:** AFDE-CCS-1: Automated drift check against the real vendored session/broker source
  - **Files:** `src/autofde_lab/hub/domain/chatman_clean_session/model.py` (`ActionKind`, `Stage`, `RouteSpec`, `RouteOutcome`), `domain.py`, `execution.py`. Need to identify the real upstream "Chatman clean session" source this models (not found vendored under `vendor/` in this repo per the earlier `find`) — this is the concrete blocker: unlike plado (vendors `plado` as an installed package) or terragoat (vendors real Terraform source), `chatman_clean_session` appears to be a hand-authored model with no committed upstream reference to diff against.
  - **DoD:** Either (a) a real vendored source is identified and a script (pattern: `l5-pack-method` skill's "vendor a real implementation, transcribe verbatim, prove fidelity with the reference's own tests") diffs `model.py`'s enums/dataclasses against it on every `just test`/CI run, or (b) if no such external reference exists, the module docstring is corrected to state explicitly that this is an original synthesis, not a transcription of a real system — which caps this dimension's achievable score below L4 by construction until a real reference is named, and the ticket should say so rather than silently claiming L4.
  - **Effort:** L (requires first locating or confirming absence of a reference implementation — an investigation task, not just a patch).
- **Verification independence=2**
  - **Title:** AFDE-CCS-2: Independent verify() distinct from the broker's own receipt
  - **Files:** `src/autofde_lab/hub/domain/chatman_clean_session/execution.py` (currently only `_invoke_broker`/`_admit_broker_standing`, which *admit* the broker's self-reported `BrokerReceipt.standing` — this is the actuator's own claim, not an independent re-derivation), `model.py` (`BrokerReceipt`, `ExecutionReceipt`).
  - **DoD:** A `verify()` function that re-derives session/route outcome from a source the `Broker.actuate()` call did not itself write — e.g., re-reading `RouteEvidence`/`ExecutionReceipt` state from a persisted log file or a second, independent broker call — matching `gym_procedure/standalone_verifier.py`'s contract (`postcondition->independent`: "was the observer identity distinct from the actuator?"). New test asserting the verifier object/process identity differs from `_invoke_broker`'s caller.
  - **Effort:** M (the `BrokerReceipt`/`ActuationIntent` types already exist; needs a genuinely separate read path, not a new type).
- **OCEL evidence=1**
  - **Title:** AFDE-CCS-3: Real OCEL 2.0 log for a chatman_clean_session episode
  - **Files:** new script under `scripts/`, new `docs/papers/evidence/chatman-clean-session/episode.ocel.json`; existing `tests/ecosystem/test_chatman_chain_chicago.py` and `tests/test_chatman_clean_session_interop.py` show the domain is already exercised end-to-end in tests — that run should be the source of the OCEL emission, not a new synthetic scenario.
  - **DoD:** Committed, schema-valid OCEL 2.0 JSON log produced by running the existing Chicago-style chain test's scenario through actual `actuate()`/broker calls with event emission added to `execution.py`, referenced by a re-runnable script.
  - **Effort:** L (zero OCEL emission exists in this module currently; needs both instrumentation and log-schema work).
- **Solver/planning integration=1**
  - **Title:** AFDE-CCS-4: Register a solver against `ChatmanCleanSessionDomain` and produce a verified plan
  - **Files:** `src/autofde_lab/hub/domain/chatman_clean_session/domain.py` (`D(DeterministicPlanningDomain)` — already a proper skdecide-style planning domain with `T_state`/`T_event`/`T_value`), no solver currently registered/tested against it (contrast with plado's `Astar`/`RayRLlib`/`StableBaseline` usage in its test file).
  - **DoD:** New test (e.g. `tests/domains/python/test_chatman_clean_session_domain.py`, currently does not exist) that runs a real registered solver (e.g. `Astar`, matching the azuregoat_privesc pattern of `utils.load_registered_solver("Astar")`) to completion on a `ChatmanCleanSessionDomain` instance and asserts the resulting plan is independently verified per the AFDE-CCS-2 ticket above.
  - **Effort:** L (no solver wiring exists at all for this domain today — new test file, new solver-domain compatibility work, likely needs `get_applicable_actions`/space adjustments to satisfy solver requirements).
- **Standing honesty=4** — already meets L4 (execution.py already has explicit `validate_standing`, `PARTIAL_ALIVE`/`UNKNOWN`/`REFUSED:AUTHORITY_DENIED` handling with documented reasoning at `_admit_broker_standing`).

## rddl

Real source: `src/autofde_lab/hub/domain/rddl/rddl.py` (179 lines), `RDDLDomain(D)` wraps `pyRDDLGym`'s real `RDDLEnv`/`RDDLSimulator` (a genuine external simulation library, not hand-rolled). Tests: `tests/domains/python/test_pyrddlgym_domains.py`, `tests/solvers/python/test_pyrddlgym_solvers.py`. No `verify()`, no OCEL, no standing tag in the module.

- Domain fidelity=4 — already meets L4.
- Solver/planning integration=4 — already meets L4.
- Test coverage=4 — already meets L4.
- **Actuation authority=3**
  - **Title:** AFDE-RDDL-1: Typed refusal + sabotage test for RDDL action admission
  - **Files:** `src/autofde_lab/hub/domain/rddl/rddl.py` (currently `enforce_action_constraints=True` is passed straight to `pyRDDLGym.make` — constraint enforcement is delegated entirely to the vendored simulator with no typed refusal surface of this repo's own; contrast with `chatman_clean_session/execution.py`'s `ActuationRefused`).
  - **DoD:** A new `ActuationRefused`-style typed exception raised by this module (not `pyRDDLGym`'s own) when an action violates a precondition this repo's code checks explicitly, plus a real sabotage test in `tests/domains/python/test_pyrddlgym_domains.py` that submits a known-invalid action and asserts the typed refusal (not a bare `pyRDDLGym` internal error propagating uncaught).
  - **Effort:** M (requires understanding `pyRDDLGym`'s existing constraint-violation signaling well enough to wrap it, not replace it).
- **Verification independence=1**
  - **Title:** AFDE-RDDL-2: Independent goal/reward re-derivation from a fresh RDDLEnv
  - **Files:** `src/autofde_lab/hub/domain/rddl/rddl.py`; new `src/autofde_lab/hub/domain/rddl/gymact_bridge.py` following the azuregoat_privesc `verify()` pattern.
  - **DoD:** A `verify()` that instantiates a second, independent `RDDLEnv`/`RDDLSimulator` from the same `rddl_domain`/`rddl_instance` files and replays the recorded action sequence to confirm the same terminal reward/goal state, rather than trusting the acting `RDDLDomain` instance's own internal state. New test in `test_pyrddlgym_domains.py` asserting the verifying env object is distinct from the acting one.
  - **Effort:** M (RDDLEnv construction is already exercised in tests; the new work is the second-instance replay-and-compare logic).
- **OCEL evidence=1**
  - **Title:** AFDE-RDDL-3: Real OCEL 2.0 episode log for an RDDL materialize→act→verify run
  - **Files:** new `docs/papers/evidence/rddl/episode.ocel.json`, new runner script; note `rddl_movies/test-sb3/*.gif` in the repo already prove real solver rollouts happen (StableBaselines3 movies exist) — the OCEL ticket should instrument that existing rollout path, not invent a new scenario.
  - **DoD:** Committed schema-valid OCEL 2.0 log from a real run (e.g. the same RDDL domain/instance already used to produce `rddl_movies/test-sb3/*.gif`), wired to a re-runnable script.
  - **Effort:** L (zero OCEL emission exists; instrumentation is new).
- **Standing honesty=2**
  - **Title:** AFDE-RDDL-4: Module-level standing tag
  - **Files:** `src/autofde_lab/hub/domain/rddl/rddl.py` module/class docstring (currently none), cross-referenced against `docs/STATUS.md` (no explicit rddl entry found in the grep above — this itself is a gap: STATUS.md should carry an rddl line if the module claims a standing).
  - **DoD:** Module docstring states an explicit `ALIVE` (justified: real `pyRDDLGym` wrapping, real solver tests) or `PARTIAL_ALIVE` (if the actuation-refusal gap from AFDE-RDDL-1 is still open) tag, and `docs/STATUS.md` gets a matching one-line entry so the two are consistent, per the L4 bar's "consistent with docs/STATUS.md" requirement.
  - **Effort:** S.

## cloudgoat_iam_privesc

Real source: `src/autofde_lab/hub/domain/cloudgoat_iam_privesc/cloudgoat_iam_privesc.py` (199 lines). The module's own docstring is unusually explicit already: *"Everything here is simulation. The domain touches no AWS API, no Terraform state, and no real IAM/EC2 resource... it does not actuate, admit, broker, or issue receipts."* This grounds the given scores directly — Standing honesty=5 and Test coverage=5 are earned by that same candor plus `vendor/gyms/cloudgoat/tests/` real coverage.

- Test coverage=5 — already meets L4.
- Standing honesty=5 — already meets L4.
- **Domain fidelity=2**
  - **Title:** AFDE-CG-1: Automated drift check against `vendor/gyms/cloudgoat`'s real scenario README/cheat sheet
  - **Files:** `src/autofde_lab/hub/domain/cloudgoat_iam_privesc/cloudgoat_iam_privesc.py` (the six `Action` preconditions are hand-transcribed from `vendor/gyms/cloudgoat/cloudgoat/scenarios/aws/iam_privesc_by_attachment/README.md` and `cheat_sheet_kerrigan.md`, cited by name in the docstring but never diffed against), new `scripts/check_cloudgoat_drift.py`.
  - **DoD:** A script that parses the real vendored `README.md`'s "Walkthrough" section and `cheat_sheet_kerrigan.md`'s ordered `aws` CLI calls, and asserts the six `Action` enum members / precondition graph in `cloudgoat_iam_privesc.py` still match that ordering — run in CI/`just pre-commit`, failing loudly on drift instead of relying on the current one-time hand transcription.
  - **Effort:** M (the source files already exist and are already cited verbatim in the docstring; this is parsing markdown structure, not new domain research).
- **Actuation authority=1**
  - **Title:** AFDE-CG-2 [INFRA-BLOCKED]: Closest achievable proxy — typed BRCE refusal wrapper over the simulated plan, real AWS actuation out of reach
  - **Files:** new `src/autofde_lab/hub/domain/cloudgoat_iam_privesc/gymact_bridge.py`.
  - **Note on infra ceiling:** True L4 actuation authority for this domain requires a real, live CloudGoat AWS deployment (`terraform apply` against an actual AWS account per `vendor/gyms/cloudgoat`'s own setup) to issue real `aws` CLI calls and real `PermissionError`/API-denial refusals — this repo has no such live account wired in, and the module's own docstring says so explicitly ("touches no AWS API"). That external-system verification stays out of reach without live infra; do not silently downgrade this ticket to pretend the simulated version is L4.
  - **DoD (proxy, not true L4):** A `gymact_bridge.py` with `Capability(consequence=Consequence.DO)` per `Action` and a real `ActuationRefused` raised when a capability is requested out of the six-step precondition order this repo's own `State`/precondition logic defines (matching the `azuregoat_privesc` pattern's *simulated*-precondition refusal, not real AWS denial) — a real sabotage test asserting refusal on out-of-order action submission. This closes the achievable gap (typed refusal over the simulated plan) without claiming AWS-level authority.
  - **Effort:** M for the proxy; L (and infra-dependent, not purely engineering effort) for true AWS-backed actuation.
- **Verification independence=1**
  - **Title:** AFDE-CG-3 [INFRA-BLOCKED]: Closest achievable proxy — independent re-check of the simulated goal state, not real AWS state
  - **Files:** new `gymact_bridge.py` `verify()`.
  - **Note on infra ceiling:** True independent verification (querying real AWS `describe-instances` to confirm `cg-super-critical-security-server` was actually terminated) requires the same live AWS account as AFDE-CG-2 and is out of reach here.
  - **DoD (proxy):** `verify()` re-derives goal satisfaction (`terminated` state) from a freshly-constructed `State`/precondition replay distinct from the actor's own `State` tuple instance (this domain's `State` is already an immutable `NamedTuple`, so the proxy is cheap: replay the recorded action sequence into a brand-new `State()` and compare), matching `gym_procedure/standalone_verifier.py`'s observer-distinct-from-actuator contract at the simulation level.
  - **Effort:** S (the `State` NamedTuple is already immutable and hashable — this is a small, real re-derivation, not infra work).
- **OCEL evidence=1**
  - **Title:** AFDE-CG-4: Real OCEL 2.0 log for a simulated cloudgoat episode
  - **Files:** new `docs/papers/evidence/cloudgoat-iam-privesc/episode.ocel.json`, new runner script.
  - **DoD:** Committed schema-valid OCEL 2.0 log from a real run of the six-step plan through the (post-AFDE-CG-2) `gymact_bridge.py`, explicitly labeled in the log/docstring as a simulated-domain episode (consistent with the module's own honesty about not touching real AWS), wired to a re-runnable script.
  - **Effort:** L (zero OCEL emission exists; requires AFDE-CG-2's bridge first).
- **Solver/planning integration=3**
  - **Title:** AFDE-CG-5: Registered-solver verified plan for the six-step chain
  - **Files:** `cloudgoat_iam_privesc.py` (`DeterministicPlanningDomain` base — already solver-compatible in principle), new test (no `tests/domains/python/test_cloudgoat_iam_privesc_unit.py` solver assertion currently — confirm via that file's actual content before starting, it exists but its name suggests unit-level, not solver-level, coverage).
  - **DoD:** New test running a real registered solver (e.g. `Astar`) to completion on `CloudgoatIamPrivesc`, replaying and independently verifying (via AFDE-CG-3's proxy verify) that the six-step goal is reached, not just a single-action unit check.
  - **Effort:** M (domain is already `DeterministicPlanningDomain`-shaped; six discrete states makes solving trivial — most effort is wiring the independent-verify step from AFDE-CG-3).

I have enough grounding now. Writing the tickets.

---

## gym (`src/autofde_lab/hub/domain/gym/gym.py`, `tests/domains/test_gym.py`)

Real source confirms: `GymDomain`/`GymPlanningDomain`/`GymDiscreteActionDomain` is scikit-decide's vendored generic wrapper over any `gymnasium.Env` — no capability model, no OCEL, no independent verifier; `test_gym.py` (360 lines) is comprehensive upstream-derived space-discretization coverage, confirming Test coverage=5 already meets L4 (skip).

- **Test coverage = 5: already meets L4.** No ticket.

- **AFDL-GYM-1 — Actuation authority: no capability/precondition gating on `_state_step`**
  Files: `src/autofde_lab/hub/domain/gym/gym.py` (`GymDomain._state_step`, L88-101), `src/autofde_lab/fabric/gymact_capability_gate.py` (existing gate pattern to reuse).
  DoD: `GymDomain._state_step` calls `gymact_capability_gate` (or an equivalent typed precondition check) before delegating to `self._gym_env.step(action)`; a new Chicago test (real `gym.make(...)` env, no mock) asserts a plan-order/precondition violation raises a typed refusal exception, not a silent no-op or a bare gym exception. `pytest tests/domains/test_gym.py -k refusal` passes.
  Effort: **M** — the wrapper class exists and is stable; adding a gate call plus one sabotage test is contained, but wiring a real capability schema for arbitrary gym envs (action space is per-env, not fixed) needs design work.

- **AFDL-GYM-2 — Verification independence: `_state_step` returns are trusted, never re-derived**
  Files: `src/autofde_lab/hub/domain/gym/gym.py`, new `src/autofde_lab/hub/domain/gym/gym_verifier.py` (does not exist).
  DoD: new module that, given a serialized episode (state/action/obs trace written to disk), re-derives the terminal state independently (e.g. replays the recorded action sequence in a **fresh** `gym.make()` instance in a **separate subprocess**, not the in-process `GymDomain` that produced the trace) and diffs against the claimed final observation. Modeled on `standalone_verifier.py`'s import-discipline pattern (`FORBIDDEN_RUNTIME_MODULES` check via `sys.modules`). `pytest tests/domains/test_gym_verifier.py::test_independent_replay_matches` passes against a real `MountainCarContinuous-v0` episode.
  Effort: **M** — gym environments are typically deterministic-replayable given seed+actions, so a subprocess-replay verifier is buildable without new infra.

- **AFDL-GYM-3 — OCEL evidence: zero OCEL emission anywhere in this file**
  Files: `src/autofde_lab/hub/domain/gym/gym.py`, new `docs/evidence/gym/episode.ocel.json`, new `scripts/run_gym_episode_evidence.py`.
  DoD: a runnable script (`python scripts/run_gym_episode_evidence.py`) that materializes a real gym env, runs `reset()`→`step()`×N→`close()`, and emits a schema-valid OCEL 2.0 log (object types: `episode`, `action`; event types: `reset`, `step`, `close`) to `docs/evidence/gym/episode.ocel.json`, committed. Validate with the same OCEL 2.0 JSON-schema check used by `level4_ocel.py`/`level4_evidence.py`.
  Effort: **M** — no existing OCEL hook on this wrapper; needs a new emission path, but the event structure is simple (3 event types, single trace).

- **AFDL-GYM-4 — Solver/planning integration: `test_gymdomain` uses CGP as a 2-iteration smoke check, not a verified plan**
  Files: `tests/domains/test_gym.py` (`test_gymdomain`, L76-87), `src/autofde_lab/hub/solver/cgp/` (existing solver).
  DoD: a new test that runs a registered solver (CGP or another hub solver) to convergence on a small discrete gym env, extracts the resulting plan, and asserts the plan is *verified* against `AFDL-GYM-2`'s independent verifier (goal reached, no precondition violations) rather than just executing 2 iterations for smoke-test purposes. `pytest tests/domains/test_gym.py::test_solved_plan_is_independently_verified` passes.
  Effort: **M** — depends on AFDL-GYM-2 landing first (verifier is the DoD gate); solver itself already exists and is already used in-repo.

- **AFDL-GYM-5 — Standing honesty: no module-level ALIVE/PARTIAL_ALIVE/BLOCKED/SIMULATED tag**
  Files: `src/autofde_lab/hub/domain/gym/gym.py` (module docstring, top of file), `docs/STATUS.md`.
  DoD: module docstring gets an explicit standing line, e.g. `Standing: ALIVE — real gymnasium.Env wrapper, upstream scikit-decide code, no autofde-lab capability/OCEL/verification layer yet (see AFDL-GYM-1..4)`; a `docs/STATUS.md` cross-reference line added in the same pass. Grep `grep -n "Standing:" src/autofde_lab/hub/domain/gym/gym.py` returns the line.
  Effort: **S** — pure documentation, no code change.

---

## rcpsp (`src/autofde_lab/hub/domain/rcpsp/{rcpsp_sk.py,rcpsp_sk_parser.py}`, `tests/domains/python/test_rcpsp_sk.py`)

Real source confirms: `rcpsp_sk.py` (790 lines) implements `RCPSP`/`MRCPSP`/`MSRCPSP` deterministic-planning domains over `discrete_optimization`-parsed PSPLIB files; `rcpsp_sk_parser.load_domain`/`load_multiskill_domain` do real file parsing (not fabricated); the one existing test (`test_rcpsp_sk`, 25 lines) runs two `get_next_state` calls with zero `assert` statements — it only prints, confirming Test coverage=2.

- **AFDL-RCPSP-1 — Actuation authority: no plan-order/precondition gate on task actions (currently scoring 3, not yet 4)**
  Files: `src/autofde_lab/hub/domain/rcpsp/rcpsp_sk.py` (`RCPSP`/`MRCPSP._get_applicable_actions_`/`_state_step`, need `LSP goToDefinition`/`documentSymbol` to locate exact line — not yet inspected past parser).
  DoD: `_state_step` refuses (typed exception, not silent state corruption) an action referencing a task whose predecessors (per `successors`/precedence graph already parsed from PSPLIB) are not yet complete, proven by a new sabotage test that submits an out-of-precedence-order action and asserts the typed refusal, not just wrong output.
  Effort: **S** — precedence data (`successors`) is already parsed and present on the domain object per `rcpsp_sk_parser.py`; likely just needs a guard clause plus one test.

- **AFDL-RCPSP-2 — Verification independence: no re-derivation of schedule validity from a source other than the in-process domain**
  Files: `src/autofde_lab/hub/domain/rcpsp/rcpsp_sk.py`, new `src/autofde_lab/hub/domain/rcpsp/rcpsp_verifier.py`.
  DoD: new module that takes a committed schedule (task→start-time assignment) written to disk, and independently re-checks precedence + resource-capacity constraints by re-parsing the *original* PSPLIB file directly (not importing `rcpsp_sk.py`'s in-memory model) — same import-discipline pattern as `standalone_verifier.py`. `pytest tests/domains/python/test_rcpsp_verifier.py::test_independent_schedule_check` passes on a real PSPLIB fixture (`examples/scheduling/data/rcpsp/j1201_1.sm`, already in repo).
  Effort: **M** — PSPLIB re-parsing is already solved by `discrete_optimization.rcpsp.parser`; the new module mainly needs constraint-checking logic independent of the domain class.

- **AFDL-RCPSP-3 — OCEL evidence: zero OCEL emission for schedule episodes**
  Files: `src/autofde_lab/hub/domain/rcpsp/rcpsp_sk.py`, new `docs/evidence/rcpsp/episode.ocel.json`, new `scripts/run_rcpsp_episode_evidence.py`.
  DoD: script runs `load_domain(...)` on the real `j1201_1.sm` fixture, executes a real action sequence to a terminal/goal state, and emits a schema-valid OCEL 2.0 log (object types: `task`, `resource`; event types: `schedule`, `complete`) committed at `docs/evidence/rcpsp/episode.ocel.json`.
  Effort: **M** — same shape as AFDL-GYM-3; task/resource object types are already explicit in the domain's constructor args.

- **AFDL-RCPSP-4 — Solver/planning integration: no registered solver run + verified plan on this domain in the test suite**
  Files: `tests/domains/python/test_rcpsp_sk.py`, `src/autofde_lab/hub/solver/` (identify an existing scheduling-capable solver via `LSP workspaceSymbol`).
  DoD: new test runs a real hub solver to a complete schedule on `j1201_1.sm`, then verifies the plan via AFDL-RCPSP-2's independent verifier. `pytest tests/domains/python/test_rcpsp_sk.py::test_solved_schedule_is_independently_verified` passes with real assertions (current file has none).
  Effort: **M** — depends on AFDL-RCPSP-2; solver wiring pattern likely mirrors `test_simple_greedy_gym_procedure_chicago.py`.

- **AFDL-RCPSP-5 — Test coverage: existing test has zero assertions**
  Files: `tests/domains/python/test_rcpsp_sk.py` (25 lines, all `print`, no `assert`).
  DoD: rewrite `test_rcpsp_sk` to assert real state: `state.tasks_remaining` (or equivalent field) decreases per step, `_is_terminal` becomes true only at a real goal state, applicable-actions set shrinks monotonically or matches precedence expectations. Add a second test exercising `MRCPSP`/`MSRCPSP` multi-mode paths (currently zero coverage of those two classes). `pytest tests/domains/python/test_rcpsp_sk.py -v` shows ≥3 tests, each with ≥1 real assert, zero mock/patch/monkeypatch (`grep -n "mock\|patch\|monkeypatch" tests/domains/python/test_rcpsp_sk.py` empty).
  Effort: **S** — the domain and fixture data already exist; this is a rewrite of an existing thin test, not new infrastructure.

- **AFDL-RCPSP-6 — Standing honesty: no module-level standing tag**
  Files: `src/autofde_lab/hub/domain/rcpsp/rcpsp_sk.py`, `docs/STATUS.md`.
  DoD: same shape as AFDL-GYM-5 — explicit `Standing:` line in the module docstring, cross-referenced from `docs/STATUS.md`.
  Effort: **S**.

---

## rock_paper_scissors (`src/autofde_lab/hub/domain/rock_paper_scissors/rock_paper_scissors.py`, `tests/domains/test_rock_paper_scissors.py`)

Real source confirms: this is a 105-line pure-simulation two-agent scikit-decide toy domain (reward-table lookup, no external system, no files/subprocess touched at all). Domain fidelity=2 reflects that there is no real external "rock-paper-scissors" system this is modeling fidelity *against* — it's a self-contained abstraction, so "drift check against real vendored source" (the L4 bar for fidelity) doesn't apply the same way as gym/rcpsp.

- **AFDL-RPS-1 — Domain fidelity: no automated check that the payoff table matches a canonical/vendored spec**
  Files: `src/autofde_lab/hub/domain/rock_paper_scissors/rock_paper_scissors.py` (`_state_step`, L61-75 payoff dict).
  DoD: since there is no external system this domain represents (Flag: infra-not-applicable, closest proxy below), the closest achievable L4 proxy is a property-based invariant test (zero-sum: `r1 + r2 == 0` for all 9 move pairs; antisymmetry: `payoff(a,b) == -payoff(b,a)`) that would catch any hand-edit drift in the payoff table, run in CI. `pytest tests/domains/test_rock_paper_scissors.py::test_payoff_table_is_zero_sum_and_antisymmetric` passes for all 9 combinations.
  **Flag:** true "drift against a real vendored source" does not apply — there is no upstream RPS spec to drift from; this ticket is the closest achievable proxy (structural invariant check), named explicitly rather than silently downgraded.
  Effort: **S** — the payoff table is 9 entries, fully enumerable in one test.

- **AFDL-RPS-2 — Actuation authority: `_state_step` accepts any `Move` from either player unconditionally**
  Files: `src/autofde_lab/hub/domain/rock_paper_scissors/rock_paper_scissors.py` (`_state_step`, `_get_action_space_`).
  DoD: add a precondition check that both agents' actions are members of `EnumSpace(Move)` (currently implicit/untyped-enforced only by Python's dict-key lookup, which would raise a raw `KeyError` — not a typed refusal — on an invalid action); a sabotage test submits a non-`Move` action and asserts a typed domain-level refusal exception, not a bare `KeyError` leaking from the payoff dict.
  Effort: **S** — one guard clause, one test.

- **AFDL-RPS-3 — Verification independence: no independent re-derivation of match outcome**
  Files: `src/autofde_lab/hub/domain/rock_paper_scissors/rock_paper_scissors.py`, new `src/autofde_lab/hub/domain/rock_paper_scissors/rps_verifier.py`.
  DoD: new module re-implements the payoff/termination rule from scratch (not importing `rock_paper_scissors.py`) and, given a committed move sequence written to disk, independently recomputes cumulative reward and termination; asserts match against the domain's own claimed final state. Same import-discipline pattern as `standalone_verifier.py`.
  Effort: **S** — the rule is 9 lines of logic; reimplementing independently is trivial.

- **AFDL-RPS-4 — OCEL evidence: zero OCEL emission**
  Files: `src/autofde_lab/hub/domain/rock_paper_scissors/rock_paper_scissors.py`, new `docs/evidence/rock_paper_scissors/episode.ocel.json`, new `scripts/run_rps_episode_evidence.py`.
  DoD: script runs a real `RockPaperScissors(max_moves=10)` episode to termination, emits schema-valid OCEL 2.0 (object types: `player1`, `player2`; event type: `move`), committed.
  Effort: **S** — 10-move fixed-length episode, trivial event structure.

- **AFDL-RPS-5 — Solver/planning integration: no registered solver ever run against this domain**
  Files: `tests/domains/test_rock_paper_scissors.py` (currently exists — read to confirm scope before starting), `src/autofde_lab/hub/solver/`.
  DoD: a real multi-agent solver (e.g. minimax or a hub game-theoretic solver) plays a full episode against a fixed opponent policy, plan verified via AFDL-RPS-3. Test asserts real state (cumulative reward within `[-10,10]`), not solver-call interaction.
  Effort: **M** — no multi-agent solver currently confirmed wired to this domain; may need to identify or adapt one via `LSP workspaceSymbol`.

- **AFDL-RPS-6 — Standing honesty: no module-level standing tag**
  Files: `src/autofde_lab/hub/domain/rock_paper_scissors/rock_paper_scissors.py`, `docs/STATUS.md`.
  DoD: same as AFDL-GYM-5.
  Effort: **S**.

(Test coverage=4 for RPS already meets L4 — no ticket, `tests/domains/test_rock_paper_scissors.py` exists and was not found empty in the earlier listing.)

---

## mastermind (`src/autofde_lab/hub/domain/mastermind/mastermind.py`)

Real source confirms: 142-line pure scikit-decide `GoalPOMDPDomain` toy (deterministic bulls/cows scoring, no external system). Confirmed via file search: **no test file exists for mastermind anywhere in `tests/`** — Test coverage=1 is a hard floor, needs a from-scratch test file per the task's own instruction.

- **AFDL-MM-1 — Domain fidelity: no automated check on bulls/cows scoring logic**
  Files: `src/autofde_lab/hub/domain/mastermind/mastermind.py` (`_calc_score`, L127-141).
  DoD: same proxy shape as AFDL-RPS-1 — no external Mastermind spec to drift-check against (**Flag: no live infra/reference to check against — closest proxy used**). Property test: for a known solution/guess pair with hand-computed bulls/cows, `_calc_score` matches; and invariant `bulls + cows <= n_positions` holds across randomized guesses.
  Effort: **S**.

- **AFDL-MM-2 — Actuation authority: no precondition on guess-row shape/values**
  Files: `src/autofde_lab/hub/domain/mastermind/mastermind.py` (`_get_next_state`, `_calc_score`).
  DoD: guard clause rejecting a guess `Row` whose length ≠ `n_positions` or whose values fall outside `range(n_colours)`, with a typed refusal exception; sabotage test submits a malformed guess and asserts the typed refusal (currently would silently index out-of-range or produce wrong score).
  Effort: **S**.

- **AFDL-MM-3 — Verification independence: no independent re-scoring**
  Files: `src/autofde_lab/hub/domain/mastermind/mastermind.py`, new `src/autofde_lab/hub/domain/mastermind/mastermind_verifier.py`.
  DoD: standalone re-implementation of `_calc_score` (bulls/cows) that does not import `mastermind.py`, checked against a committed guess/solution log on disk. Same import-discipline as `standalone_verifier.py`.
  Effort: **S**.

- **AFDL-MM-4 — OCEL evidence: zero OCEL emission**
  Files: `src/autofde_lab/hub/domain/mastermind/mastermind.py`, new `docs/evidence/mastermind/episode.ocel.json`, new `scripts/run_mastermind_episode_evidence.py`.
  DoD: script runs a real `MasterMind(n_colours=2, n_positions=2)` episode to a goal state via a simple exhaustive-guess policy, emits schema-valid OCEL 2.0 (object type: `solution`; event type: `guess`), committed.
  Effort: **S** — small state space (4 possible solutions at n_colours=2/n_positions=2), trivial to run to completion.

- **AFDL-MM-5 — Solver/planning integration: currently scores 2 but no *verified* plan exists**
  Files: new `tests/domains/python/test_mastermind_solver.py`, `src/autofde_lab/hub/solver/`.
  DoD: a registered POMDP-capable hub solver (this domain is `GoalPOMDPDomain`) solves to the goal `Score(total_bulls=n_positions, total_cows=0)` from a real initial distribution, plan verified via AFDL-MM-3. `pytest tests/domains/python/test_mastermind_solver.py` passes.
  Effort: **M** — need to confirm a POMDP solver exists in `src/autofde_lab/hub/solver/` capable of `GoalPOMDPDomain`; if not, this is L (new solver adaptation), not just M.

- **AFDL-MM-6 — Test coverage: zero test file exists for this domain**
  Files: new `tests/domains/python/test_mastermind.py` (does not exist — confirmed by directory search).
  DoD: new test file with real assertions: initial state distribution has `4**2` (n_colours=2, n_positions=2) equally-weighted states; `_calc_score` against 3+ hand-verified guess/solution pairs; `_is_terminal` true only at the exact goal score; `_get_applicable_actions_`/action space size matches `n_colours**n_positions`. Zero mock/patch/monkeypatch (`grep -n "mock\|patch\|monkeypatch" tests/domains/python/test_mastermind.py` empty). `pytest tests/domains/python/test_mastermind.py -v` all pass.
  Effort: **M** — new file from scratch per the task's own instruction, but the domain logic is small (142 lines) and self-contained, so coverage is straightforward once written.

- **AFDL-MM-7 — Standing honesty: no module-level standing tag**
  Files: `src/autofde_lab/hub/domain/mastermind/mastermind.py`, `docs/STATUS.md`.
  DoD: same as AFDL-GYM-5.
  Effort: **S**.

---

**Cross-domain infra flag:** none of these four domains touch a live cluster/cloud account — they are all in-process simulation or local-file-parsed (PSPLIB) domains, unlike e.g. `terragoat`/`azuregoat_privesc` (real vendored Terraform/subprocess-bridge patterns) or `gymact_bridge.py` (real subprocess-isolated external kernel). So Verification-independence tickets above (AFDL-GYM-2, AFDL-RCPSP-2, AFDL-RPS-3, AFDL-MM-3) can all reach genuine L4 with **subprocess/fresh-process re-derivation** — no infra gap, unlike a domain that would need a live external system to verify against.

Good, this confirms no mocks are present already (Test coverage scores of 4-5 are consistent). Now I have sufficient grounding across all four domains to write real tickets.

---

# k8s_goat_rbac_escalation — Domain: `src/autofde_lab/hub/domain/k8s_goat_rbac_escalation/k8s_goat_rbac_escalation.py`

Test coverage=5 — already meets L4 (real Astar solver, real in-process domain, `tests/domains/python/test_k8s_goat_rbac_escalation_unit.py` explicitly asserts zero mock/patch/monkeypatch per `.claude/rules/testing-chicago-style.md`). Standing honesty=5 — already meets L4 (module docstring explicitly states "Nothing here talks to a real Kubernetes API server... nor performs any actuation," matches its documented search-graph-only scope).

- **AFL-K8S-1 — Automated drift check between `K8sGoatRBACEscalation.DEFAULT_STEPS` and the vendored scenario-16 source**
  Files: `src/autofde_lab/hub/domain/k8s_goat_rbac_escalation/k8s_goat_rbac_escalation.py`, new `tests/domains/python/test_k8s_goat_rbac_escalation_drift.py`, reference `vendor/gyms/kubernetes-goat/guide/docs/scenarios/scenario-16/scenario-16.md` + `vendor/gyms/kubernetes-goat/scenarios/insecure-rbac/setup.yaml`.
  DoD: a real test parses the vendored `scenario-16.md` walkthrough (or a stable derived fixture of it, e.g. its numbered step list) and `setup.yaml`'s RBAC binding, and asserts the parsed step ids/order match `DEFAULT_STEPS`' `id`/`prerequisite_ids` structure exactly, failing loudly if the vendored file changes underneath it (i.e. re-vendoring the scenario is what breaks the test, not a hand edit to this module). `uv run pytest tests/domains/python/test_k8s_goat_rbac_escalation_drift.py -v` green, zero mocks.
  Effort: **M** — the domain module already carries an unenforced prose citation to the source files; writing a real parser/comparator against the walkthrough Markdown and setup.yaml is new code, but the source structure (five sequential attack steps, one ClusterRole binding) is simple and stable.

- **AFL-K8S-2 — Real actuation authority: typed refusal for a materialize/act call without a bounded plan/precondition gate**
  Files: `src/autofde_lab/hub/domain/k8s_goat_rbac_escalation/k8s_goat_rbac_escalation.py` (currently has zero actuation surface — no `gymact_bridge.py`, no DO capability), new `src/autofde_lab/hub/domain/k8s_goat_rbac_escalation/gymact_bridge.py` modeled on `src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py` and `src/autofde_lab/hub/domain/gym_procedure/level4_gymact_bridge.py`, new sabotage test `tests/domains/python/test_k8s_goat_rbac_escalation_actuation_refusal_chicago.py`.
  DoD: a real subprocess-bridge (or explicit `BLOCKED:NO_LIVE_CLUSTER` refusal path if no kubernetes-goat cluster is available locally — see infra flag below) whose every DO capability (e.g. `authenticate_to_apiserver`, `read_and_decode_k8svaultapikey`) is gated on a typed precondition + plan-order check, proven by a real sabotage test that calls a capability out of order (e.g. `list_namespace_secrets` before `authenticate_to_apiserver`) and asserts a typed refusal (not an exception, not a silent no-op). `uv run pytest tests/domains/python/test_k8s_goat_rbac_escalation_actuation_refusal_chicago.py -v` green.
  Effort: **L** — zero actuation surface exists today; this is a new bridge file plus a new capability-gating layer, mirroring the `azuregoat_privesc`/`gym_procedure` pattern from scratch. **Infrastructure flag: true actuation against a live Kubernetes Goat cluster is out of reach without a live k8s cluster in this environment.** Closest achievable proxy: gate against a real local `kind`/`minikube` cluster running `vendor/gyms/kubernetes-goat/scenarios/insecure-rbac/setup.yaml` if one can be stood up in CI, or — if that infra is not available — an explicit, honestly-labeled `BLOCKED:NO_LIVE_CLUSTER` refusal path that still proves the precondition/plan-order gating logic runs correctly in isolation (unit-level sabotage test against the gate function itself, not a live API call). Do not silently downgrade this ticket's bar to "gate exists" without naming the missing live-cluster verification.

- **AFL-K8S-3 — Verification independence: re-derive scenario completion from a source other than in-process planning state**
  Files: new `src/autofde_lab/hub/domain/k8s_goat_rbac_escalation/verify.py`, new `tests/domains/python/test_k8s_goat_rbac_escalation_verify_independent_chicago.py`.
  DoD: a `verify()` function that re-derives "flag recovered" from an independent source — e.g. a fresh subprocess re-reading a real cluster secret via `kubectl get secret k8svaultapikey -o jsonpath=...` (matching the terragoat/gym_procedure subprocess-bridge pattern cited in the task), not from the same `State.known` frozenset the planning domain accumulated. Test asserts verify() run against a state produced by a *different* process/session still confirms success independently.
  Effort: **L** — no verification code exists at all today; this requires either a live cluster (see infra flag in AFL-K8S-2) or, as the closest local proxy, an independent re-parse of a captured transcript/log file distinct from the in-memory `State` the domain built, which is itself new machinery. **Infrastructure flag: full independent verification against a live API server is out of reach without a live cluster; the local proxy (independent re-parse of a persisted transcript) is the ticketed bar.**

- **AFL-K8S-4 — Real, schema-valid OCEL 2.0 evidence from an actual materialize→act→verify→teardown episode**
  Files: new `src/autofde_lab/hub/domain/k8s_goat_rbac_escalation/gymact_bridge.py` (shared with AFL-K8S-2) emitting OCEL events, new `docs/evidence/k8s_goat_rbac_escalation/episode.ocel.json`, new run script `scripts/k8s_goat_rbac_escalation_episode.sh` or `.py`.
  DoD: `python scripts/k8s_goat_rbac_escalation_episode.py` runs a real (or the local-proxy, see AFL-K8S-2's infra flag) materialize→act→verify→teardown episode and writes a schema-valid OCEL 2.0 log to `docs/evidence/k8s_goat_rbac_escalation/episode.ocel.json`; a companion test validates the JSON against the OCEL 2.0 JSON schema (e.g. via the same validator used elsewhere in the repo, if one exists — grep `ocel` schema usage in `gym_procedure`) and asserts non-empty `events`/`objects` arrays reflecting the real five-step episode.
  Effort: **L** — depends on AFL-K8S-2/3 landing first (no bridge, no episode to log); this is new OCEL-emission code plus a new evidence artifact and run script.

- **AFL-K8S-5 — Register a real solver against the actuation-gated domain and produce a verified plan**
  Files: `src/autofde_lab/hub/domain/k8s_goat_rbac_escalation/k8s_goat_rbac_escalation.py`, `tests/planning/test_fortune5_k8s_state_space_plan_chicago.py` (existing, extend), possibly `autofde_lab.domains` entry-point registration (currently deliberately unregistered per the module docstring).
  DoD: a registered solver (Astar, already used in the unit test) produces a plan over the domain, and that plan is run through the real actuation bridge (AFL-K8S-2) with the result independently verified (AFL-K8S-3) — not just an in-memory `solver.solve()` checkpoint as today. `uv run pytest tests/planning/test_fortune5_k8s_state_space_plan_chicago.py -v` asserts a full plan→actuate→verify chain, not solve-only.
  Effort: **M** — the solver-integration half already exists (`Astar` works today per the unit test); the new work is wiring plan output into the actuation/verification pair from AFL-K8S-2/3, which is why this is smaller than those tickets themselves.

---

# career_admission — Domain: `src/autofde_lab/hub/domain/career_admission/career_admission.py`, `authority.py`

Standing honesty=5 — already meets L4 (module docstrings for both files are explicit: "Scope — this is search-graph work only... No receipt, admission, actuation, or standing-closure semantics are implemented or implied here").

- **AFL-CAR-1 — Automated drift check against the real `ggen-legacy` authority file**
  Files: `src/autofde_lab/hub/domain/career_admission/authority.py` (currently a one-shot hand-parsed load via `load_capability_facts`, no drift detection), new `tests/domains/python/test_career_admission_authority_drift.py`.
  DoD: a real test that re-reads `~/ggen-legacy/ontology/v26.8.1/legacy-capabilities.ttl` (the actual vendored authority source, read in place per the module's own design) at test time and asserts the parsed fact count (currently implicitly 65 `ggen:LegacyCapability` individuals, 45 blocked) and the blocked/admitted partition are still consistent with what `load_capability_facts`/`is_blocked_capability` compute — so if the upstream ontology file changes, this test fails rather than silently drifting. `uv run pytest tests/domains/python/test_career_admission_authority_drift.py -v` green when the vendored file is current, and demonstrably red if a stale/mismatched copy is substituted (prove this once by pointing `path=` at a doctored fixture).
  Effort: **S** — `authority.py` already does the real parsing (`parse_legacy_turtle`/`load_capability_facts`/`is_blocked_capability`); this ticket is a new drift-assertion test over already-live parsing logic, not new parsing machinery. `tests/domains/python/test_career_admission_authority.py` (173 lines) already exercises much of this — check first whether it already covers drift and this ticket reduces to adding one assertion, or extend it explicitly for drift.

- **AFL-CAR-2 — Actuation authority: typed refusal for admitting a blocked capability out of order**
  Files: `src/autofde_lab/hub/domain/career_admission/career_admission.py` (currently zero actuation surface — `_get_applicable_actions_from` silently excludes blocked facts rather than refusing them with a typed reason), new `tests/domains/python/test_career_admission_actuation_refusal_chicago.py`.
  DoD: a real sabotage test that attempts to force-admit a fact whose `prerequisite_ids` include `UNASSIGNED_VERIFIER_ID` (from `authority.py`) and asserts a typed refusal object/exception is raised (not silently absent from `_get_applicable_actions_from`'s returned space) — i.e. the domain must expose a real precondition-check entry point separate from "just doesn't show up in applicable actions," so a caller attempting the action directly gets a named refusal, matching the `career_admission_pack`'s own "chicken-and-egg" framing. `uv run pytest tests/domains/python/test_career_admission_actuation_refusal_chicago.py -v` green.
  Effort: **M** — `career_admission.py` has no actuation surface at all (it's pure search-graph, `_get_transition_value` just returns `float("inf")` for unknown ids, no typed refusal object exists anywhere in the module); this requires adding a new typed-refusal precondition-check API and a real test exercising it.

- **AFL-CAR-3 — Verification independence: re-derive admitted-set validity from a source other than in-process `State`**
  Files: new `src/autofde_lab/hub/domain/career_admission/verify.py`, new `tests/domains/python/test_career_admission_verify_independent_chicago.py`.
  DoD: a `verify(admitted_ids, authority_path=...)` function that independently re-reads `ggen-legacy/ontology/v26.8.1/legacy-capabilities.ttl` fresh from disk (a separate read from whatever produced the plan) and re-checks that every admitted id's prerequisites are satisfied and no `REFUSED`-disposition (blocked) capability was admitted — run as a genuinely separate process step (e.g. a `subprocess.run([sys.executable, "-m", ...])` call, not just a second in-process function call reusing the same loaded `graph` dict), matching terragoat's/gym_procedure's real subprocess-verification pattern named in the task brief.
  Effort: **M** — `authority.py`'s parsing functions (`parse_legacy_turtle`, `is_blocked_capability`) are directly reusable; the new work is wrapping them in a genuinely independent (fresh-process, fresh-disk-read) verify entry point plus a test proving it catches a plan that admitted a blocked fact.

- **AFL-CAR-4 — Real, schema-valid OCEL 2.0 evidence from a real admission episode**
  Files: new `src/autofde_lab/hub/domain/career_admission/gymact_bridge.py` or lighter-weight OCEL-emission module (no gym/cluster is involved here — this is pure in-process state, unlike k8s), new `docs/evidence/career_admission/episode.ocel.json`, new run script `scripts/career_admission_episode.py`.
  DoD: `python scripts/career_admission_episode.py` runs a real materialize (load authority)→act (admit facts per an Astar plan)→verify (AFL-CAR-3)→teardown episode and emits a schema-valid OCEL 2.0 log to `docs/evidence/career_admission/episode.ocel.json`, validated by a companion test against the OCEL 2.0 schema.
  Effort: **M** — no cluster/subprocess bridge needed (this domain is pure in-process planning over a static ontology file), so this is lighter than the k8s equivalent — new OCEL-emission code and one run script, but no live-infra dependency.

- **AFL-CAR-5 — Register a real solver and produce a verified admission plan**
  Files: `src/autofde_lab/hub/domain/career_admission/career_admission.py`, `tests/domains/python/test_career_admission_unit.py` (existing, extend — currently solve-only per its own docstring "real rollout, no mocks -- an action").
  DoD: extend the existing unit test (or add a new Chicago-tier test) so the Astar-produced plan is run through AFL-CAR-2's actuation gate and AFL-CAR-3's independent verify, not just checked for reaching a goal state in-memory.
  Effort: **S** — the solver integration already exists and works (`test_career_admission_unit.py`, 86 lines, real Astar); this is wiring, contingent on AFL-CAR-2/3 landing first.

---

# breach_clock — Domain: `src/autofde_lab/hub/domain/breach_clock/breach_clock.py`

Standing honesty=5 — already meets L4 (module docstring's opening line is literally "Breach Clock — a SIMULATED incident-response planning domain," with an explicit list of what it does not touch).

- **AFL-BRC-1 — Domain-fidelity drift check: none possible without naming the missing real source**
  Files: `src/autofde_lab/hub/domain/breach_clock/breach_clock.py`.
  This domain is scored `Domain fidelity=1` because, unlike `k8s_goat_rbac_escalation` (vendored scenario-16 walkthrough) or `career_admission` (vendored `ggen-legacy` ontology), `breach_clock.py`'s own docstring states it is pure simulation with **no external reference source at all** — "no cloud provider, no identity system, no workload, and no notification channel." There is nothing to drift-check against because there is no real system this domain claims to model faithfully; the eight `Action` enum members and their preconditions are hand-invented, not transcribed from a real incident-response runbook or regulatory framework (e.g. GDPR 72-hour notification, NIST IR).
  DoD (closest achievable): pick a real, citable incident-response reference (e.g. NIST SP 800-61 phases, or a specific regulator's breach-notification timeline) and rewrite the docstring + `Action`/precondition structure to cite it verbatim (mirroring how `k8s_goat_rbac_escalation.py` cites `scenario-16.md` line-for-line), then add a drift test against that citation the same shape as AFL-K8S-1.
  Effort: **L** — this is a structural rewrite of the domain's grounding, not an incremental patch; the current model has zero real-source anchor to drift-check against, so "automated drift check" first requires choosing and vendoring/citing a real source. **Flag: this ticket changes what the domain models, not just how it's verified — confirm with domain owner before starting, since "SIMULATED" may be an intentional design choice for this domain rather than a gap.**

- **AFL-BRC-2 — Actuation authority: typed refusal for out-of-order containment/notification actions**
  Files: `src/autofde_lab/hub/domain/breach_clock/breach_clock.py` (has a real, well-tested `applicable()` predicate but zero DO-capability/actuation surface — everything stays in-memory `State` transitions), new `tests/domains/python/test_breach_clock_actuation_refusal_chicago.py`.
  DoD: a real sabotage test that calls `_get_next_state` (or a new typed `actuate()` wrapper) with an inapplicable action per `applicable()` (e.g. `deliver_notification` before `draft_notification`) and asserts a typed refusal is raised rather than the current silent fallthrough (`_get_next_state`'s final `return s` — the state is simply unchanged, no error, no refusal object). This is the concrete gap: today an inapplicable action silently no-ops instead of failing loudly.
  Effort: **M** — `applicable()` (lines 186-214) is real, well-documented, and already exercised by `tests/agent/test_breach_clock_chicago.py` (641 lines); the gap is that `_get_next_state` doesn't consult it and doesn't refuse — wiring a typed-refusal wrapper around the existing predicate is a moderate, well-scoped change.

- **AFL-BRC-3 — Verification independence: none possible without first having any actuation**
  Files: new `src/autofde_lab/hub/domain/breach_clock/verify.py`.
  DoD: since this domain performs no real-world actuation by design (pure simulation, per its own docstring), true "verify from an independent source" (subprocess/disk/API) has no real target to re-derive from. Closest achievable proxy: an independent re-simulation — a `verify()` that takes a committed action sequence and a claimed final `State`, re-runs the sequence through a *fresh* `BreachClockDomain` instance (not the same in-memory object the planner used) via `_get_next_state`/`applicable`, and asserts the re-derived state matches, catching any object-identity/mutation bug the original run might have masked.
  Effort: **S** — the domain's transition function is already pure and deterministic (confirmed by the module docstring: "`revoke_sessions` moves an enum in a `State` tuple and does nothing else"), so a fresh-instance replay is cheap to build; this is the cheapest verification-independence ticket of the four domains because there's no subprocess/cluster dependency to stand up. **Flag: this is a within-process re-derivation, not verification against an external system — true independent verification is not applicable to a domain that is simulation-only by design; name this explicitly rather than claiming external verification was achieved.**

- **AFL-BRC-4 — Real, schema-valid OCEL 2.0 evidence from a real simulated episode**
  Files: new `src/autofde_lab/hub/domain/breach_clock/episode.py`, new `docs/evidence/breach_clock/episode.ocel.json`, new run script `scripts/breach_clock_episode.py`.
  DoD: `python scripts/breach_clock_episode.py` runs a real simulated episode (triage→collect_evidence→compute_scope→one containment choice→observe_divergence→draft_notification→deliver_notification, exercising the divergence hook named in the module docstring) and emits a schema-valid OCEL 2.0 log, validated by a companion test.
  Effort: **M** — the domain logic driving the episode is fully real and already tested (`tests/agent/test_breach_clock_chicago.py`); this is new OCEL-emission code and a run script wrapping an already-correct simulation, no live-infra dependency.

- **AFL-BRC-5 — Register a real solver and produce a verified plan through the divergence hook**
  Files: `src/autofde_lab/hub/domain/breach_clock/breach_clock.py`, `tests/agent/test_breach_clock_chicago.py` (existing, extend).
  DoD: extend the existing Chicago test suite so a registered solver's plan is replanned mid-execution via `observe_divergence` (the domain's own named "forces a replan" mechanism) and the replanned result is independently re-verified per AFL-BRC-3, not just solved once.
  Effort: **S** — `test_breach_clock_chicago.py` is already 641 lines and Chicago-style with zero mocks; this is incremental wiring against AFL-BRC-2/3, not new domain logic.

---

# graph_domain — Module: `src/autofde_lab/hub/domain/graph_domain/GraphDomain.py`

Test coverage=5 — already meets L4 (`tests/domains/test_graph_domain.py`, 299 lines, explicitly states "no mocking of the domain under test," 19/19 passing per `docs/STATUS.md` line 491).

- **AFL-GRD-1 — Domain fidelity: this module has no external reference to be faithful to — name the actual gap and ticket the real fix**
  Files: `src/autofde_lab/hub/domain/graph_domain/GraphDomain.py`.
  Unlike the other three domains, `GraphDomain`/`GraphDomainUncertain` are generic containers over caller-supplied `next_state_map`/`state_terminal` dicts (lines 145-242) — there is no "real world" this module claims to model, so "domain fidelity" as defined for the other three domains (drift check against a vendored source) does not apply here in the same sense. The actual `Domain fidelity=2` score reflects a different real gap: **zero module docstring or class-level documentation at all** (confirmed: no docstring on the module, `GraphDomainUncertain`, or `GraphDomain` beyond one inline sentence each) — a caller cannot tell from the file what invariants `next_state_map`/`next_state_attributes` must satisfy (e.g. must every state in `next_state_map` also appear in `next_state_attributes` with matching action keys? `merge()` at lines 176-195 assumes so but never asserts it).
  DoD: add a real docstring stating the module's actual contract (generic pre-computed-transition-table domain, no live source, invariants over the two dict parameters), plus a real invariant-checking test (`tests/domains/test_graph_domain.py`, extend) that constructs a `GraphDomain` with a mismatched `next_state_map`/`next_state_attributes` pair and asserts a typed error rather than a silent `KeyError` deep in `_get_transition_value`.
  Effort: **S** — this is a documentation + one invariant-check addition to an already well-tested, small (242-line) module, not new domain modeling.

- **AFL-GRD-2 — Actuation authority: `merge()` silently overwrites without precondition/plan-order gating**
  Files: `src/autofde_lab/hub/domain/graph_domain/GraphDomain.py` (`merge()`, lines 176-195 — the only mutating/combining operation in the module, and it currently has zero validation), new `tests/domains/test_graph_domain_merge_refusal_chicago.py`.
  DoD: a real sabotage test that calls `merge()` on two `GraphDomain` instances with conflicting `attribute_weight` values or overlapping-but-inconsistent transitions for the same `(state, action)` pair, and asserts a typed refusal (`ValueError` with a real message, not silent last-write-wins as today — `merge()`'s `if action not in next_state_map[k]` guard means a conflicting existing transition is silently kept, never flagged).
  Effort: **S** — `merge()` is a small, already-fully-read function (20 lines); adding a conflict-detection guard and one test is a contained change.

- **AFL-GRD-3 — Verification independence: re-derive reachability/goal status from the graph's own `to_networkx()` export, not the dict state `_is_terminal`/`_get_goals_` read**
  Files: `src/autofde_lab/hub/domain/graph_domain/GraphDomain.py` (`GraphDomainUncertain.to_networkx()`, lines 84-101 — already exists and is a real, independent representation), new `tests/domains/test_graph_domain_verify_independent_chicago.py`.
  DoD: a test that takes a plan/path produced by a solver over `GraphDomain`/`GraphDomainUncertain`, exports the domain via the existing `to_networkx()` method, and independently re-checks the plan's validity using `networkx` path-checking (e.g. `nx.is_path`/edge-existence walk) rather than re-querying `next_state_map` directly — a genuinely separate code path (`networkx`'s own graph traversal) re-deriving the same fact, satisfying the "different source" bar even though both ultimately read the same dicts (this module has no external system to verify against, so the closest available independence is a structurally different traversal implementation).
  Effort: **S** — `to_networkx()` already exists and is exercised in `tests/domains/test_graph_domain.py`; this ticket adds one new test using it for independent verification rather than new production code. **Flag: `GraphDomain` (deterministic) itself has no `to_networkx()` — only `GraphDomainUncertain` does; if the drift-check/verify tickets target the deterministic `GraphDomain` class specifically, `to_networkx()` needs porting to it first (add ~S effort).**

- **AFL-GRD-4 — Real, schema-valid OCEL 2.0 evidence from a real solve episode over a graph domain**
  Files: new `docs/evidence/graph_domain/episode.ocel.json`, new run script `scripts/graph_domain_episode.py`.
  DoD: `python scripts/graph_domain_episode.py` constructs a real (non-trivial, multi-state) `GraphDomain`, solves it, exports via `to_networkx()`, and emits a schema-valid OCEL 2.0 log of the solve episode, validated by a companion test.
  Effort: **S** — this module has no live-infra dependency and the solve/export machinery already exists; purely new OCEL-emission wiring.

Solver/planning integration=3 — already close to L4 but not fully there; existing coverage (`tests/domains/test_graph_domain.py`, 19 passing, touched incidentally by scheduling/GNN solver tests per `docs/STATUS.md` line 491) is real but not yet "a real registered solver produces a verified plan" as a dedicated, named test — folding a solver+verify assertion into AFL-GRD-3's new test closes this without a separate ticket.
