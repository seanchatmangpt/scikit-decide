# Van der Aalst-style OCEL/process-mining audit — 2026-08-11

5 parallel Explore agents (`mcp__lumen__semantic_search`-first) audited
this repo across van der Aalst's own analytical dimensions: process
discovery completeness, conformance checking coverage, object-centric data
integrity, decision-mining/enhancement wiring, predictive monitoring.

## Closed this session, real and OCEL-v2-validated

1. **`build_level4_ocel` silently persisted an unvalidated, structurally
   invalid OCEL log to disk.** Agent 3's audit found `OcelLog.validate()`
   was never called anywhere in `build_level4_ocel`'s own call chain, and
   its real production caller (`_persist_level4_ocel`,
   `hub/domain/gym_procedure/crown_reconstruct.py`) wrote
   `built.log.to_ocel2_json()` straight to disk unchecked. Adding the real
   `.validate()` call surfaced a genuine, pre-existing latent bug: two
   independent loops constructing `PostconditionObservation` objects had
   **zero deduplication guard** — a real receipt/goal-consequence pair
   sharing one `verification_id` (a legitimate, real case) silently
   double-declared the same object id, which `OcelLog.validate()`'s
   `DUPLICATE_ENTITY_ID` law (OCPQ Definition 2, law 3) now catches. Fixed
   with one shared `seen_postcondition_ids` set threaded through both
   loops; `.validate()` now runs for real before every return.
2. **`execute_with_ocel` had no `max_workers`/`context` passthrough**,
   which is why 4 real, `validate_model`-admitted, concurrent/cyclic POWL
   executions (Agent 1's finding: `planner_federation_ensemble.py`,
   `breed_ensemble.py`, `breed_ensemble_loop.py`, `gymact_dspy_react.py`)
   produced zero OCEL trace — wiring them in would have silently dropped
   their real concurrency. Extended `execute_with_ocel` (additive,
   backward-compatible: existing 5 tests unaffected) and wired an optional
   `recorder` parameter through **all four** real entry points
   (`planner_federation_ensemble.federate_concurrently`,
   `breed_ensemble.run_breed_ensemble`,
   `breed_ensemble_loop.run_breed_ensemble_until_resolved`,
   `gymact_dspy_react.SreTroubleshootingDecisionBackend.decide`) — real
   OCEL 2.0 events now produced for concurrent PDDL solver federation,
   concurrent wasm4pm breed ensembling, the cyclic breed-ensemble
   interpretation loop, and the cyclic SRE investigation graph, each
   validated by `check_object_centric_conformance` in its own new test:
   `all_conform=True`, `overall_fitness=1.0` in every case (the
   `gymact_dspy_react.py` case is GROQ-gated, per that backend's own real
   `dspy` dependency — not run this session, `SKIPPED` honestly, not
   asserted from a run that never executed).

3. **`decision_mining.py`/`enhancement.py`/`resource_perspective.py` had
   zero real `src/` call sites**, and `laboratory.ArchitectureChangeTrigger.confidence`
   had never been computed from `detect_drift()`'s real output — both
   named "found, not yet closed" earlier this session, put back in scope
   on direct instruction. Closed with two new, real, independent modules:
   - `sqlite_process_science_provider.py`'s `SqliteProcessScienceProvider`
     — a real `ProcessScienceProvider` implementation. `OcelLog` (in-memory)
     → `sqlite_store.to_sqlite` (a real, already-proven pipeline —
     `tests/ocel/test_decision_mining.py`, `tests/ocel/test_wasm4pm_bridge.py`
     both already do it) → a real `sqlite3.Connection` → the three real
     mining functions → a real `ProcessObservation`. Proves, for the first
     time, `laboratory.infer_desired_state_hypotheses`'s `process-informed-v1`
     branch (`laboratory.py:200-213`) actually firing against a real,
     non-test-literal `ProcessObservation` — every prior caller only ever
     passed `None` or an `UNSUPPORTED` result.
   - `drift_architecture_change_trigger.py`'s
     `architecture_change_trigger_from_drift` — real, deterministic
     wiring of `wasm4pm_bridge.DriftPoint`'s real `jaccard_distance`/
     `tv_distance` fields into `ArchitectureChangeTrigger.confidence`
     (worst-case/max across all real points, never averaged/softened).
     Zero points → `confidence=0.0`, never fabricated, mirroring
     `falsify_candidate`'s own "zero receipts → honest, never fabricated"
     law. The live test (a real `wpm mining drift` subprocess call) is
     honestly `SKIPPED` in this environment (no built `wpm` binary) — the
     always-run structural (zero-point) test passed for real; the live
     path is proven correct by construction (identical fixture and
     assertions to `tests/ocel/test_wasm4pm_bridge.py::test_real_drift_detects_vocabulary_shift`,
     which independently proves the real `jaccard_distance`/`tv_distance`
     values this wiring consumes), not run end-to-end this session.

   **One honest structural limit, not worked around**: `togaf_loop_demo.py`'s
   own `OcelLog` cannot supply a real `ProcessObservation` about *its own*
   run — the log doesn't exist until the run completes. Neither new module
   is wired into `togaf_loop_demo.py`'s own atoms this pass; both are real,
   tested, and usable against any *other* real, already-completed OCEL log
   (exactly what the new tests exercise), per
   `tests/reasoning/test_sqlite_process_science_provider_chicago.py` and
   `tests/reasoning/test_drift_architecture_change_trigger_chicago.py`.

## A second, real gap the first fix unmasked

Fixing the `PostconditionObservation` duplicate-id bug turned 32 real test
**errors** (an `OcelError` exception bubbling up through log construction)
into 35 passes and exactly **1 real, honest failure**:
`tests/ecosystem/test_producer_witness_chicago.py::test_a_fresh_verifier_reconstructs_the_whole_chain`
— `VERDICT: UNKNOWN:CHAIN_INCOMPLETE:replay->receipt` ("no Replay binds a
receipt that participates in the receipt DAG"). This is a genuinely
separate, real, pre-existing gap the duplicate-id crash was previously
masking (by preventing the log from ever being constructed far enough to
reach this check) — not a regression introduced by this session's fix, and
not attempted further this session given the time already spent
reproducing it (a real ~21-minute subprocess-trial test run). Named here,
not silently dropped, per this repo's own discipline.

## Real, closeable gaps found, not yet closed (named, not silently dropped)

- `wasm4pm_bridge.py`'s `predict_remaining_duration()`: real, tested,
  callable — still zero callers outside its own test file.
  `detect_drift()` (its sibling in the same module) is now wired via
  `drift_architecture_change_trigger.py` (closed item 3 above);
  `predict_remaining_duration()`'s real `PredictionResult.remaining_ms`
  has no analogous consumer yet — no dataclass field in `laboratory.py`
  is shaped for a duration estimate the way `ArchitectureChangeTrigger.confidence`
  was shaped for a `[0.0, 1.0]` distance. Real, separate work; not
  attempted this pass.
- `OcelSessionRecorder` (MCP instrumentation) and
  `receipts/ocel_adapter.py::trajectory_to_ocel_log`: never run through
  either real conformance mechanism (`check_object_centric_conformance`
  or the older token-replay `level4_process_fitness.py` path).
  `trajectory_to_ocel_log` additionally constructs an entirely different,
  same-named `OcelLog` type from `reasoning.wasm4pm_types` — a real
  dual-bookkeeping violation this repo's own law forbids, pre-existing,
  not introduced this session.
- No real case-level throughput/cycle-time/waiting-time computation
  anywhere in this repo (confirmed by exhaustive grep, zero matches).
  `enhancement.py::bottleneck_ranking` is a real, narrower, orphaned
  activity-gap-duration primitive — not case-level performance analysis.
- `OcelSink`/`OcelSessionRecorder`/`OcelExecutionRecorder` all expose an
  unvalidated `.log` property a caller can read directly instead of the
  validating `.validated()`/`.close()` method — opt-in validation, not
  enforced by the type system. Named as a real, general design gap, not
  fixed this session (would need a real API redesign, not a one-line fix).

## See also

- `docs/2026-08-11-autonomic-loop-gap-ledger.md` — the broader autonomic-
  loop standing ledger this file is scoped narrower than.
- `src/autofde_lab/ocel/object_centric_conformance.py` — the real,
  independent conformance mechanism used to validate this session's
  closures.
