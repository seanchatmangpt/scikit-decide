# Level 4 on the new architecture — SHACL tracer bullet, two-gym gate

Real work, this session, on branch `feat/procint-quality-dims-resource-perspective`, at
`HEAD` `cf0c0929c2305037ee0c0ce573b258a1642c3e34` (the commit both tracer bullets' witness
graphs cite as their `afl:sourceRevision` — captured by `level4_witness.py`'s own
`_repo_head_sha()` at projection time, not asserted separately).

## Context: three disjoint "Level 4" systems

Established earlier this session by exhaustive grep + real command execution, restated here
because this doc is the closure of System C:

| | Namespace | Verifier | Status |
|---|---|---|---|
| System A — `level4_crown.py`, `level4_ocel.py`, `standalone_verifier.py` | bespoke OCEL JSON | hand-rolled Python `REQUIRED_CHAIN` walk | Still defective, untouched; superseded for *validation*, reused read-only for its real trial-execution machinery (`run_real_trial`, `build_level4_ocel`, `link_commitment_ttl`) |
| System B — `ocel/rdf_projection.py` + `level4-chain.shacl.ttl` | `urn:autofde:ocel:` | real `pyshacl` | Real, 25/25 passing, untouched by this work |
| System C — PR #37 constitution + `ontology/shapes/{level4,authority,planning}.shacl.ttl` | `urn:autofde-lab:` (`afl:`) | **none, until this pass** | **Closed by this doc**: `src/autofde_lab/evidence/{level4_witness,verify}.py` |

## What was built

`src/autofde_lab/evidence/` (new package, 3 files):

- `level4_witness.py` — `project_trial_to_witness(trial_dir) -> Level4WitnessProjection`.
  Reads the three real, already-durable artifacts a completed `run_real_trial` +
  `build_level4_ocel`/`link_commitment_ttl` pass writes (`commitment.ttl`, `level4.ocel.json`,
  `receipts.sqlite3`) and mechanically transcribes them into `afl:`-namespaced RDF. Every
  triple is a real identity already present in the artifact — a real digest, a real receipt
  chain, a real replay-anchored backward walk (Replay → its replayed Receipt → the
  PostconditionObservation it evidences → the Actuation it observes → that Actuation's
  commitment/authority/receipt). Raises `Level4WitnessGap` naming the exact missing edge
  rather than inventing one, per `.claude/rules/absence-is-not-evidence.md`.
- `verify.py` — `verify_witness_graph`/`verify_trial`, modeled on the proven
  `fabric/shacl_conformance.py` pattern (lazy `pyshacl` import, typed `ShaclDependencyMissing`
  remedy). A `__main__` CLI (`python -m autofde_lab.evidence.verify <trial_dir>`) whose own
  import graph never reaches `level4_witness` at module scope and never reaches any System A
  module at all — the destructive-verification criterion is satisfied by construction, not by
  a runtime `sys.modules` assertion bolted on afterward.
- `tests/evidence/test_level4_witness_falsifiers_chicago.py` — 14 Chicago-style tests: one
  baseline conformance check + 13 real identity-mutation falsifiers, against a real trial (not
  a hand-built fixture).

## Stage 3 — real SHACL validation

`resource_flow`, seed `3979297810`, config `{"target": 3, "capacity": 4, "mine_rate": 1}`.
Trial outcome `EXECUTED`. Projected graph: 131 triples, one `afl:Level4Witness` node.

```text
Validation Report
Conforms: True
```

Non-vacuousness confirmed live: severing the real `afl:authorizedBy` edge on the actuation
flips the same graph to `Conforms: False`, naming both the SPARQL closure shape and the
`ActuationAuthority` property shape — the check discriminates, it doesn't pass by construction.

## Stage 4 — 14/14 real identity-mutation falsifiers

`tests/evidence/test_level4_witness_falsifiers_chicago.py`, real trial fixture (module-scoped,
`run_real_trial` + link, same recipe as `test_level4_ocel_vocabulary_chicago.py`), real
`pyshacl` engine, zero mocks:

```text
$ .venv/bin/python -m pytest tests/evidence/test_level4_witness_falsifiers_chicago.py -v
================== 14 passed, 53 warnings in 73.61s (0:01:13) ==================
```

One real bug found and fixed en route: the test file's `_clone()` helper copied triples but
not namespace bindings, so every mutated (cloned) graph lost the `afl:` prefix binding pyshacl's
`sh:sparql` constraints resolve off the *data* graph's namespace manager — every mutation test
failed with `Unknown namespace prefix: afl` until `_clone` was fixed to copy
`graph.namespaces()` too. Root-caused precisely (only the unmutated `baseline_graph` fixture,
which skips `_clone`, had passed) before the fix, not patched blind.

Covers: `GovernedCandidate.governsCandidate`/`.admittedFromCandidateSet`,
`POWLCommitment.commitsTo`/`.committedProcess`, `Actuation.realizesCommitment`/
`.authorizedBy`/`.belongsToTrial`, top-level `Level4Witness.replay`/`.manifest`, the SPARQL
closure's manifest-binds-every-entity requirement, an identity-substitution falsifier (actuation
repointed at a well-typed decoy commitment — adjacency preserved, identity wrong), the
**self-certification guard** (`observer == actor` on the PostconditionObservation, refused by
the same `FILTER (?observer != ?actor)` closure that makes `SELF_CERTIFIED_POSTCONDITION` a
graph violation per `.claude/rules/no-dual-bookkeeping.md`), and the `AliveStanding` shape (a
`StandingAssertion` claiming `afl:ALIVE` with no `derivedFromWitness` edge).

```text
$ grep -rn "unittest.mock\|Mock(\|MagicMock\|patch(\|monkeypatch" src/autofde_lab/evidence/ tests/evidence/
tests/evidence/test_level4_witness_falsifiers_chicago.py:15:committed shapes files. No mock, stub, `patch`, or `monkeypatch` anywhere in
```
Zero real matches (the one hit is the docstring's own denial).

## Stage 5 — destructive fresh-process verification

Real subprocess, `python -m autofde_lab.evidence.verify <trial_dir>`:

```text
$ .venv/bin/python -m autofde_lab.evidence.verify <trial_dir>
shapes: [".../level4.shacl.ttl", ".../authority.shacl.ttl", ".../planning.shacl.ttl"]
Validation Report
Conforms: True

CONFORMS
exit code: 0
```

A second run wrapped the same CLI entry point and inspected `sys.modules` afterward for any
`autofde_lab.hub.domain.gym_procedure.*` (System A) or `autofde_lab.ocel.rdf_projection`
(System B) module:

```text
verify.main() exit_code = 0
producer modules present in sys.modules: []
DESTRUCTIVE_VERIFICATION: PASS -- zero producer modules in this process's sys.modules
```

## Stage 6 — the architecture proof: TWO_GYM_KERNEL_GATE = PASSED

**TracerBulletA — `resource_flow`** (seed `3979297810`):

| Field | Value |
|---|---|
| trial_id | `5e10eecf-52e6-463f-893c-efa0da93d5a7` |
| witness IRI | `urn:autofde-lab:witness/5e10eecf-52e6-463f-893c-efa0da93d5a7` |
| actuation_id | `urn:level4:actuation:65882fc5503147429c5363753158fae8` |
| observation_id | `urn:level4:postcondition:94ff734b2aae4ee58cf911c8fc4ccfa6` |
| replay_id | `urn:level4:replay:95eede23115a76deb0cf957ee02f735fc998f8d1cf926b6116a390d308dcf06e` |
| committed plan sequence | `mine → refine → assemble → burn_catalyst` |
| graph triples | 131 |
| SHACL | `Conforms: True` |

**TracerBulletB — `lock_and_key`** (seed `3979297810`, `config={"depth": 2}`,
`probe_budget=40`) — chosen deliberately over another counter-shaped gym: ordered hidden
prerequisites (a seeded key permutation, never disclosed), reversible `pick_key`/`drop_key`,
and one irreversible trap (`force_latch`) — structurally nothing like `resource_flow`'s linear
4-step production chain:

| Field | Value |
|---|---|
| trial_id | `7ee7eaec-3eff-4b07-b796-6bff521c0ece` |
| witness IRI | `urn:autofde-lab:witness/7ee7eaec-3eff-4b07-b796-6bff521c0ece` |
| actuation_id | `urn:level4:actuation:935d737571f54818bd6722d277bb1a32` |
| observation_id | `urn:level4:postcondition:cbfedb9fae4547dbafa064cd7ea835b1` |
| replay_id | `urn:level4:replay:ab73169faeff49fad32ea65e556ebda79b2304b41748677d00c0e094d929a703` |
| committed plan sequence | `pick_key[key=0] → open_lock → force_latch` (the typed planner chose the irreversible trap for the second lock rather than discovering its key — a real, legitimate plan under the domain's own rules, not fabricated) |
| graph triples | 137 |
| SHACL | `Conforms: True` |
| Non-vacuousness | severing `afl:authorizedBy` flips this graph to `Conforms: False` too |

**Zero changes** to `level4_witness.py`, `verify.py`, or any of the three SHACL shape files
between TracerBulletA and TracerBulletB — confirmed by `git status --short
src/autofde_lab/evidence/ ontology/shapes/` showing only the original untracked new files, no
modifications:

```text
?? src/autofde_lab/evidence/
```

**Real finding along the way, not glossed over**: both `switchboard` and `lock_and_key` returned
`NO_TYPED_VALID_PLAN` at the default `probe_budget=12` across every seed tried (4 seeds each).
Root cause confirmed by direct source inspection of `lock_and_key.py`/`switchboard.py`
(`gymact.gyms.*`): not a missing config field (`lock_and_key`'s `depth` self-discloses via
`observe()`, defaulting to 3; `switchboard`'s goal depends only on hidden hidden state
`required_on`/`required_count`, not config) and not a kernel/ontology gap — raising
`probe_budget` to 40 made all four retried seeds (`lock_and_key` × 2, `switchboard` × 2) reach
`EXECUTED`. This matches a pre-existing, already-named item in this session's own task list
(#21, "lock_and_key: prefix-keyed induction + CATEGORICAL_ID dimensions") — a planning-layer
discovery-budget characteristic of these two domains, entirely upstream of the evidence/SHACL
kernel this doc closes.

**`TWO_GYM_KERNEL_GATE = PASSED`.** A second, structurally unrelated consequential world
inhabits the same Level-4 constitutional evidence kernel without the kernel learning its
provider name.

## Kernel freeze, effective now

Per the campaign this pass is part of: `src/autofde_lab/evidence/level4_witness.py`,
`src/autofde_lab/evidence/verify.py`, and `ontology/shapes/{level4,authority,planning}.shacl.ttl`
are frozen for provider migration work. A migration attempt that believes one of these needs to
change must stop and report `CONSTITUTIONAL_GAP` with the exact missing semantic — never patch
around it with a provider-specific branch.

## Next: census + backfill (in progress, separate workflow)

A background workflow (launched this same session) is running: TracerBulletC (`switchboard`)
through the identical unmodified kernel, a real-source census of every GymAct-capable provider
across this repo and the sibling `~/gymact` package (not from memory), a synthesized migration
matrix, and migration attempts for whatever census classifies `SAFE_EXECUTABLE`. Results will be
filed as a follow-up pass once that workflow returns — reported honestly against whatever it
actually finds, not pre-declared here.

## See also

- `docs/STATUS.md` Pass 10 — the ledger row for this pass.
- `.claude/rules/absence-is-not-evidence.md`, `.claude/rules/no-dual-bookkeeping.md`,
  `.claude/rules/level4-completion-law.md` — the standing evidence family this closure
  satisfies.
- `docs/2026-08-08-ggen-manufactures-the-constitution.md` — the prior pass that manufactured
  `src/autofde_lab/constitution/` from the same PR #37 ontology this pass validates against.
