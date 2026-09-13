# 2026-08-08 Level 4 Crown Progress

Experiment record for the Level 4 discovery subsystem on branch
`feat/procint-quality-dims-resource-perspective`. Architecture reference:
`level4-discovery-architecture.md`.

Every claim below is a `technicalStanding` claim in the sense of
`../.claude/rules/standing-law.md`. No component in this subsystem computes
`organizationalStanding`, so `organizationalStanding` is `UNKNOWN` throughout and
`enterpriseStanding` is therefore `UNKNOWN` throughout. Stated once here rather than
repeated per entry.

## Commits on the branch

Newest last:

```text
34d7462  DiscoveredDomain causal IR + discriminating-probe refinement
aef1840  real GymAct-backed BlindEnvironment (cube_counter, cube_container_counter)
070cc3a  real planner-federation inventory + bounded execution
a4f709d  typed state dimensions + full crown chain (commit->execute_verified->OCEL->replay)
b28905c  frozen-crown runner with mechanical anti-cheating enforcement
```

## Measured results

Each entry gives the result, the measurement behind it, and its `technicalStanding`.

**Causal refinement resolves a confound** — `ALIVE`.
Probe log where `{A,B,C}` always co-occur but only `B` is causal. Naive induction gives
`{A,B,C}`; two `refine_from_probe` calls shrink it to exactly `{B}`.

**Planner inventory over the real entry-point group** — `ALIVE`.
Re-run this session against a real `GymProcedureDomain` built from
`agentbench_kg_relation_path.json`: 49 `SUPPORTED`, 8 `UNSUPPORTED:CHECK_DOMAIN_FALSE`,
57 classified total, 0 `UNAVAILABLE`.

**Unsupported solvers, by name** — `ALIVE`.
`AugmentedRandomSearch`, `CGP`, `CIDual`, `DOSolver`, `GPHH`, `PilePolicy`,
`RDDLGurobiSolver`, `RDDLJaxSolver` — each via a real `check_domain()` returning false.

**Federation agreement on a real 7-step recipe** — `ALIVE`.
On `agentbench/knowledgegraph`, `Astar`, `LRTDP` and `EHC` each produced a 7-step
`PLAN_CANDIDATE`, and the three agreed.

**Federation failures recorded, not hidden** — `ALIVE`.
`IW` and `BFWS` failed with a real constructor-signature gap (`state_features` required).
`SimpleGreedy` failed on an observation-type mismatch. Each is a `PlannerAttempt` record.

**Continuous dimension refused, not propositionalized** — `ALIVE`.
On the real live observation `{counter, target, reward, solved}`, `reward` classified
`CONTINUOUS` and the projection reported
`UNREPRESENTABLE:CONTINUOUS_DIMENSION_HAS_NO_SOUND_PROPOSITIONAL_ENCODING`.
No `reward=` atom was emitted.

**Boolean classified before integer** — `ALIVE`.
`solved` classified `BOOLEAN` on the same real observation, because bool is checked
before int.

**Full chain against the real gymact `CubeCounterProvider`** — `ALIVE`.
`independently_verified=True`; `final_state={'counter': 3, 'target': 3, 'reward': 1.0,
'solved': True}`; 7 real receipts in a real `SQLiteReceiptLedger`; OCEL validated against
gymact's own OCEL 2.0 schema with 0 referential-integrity violations; `replay_ledger`
reported 0 mismatches; real `commitment.ttl`, `episode.ocel.json` and `receipts.sqlite3`
written to disk.

**Multi-step `execute_verified` postconditions** — `BUILD_BROKEN`.
The same expected postcondition is checked after every actuation, so intermediate steps of
a multi-step plan are correctly `REFUSED`. Per-step predicted postconditions are the fix;
that repair is in progress.

**Frozen crown run (at least 10 trials)** — `UNKNOWN`. Not executed.

Correction to a prior count carried into this session: the planner inventory was previously
described as 55 registered with 6 unsupported. The re-run above gives 57 classified with 8
unsupported, and the eight names listed are the real output. Use the numbers above.

## Falsifiers

Each falsifier below was observed firing for real this session, producing the typed refusal
named. A falsifier that has never fired is an untested falsifier; these three have fired.

**`ADVISORY_AUTHORITY_USED_AS_BEARER`** — triggered by passing a raw plan tuple directly to
`commit_and_execute` instead of a `PowlCommitment`.

**`CROWN_MANIFEST_TAMPERED`** — triggered by a one-byte edit to the seed in the crown
manifest, detected by `verify_manifest`.

**`SUPPRESSED_TRIAL` and `DENOMINATOR_CHANGED`** — both triggered by reporting an 8-of-10
execution against a 10-trial frozen protocol.

## Not yet established

- **The frozen crown has not been run.** `freeze_crown` / `load_crown` / `verify_manifest` /
  `CrownAttempt` / `CrownRun` exist in `level4_crown_runner.py`, and the tampering falsifier fires,
  but no frozen run of at least ten trials has executed. Standing: `UNKNOWN`.
- **There is no crown score.** None is stated in this document because none has been measured.
  Any score appearing elsewhere for this branch is not derived from a run recorded here.
- **Multi-step verified execution is not working.** See the `BUILD_BROKEN` entry above. Until
  per-step predicted postconditions land, only the single-step case has an executed witness, and
  the 7-receipt chain above must not be read as a general multi-step result.
- **No POWL workflow execution, and no `organizationalStanding`.** See
  `level4-discovery-architecture.md` and `ecosystem-standing.md`.

## Reproduction

The planner inventory result was re-run this session with:

```bash
.venv/bin/python -c "
from pathlib import Path
from autofde_lab.hub.domain.gym_procedure.gym_procedure import load_recipe
from autofde_lab.hub.domain.gym_procedure.planner_federation import classify_registered_solvers
from collections import Counter
recipe = load_recipe(Path(
    'src/autofde_lab/hub/domain/gym_procedure/recipes/agentbench_kg_relation_path.json'))
result = classify_registered_solvers(recipe)
print(Counter(x.status for x in result))
print(sorted(x.name for x in result if x.status != 'SUPPORTED'))
"
```

## See Also

- `level4-discovery-architecture.md` — the architecture reference for this subsystem.
- `STATUS.md` — the in-repo working ledger.
- `ecosystem-standing.md` — the cross-repository standing ledger.
- `../CLAUDE.md` — repository index and standing-law entry point.
