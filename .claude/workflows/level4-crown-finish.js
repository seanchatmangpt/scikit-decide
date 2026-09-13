export const meta = {
  name: 'level4-crown-finish',
  description: 'Finish and validate the Level 4 crown end-to-end with Chicago-style tests',
  phases: [
    { title: 'Repair', detail: 'per-step postconditions + outer loop' },
    { title: 'Providers', detail: 'structurally distinct bounded gymact providers' },
    { title: 'Tests', detail: 'Chicago tests + falsifiers' },
  ],
}

const REPO = '/Users/sac/autofde-lab'
const GYMACT = '/Users/sac/gymact'

const CONTEXT = `
CONTEXT (already built and REAL, verified by real runs this session):
- ${REPO}/src/autofde_lab/hub/domain/gym_procedure/discovered_domain.py
  DiscoveredDomain/DiscoveredProblem/DiscoveredAction IR + induce_discovered_domain +
  propose_discriminating_probe + refine_from_probe + project_to_recipe + project_to_pddl
- .../state_typing.py  DimensionKind (BOOLEAN/CATEGORICAL/INTEGER/CONTINUOUS/OBJECT_VALUED/UNKNOWN),
  classify_observation, propositionalize (returns UNREPRESENTABLE:<reason> for lossy dims), ProjectionResult
- .../level4_gymact_bridge.py  RealBlindEnvironment: subprocess bridge into ${GYMACT}/.venv driving real
  GymAct episodes. Providers: 'cube_counter', 'cube_container_counter'. available_actions() ->
  ['increment','decrement','increment_by']. try_action(a) -> {action, applicable, observed_pre_facts,
  delta_added, delta_removed, standing, reason}
- .../planner_federation.py  classify_registered_solvers(recipe) (49/55 SUPPORTED, real check_domain),
  run_federation(recipe, names, timeout_s) -> list[PlannerAttempt]
- .../level4_crown.py  critique_candidates (advisory), independently_validate -> ValidatedPlan,
  commit -> PowlCommitment, commit_and_execute (ONLY actuation path; refuses non-PowlCommitment with
  AdvisoryAuthorityRefused = ADVISORY_AUTHORITY_USED_AS_BEARER), validate_ocel_referential_integrity
- .../level4_generator.py  Trial (uuid4 run_id + isolated evidence dir), BlindEnvironment (synthetic),
  blind_discover_and_plan, verify_trial

REAL VERIFIED RUN (do not re-derive, it works):
  vp = ValidatedPlan(plan=('increment',)*3, model_digest='x'); c = commit(vp,'t')
  res = commit_and_execute(c, 'cube_counter', {'target':3}, {'counter':3,'solved':True}, evdir)
  -> independently_verified=True, 7 receipts, ocel_valid=True, 0 ref violations, replay 0 mismatches

RULES (hard):
- Chicago-style tests ONLY: real collaborators, real subprocesses, real files, assert final STATE.
  unittest.mock / Mock / MagicMock / patch / monkeypatch are BANNED. No interaction assertions.
- Run tests with: cd ${REPO} && .venv/bin/python -m pytest <paths> -v
- NEVER fabricate results. Report real command output. If something fails, say so with the output.
- Do not weaken assertions to make tests pass. Fix the code or report the real failure.
`

phase('Repair')

const repair = await agent(`${CONTEXT}

TASK: Two real repairs in ${REPO}/src/autofde_lab/hub/domain/gym_procedure/level4_crown.py

(1) PER-STEP POSTCONDITIONS. Currently commit_and_execute's embedded _EXECUTE_SCRIPT passes the SAME
'expected' dict to execute_verified after EVERY action, so intermediate steps of a multi-step plan are
REFUSED (verified real: 3x increment to target 3 gave REFUSED, REFUSED, ALIVE). Fix: commit_and_execute
should accept a list of per-step expected dicts (one per plan action), passing expected[i] to
execute_verified for step i. Keep a single-dict form working for backward compat (broadcast it to the
final step only, with earlier steps using a plain predicted postcondition). Add a helper
predict_step_postconditions(plan, provider_key, initial_observation) that predicts the expected
observation after each step for the counter providers (increment: counter+1, decrement: counter-1,
increment_by: counter+payload amount; solved = counter==target). Verify with a REAL run:
3x increment against cube_counter target 3 must give ALIVE+verified for ALL THREE steps.

(2) OUTER DISCOVER<->PLAN LOOP. Add run_real_trial(seed, provider_key, config, evidence_root) implementing:
  probe -> induce DiscoveredDomain_n -> project (recipe; record UNREPRESENTABLE losses) ->
  run_federation over ALL classified-SUPPORTED solvers (bounded timeout ~10s each) ->
  critique_candidates -> if disagreement AND probe budget remains: propose_discriminating_probe,
  probe it, induce DiscoveredDomain_n+1, replan -> independently_validate best candidate ->
  commit -> commit_and_execute -> return a TrialReport dataclass with: seed, run_id, provider,
  n_probes, n_planner_attempts, planners_producing_candidates, disagreement_detected,
  independently_verified, ocel_valid, ocel_ref_violations, replay_mismatches, evidence_dir.
Use typed state: build facts via state_typing.propositionalize and RECORD the UNREPRESENTABLE losses
in the report (do not silently drop them).
IMPORTANT: the discovery phase uses RealBlindEnvironment (real gymact). Keep per-trial isolation:
unique uuid4 run_id + own evidence dir, exactly like level4_generator.Trial.

Then RUN it for real: run_real_trial(seed=1, 'cube_counter', {'target':3}, <tmpdir>) and report the
REAL output. Fix whatever really breaks. Report the final real TrialReport values.

Return: what you changed, the real run output, and any real remaining failure.`, { phase: 'Repair' })

phase('Providers')

const providers = await agent(`${CONTEXT}

TASK: Add 3 structurally-distinct bounded local providers to ${GYMACT}/src/gymact/gyms/, each
seed-parameterized, requires_authority=False, no cloud/network/Docker. Follow the EXACT structure of
${GYMACT}/src/gymact/gyms/cube_counter.py (module-level *_CAPABILITIES tuple of gymact.models.Capability
with consequence=Consequence.DO/READ and a 'binding' dispatch key; an Environment class with
environment_id, requires_authority, capabilities(), async observe/actuate/verify/checkpoint/restore/teardown;
a Provider class with name + materialization_requires_authority + async materialize(scenario, config)).
Do NOT depend on the optional counter_cube package -- these must be self-contained pure Python.

1. switchboard.py  (name='switchboard'): N boolean switches; some actions have CONDITIONAL effects
   (flip C only works if A and B are on), some are irrelevant/decoy switches, at least one action has a
   NEGATIVE effect (turns something off). Goal: a specific switch pattern. Config: {'seed': int, 'n_switches': int}.
2. resource_flow.py (name='resource-flow'): bounded token pools with capacity; actions consume and produce;
   at least one action IRREVERSIBLY consumes a resource so a later action becomes impossible (real dead end).
   Goal: reach a target amount in an output pool. Config: {'seed': int, 'capacity': int, 'target': int}.
3. lock_and_key.py  (name='lock-and-key'): ordered hidden prerequisites; reversible AND irreversible actions;
   deceptive-but-lawful dead ends that are executable but never reach the goal. Goal: open the final lock.
   Config: {'seed': int, 'depth': int}.

Each provider's observe() must return a dict mixing types (bool + int at minimum) so the typed-state
classifier is genuinely exercised.

Then write a REAL Chicago test file ${GYMACT}/tests/test_bounded_discovery_gyms.py exercising all three
through the REAL GymAct kernel (register_provider -> MaterializationIntent -> act -> observe -> verify ->
teardown), asserting real final STATE (not interactions). Follow the structure of
${GYMACT}/tests/test_cube_counter.py.

RUN IT FOR REAL: cd ${GYMACT} && .venv/bin/python -m pytest tests/test_bounded_discovery_gyms.py -v
Report the real output. Fix real failures. Do NOT commit -- just leave the files and report.

Return: files created, the real pytest output, real pass/fail counts.`, { phase: 'Providers' })

phase('Tests')

const tests = await agent(`${CONTEXT}

TASK: Write Chicago-style tests in ${REPO}/tests/ecosystem/test_level4_crown_chicago.py covering the
Level 4 crown chain. Real collaborators only -- real gymact subprocess, real Astar/solvers, real files.
Skip with a named BLOCKED:<reason> via pytest.mark.skipif ONLY if ~/gymact or its .venv is genuinely
absent (use level4_gymact_bridge.skip_reason()).

Required tests (each asserting real final state):
1. test_typed_state_preserves_continuous_dimension_as_unrepresentable -- classify_observation on the REAL
   observation shape; assert reward is CONTINUOUS, solved is BOOLEAN, and propositionalize reports
   UNREPRESENTABLE for reward and does NOT emit a reward= fact.
2. test_causal_refinement_recovers_minimal_precondition -- confounded probe log ({A,B,C} co-occur, only B
   causal); assert naive induce gives {A,B,C} and after two refine_from_probe calls it is exactly {B}.
3. test_real_gymact_probes_produce_real_state_deltas -- RealBlindEnvironment against real cube_counter;
   assert a real increment probe returns applicable=True with a real counter delta.
4. test_planner_federation_classifies_real_registered_solvers -- assert >=40 solvers classified SUPPORTED
   from the REAL entry-point group (not a hardcoded list) and that Astar is among them.
5. test_multiple_planners_independently_agree -- run_federation over Astar + at least 2 other SUPPORTED
   solvers on a real recipe; assert >=3 produce PLAN_CANDIDATE and at least 2 agree on an identical plan.
6. FALSIFIER test_advisory_output_cannot_actuate -- passing a raw plan tuple / a PlannerAttempt / an
   AdvisoryCritique to commit_and_execute raises AdvisoryAuthorityRefused whose message contains
   'ADVISORY_AUTHORITY_USED_AS_BEARER'.
7. FALSIFIER test_dangling_ocel_object_reference_is_detected -- hand-build an OCEL dict with an event whose
   relationship objectId is absent from objects[]; assert validate_ocel_referential_integrity returns a
   DANGLING_OBJECT_REFERENCE violation. Also assert a REAL log from a real run has ZERO violations.
8. FALSIFIER test_postcondition_failure_refuses -- commit_and_execute with a deliberately WRONG expected
   dict (e.g. {'counter': 999}) against the real provider; assert the transition standing is REFUSED /
   independently_verified is False. Do NOT assert success.
9. test_zero_step_plan_requires_goal_already_satisfied -- Recipe with empty steps and unmet goal raises
   ValueError; with goal already in initial_facts it is accepted.

RUN FOR REAL: cd ${REPO} && .venv/bin/python -m pytest tests/ecosystem/test_level4_crown_chicago.py -v
Also run: grep -rn "unittest.mock\\|Mock(\\|MagicMock\\|patch(\\|monkeypatch" ${REPO}/tests/ecosystem/test_level4_crown_chicago.py
(must be zero matches).
Report BOTH real outputs verbatim. Fix real failures in the TEST if the test is wrong; if the PRODUCT is
wrong, report it precisely rather than weakening the assertion.

Return: the test file path, the real pytest output, the real grep output, and any real failures.`, { phase: 'Tests' })

return { repair, providers, tests }
