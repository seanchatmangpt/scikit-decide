# Ecosystem standing — scikit-decide inside the Chatman manufacturing chain

Companion to `docs/STATUS.md`, same discipline, wider scope. `STATUS.md` ledgers WIP inside
this repository; this file ledgers the **cross-repository chain** —
`ggen-create → ggen → ggen-legacy`, with `mfw` supplying admission/receipt/replay law and
scikit-decide supplying the search graph.

Every row is a **measured win** (command run this session, output quoted, passed), a
**recorded negative** (attempted, genuinely blocked, blocker named precisely), or
**deferred/scoped** (a plan exists, nothing under it executed). Where this sheet and the code
disagree, the code is the witness.

Last update: **pass 4** (2026-08-08) — a **new, previously unledgered** linkage between this
repo and `~/gymact` (discovery → planning → commitment → bounded actuation → OCEL/receipt/
replay), disjoint from the POWL crown and not moving S1–S7; its frozen ≥10-trial run has **not**
executed. Pass 3 (2026-08-06) — the FDE authority boundary named as a distinct gap; a
new standing axis (technical / organizational / enterprise); a second crown question; RP-8
opened. Everything in pass 3 is **deferred/scoped** except one measured win on
`decision-engine.py`. Pass 2 (2026-08-06) closed RP-2 by a measured build, demoted S3b on a
real SHACL defect, and merged G1/G3. Pass 1 (2026-08-06) was the first session to execute
across the chain rather than describe it; its rows are corrected in place below, never
deleted. **The crown remains `BLOCKED`.**

## Why this file exists

An earlier attempt this session built an isolated domain + A* test inside scikit-decide and
reported it `ALIVE` as a "Chicago test." That test passes, but it *encodes an analogy to* the
manufacturing law rather than exercising it — no sibling repo was touched, nothing was
manufactured, nothing independently verified. It has been demoted to
`tests/domains/python/test_career_admission_unit.py` with an explicit scope warning. The crown
is `tests/ecosystem/test_chatman_chain_chicago.py`, which drives real binaries and real
corpora. It went red on a real defect the moment it was written (EV-1) and is green now only
because that defect was actually fixed — not because the assertion was relaxed.

## Standing by stage

| # | Stage | Owner | Standing | Witness |
|---|---|---|---|---|
| S1 | exemplar → candidate authority | ggen-create | `UNSUPPORTED` | Reverse compiler is **0 lines**; `ontology/` holds only `.keep`. Repo self-declares it: `scan_ontology` → `bootstrap_empty_surface: True`, claim ceiling `ONTOLOGY_SURFACE_INTEGRITY_ONLY`. Its CI/GALL harness *is* real (25/25 tests, 0.26s, real git fixtures) — governance, not payload. |
| S2 | candidate authority → admitted | mfw | `ALIVE` | **Changed twice this pass; the second change retracts the first.** `cargo build -p mfw-planner -p mfw-pcp-cli` succeeds (47.23s, exit 0), committed as `bc1272b2` in `~/praxis`. Engine admission was first recorded `BLOCKED:VALIDATOR_ABSENT` on the claim that *"no VAL binary exists anywhere on this machine."* **That claim was false and is retracted** — it came from a `command -v` search, i.e. `PATH` only, stated over the whole machine. Four exist, one of them vendored inside mfw-planner itself (`~/mfw/mfw-planner/.vendor-val/build/bin/Validate`, Mach-O arm64, VAL Version 4). Registering both roles and running mfw's own gate: **classical** `purpose=classical_candidate`, `executable_digest=blake3:9c1b1943…`, `status=found`, exit 0; **validator** `purpose=independent_validator`, `executable_digest=blake3:0ce0a2e6…`, `validation_status=**valid**`, exit 0. Two distinct pinned executables, distinct purposes, independent verdict — this is admission, not contract conformance. Plan digest `blake3:d5168d9c…` matches the `export-powl` run; domain/problem digests match scikit-decide's independent computation. **Scope**: `engines.toml` + the wrapper are local and uncommitted, so this is reproducible only from that fixture. See RP-2 and pass 3 §6. |
| S3 | plan computation (search graph) | **scikit-decide** | `ALIVE` | Engine runs, produces VAL-format plans. Quoted below. |
| S3b | plan → POWL2 **projection** | **scikit-decide** | `ALIVE` *(projection only)* | **Restored this pass, on real evidence, not restored to the pass-1 claim's basis.** The writer defect (missing `mfwp:implementsAction`, zero `powl2:precedes` edges) was repaired by a concurrent agent before this pass; what this pass adds is the actual missing check — `src/autofde_lab/fabric/shacl_conformance.py` runs `pyshacl.validate()` (a real, independent SHACL engine, not a second hand-written copy of the constraints) against the literal committed `~/mfw/mfw-planner/shapes/powl2.shacl.ttl`. Run and quoted (below): `conforms=True`, 0 violations; the wired test `test_projection_conforms_to_real_pyshacl_validation` passed (not skipped). **Scope**: this manufactures a document; it is NOT execution — see the decisive question. |
| S3c | admitted POWL → **executed** workflow | mfw + **bcinr** (RP-7) | `PARTIAL_ALIVE` | A real POWL executor exists in `~/bcinr` (`execution_v2.rs:129` tick loop, OCEL, BLAKE3, deadlock refusal) — but it is **symbolic** (in-memory state only) and **not wired** to mfw's actuating broker. Three POWL representations, zero converters. Blocks the crown. |
| S4 | manufacture (μ) | ggen | `PARTIAL_ALIVE` | `sync run` executes and self-verifies in CI; `Root Dogfood` 8/8 red at the closure gate. See RP-4. |
| S5 | independent verification | ggen / ggen-legacy | `PARTIAL_ALIVE` | **Changed this pass.** A receipt manufactured this session verified `valid=True`, chain `98e756627c789118`, `outputs=7` under **two** builds, byte-identical — and the verifying build was not the writing build. But only two builds are reachable (`/opt/homebrew/bin/ggen` no longer exists), so EV-1's residual is untested rather than disproven. See EV-1 / RP-1, both still open. |
| S6 | replay / equivalence / sunset | ggen-legacy | `PARTIAL_ALIVE` | 3 compiled verifier binaries execute and emit typed fail-closed refusals; `decision-engine.py` is a real 3-report + customer-flag gate defaulting to REFUSED. Root LSP crate never built, no CI builds it. |
| S7 | recursive bootstrap controller | — | `UNSUPPORTED` | `Blocked → spawn child → manufacture → verify → admit → resume parent` exists **nowhere in code** across all five repos (`mfw`, `ggen`, `ggen-create`, `ggen-legacy`, `bcinr`). Primitives real; orchestration absent. Asserted absent by a test so the claim cannot drift silently. |

**The chain does not close.** `ALIVE` is not claimable for the end-to-end path. S3 and S3b are
genuinely `ALIVE` (S3b's real SHACL conformance is verified this pass — see the S3b row); S1,
S3c and S7 each independently prevent closure — **S3c is the decisive one**, because a plan
that is never executed makes every downstream stage moot.

*Correction, recorded in place.* The pass-1 text here read "S3/S3b are genuinely `ALIVE`". That
is retracted: S3b's output does not satisfy the shapes it claims to target (see the S3b row and
S3b below). S2 no longer belongs in the blocking list — it built this pass.

### The crown condition, stated correctly

The crown is **not** `PDDL → A* → plan file → POWL Turtle`. That path is real and now works,
but it stops one step before the thing that matters. The crown is:

```
ontology-governed capability discovery
  → complete applicable-capability coverage (selected / compared / excluded-with-reason)
  → candidate-plan computation
  → POWL manufacture
  → MFW admission
  → brokered EXECUTION of the whole plan
  → OCEL + receipts at execution time
  → replay
  → verified plan-level standing
```

Measured against that, this session moved the first four steps and proved the fifth-to-ninth
absent. Reporting the crown as anything other than `BLOCKED` would require a projector to
stand in for an executor, which is the specific error this file exists to prevent.

## Pass 4 — NEW LINKAGE: autofde-lab ↔ `~/gymact` discovery/actuation bridge (2026-08-08)

**This section records a linkage that did not previously exist in this ledger.** Before this
pass, `grep -c gymact docs/ecosystem-standing.md` returned `0`: `~/gymact` appears in none of
the five repositories this file has tracked (`~/mfw`, `~/ggen`, `~/ggen-create`,
`~/ggen-legacy`, `~/bcinr`), in no stage row S1–S7, and in no repair plan RP-1…RP-8. Nothing
below continues, strengthens or weakens a prior claim — there is no prior claim to build on.

It is also **disjoint from the POWL crown.** This bridge does not execute a POWL workflow, does
not close S3c, and does not move S1–S7. Reading any row below as crown progress is the exact
projector-for-executor substitution this file exists to prevent.

Every row is a `technicalStanding` claim (`.claude/rules/standing-law.md`).
`organizationalStanding` is `UNKNOWN` for the whole section — no accountable customer
acceptance exists, and no component here computes one. `enterpriseStanding` is therefore
unreachable.

Owner split: this repo owns discovery, planning, and the commitment record; `~/gymact` owns the
environment providers, the episode runtime, and the OCEL 2.0 schema the emitted log is
validated against.

### Per-transition standing

| # | Transition | Owner | Standing | Witness |
|---|---|---|---|---|
| G1 | blind probing → observed transition log | autofde-lab + gymact | `ALIVE` | `level4_gymact_bridge.py`'s `RealBlindEnvironment` drives real GymAct episodes through a subprocess into `~/gymact/.venv` — real interpreter, real provider, no in-process fake. Exercised against `cube_counter` and `cube_container_counter`. |
| G2 | transition log → `DiscoveredDomain` causal IR | autofde-lab | `ALIVE` | `induce_discovered_domain` + `propose_discriminating_probe` + `refine_from_probe`. On a confounded log where `{A,B,C}` always co-occur and only `B` is causal, naive induction gives `{A,B,C}`; two refinement rounds shrink it to exactly `{B}`, by executing probes rather than reading ground truth. |
| G2b | observation → typed state dimensions | autofde-lab | `ALIVE` *(refusal included)* | On the real live observation `{counter:int, target:int, reward:float, solved:bool}`: `reward` → `CONTINUOUS`, and the propositional projection returns `UNREPRESENTABLE:CONTINUOUS_DIMENSION_HAS_NO_SOUND_PROPOSITIONAL_ENCODING` instead of emitting a junk atom; `solved` → `BOOLEAN`. The refusal is the load-bearing part. |
| G3 | discovered domain → candidate plan (federation) | autofde-lab | `PARTIAL_ALIVE` | Real inventory re-measured this pass: **57 solvers registered, 49 `SUPPORTED`, 8 `UNSUPPORTED:CHECK_DOMAIN_FALSE`, 0 `UNAVAILABLE`**, classified by the framework's own `check_domain()` against a real `GymProcedureDomain`. On the real 7-step `agentbench/knowledgegraph` recipe, `Astar`/`LRTDP`/`EHC` each produced an agreeing 7-step `PLAN_CANDIDATE`. `PARTIAL_ALIVE`, not `ALIVE`: `IW`/`BFWS` fail on a `state_features` constructor-signature gap and `SimpleGreedy` on an observation-type mismatch — three real refusals inside the federation, recorded not hidden. |
| G4 | validated plan → commitment record | autofde-lab | `PARTIAL_ALIVE` *(bounded — commitment, **not** POWL execution)* | `independently_validate` → `ValidatedPlan` → `commit` → `PowlCommitment`, writing a real `commitment.ttl`. **This edge manufactures a commitment record. It does not run a POWL workflow, and it is not S3c.** The S3c finding stands unchanged: no component in the portfolio executes a POWL plan end to end. |
| G5 | commitment → actuation (`commit_and_execute`) | autofde-lab + gymact | `PARTIAL_ALIVE` | Real actuation against the real `CubeCounterProvider`: `independently_verified=True`, `final_state={'counter': 3, 'target': 3, 'reward': 1.0, 'solved': True}`. `commit_and_execute` is the **only** actuation path, and it refuses a raw plan tuple with `ADVISORY_AUTHORITY_USED_AS_BEARER`. `PARTIAL_ALIVE` because of the defect in the next row. |
| G5b | per-step postcondition checking inside `execute_verified` | autofde-lab | `BLOCKED:SAME_POSTCONDITION_CHECKED_EVERY_STEP` | `execute_verified` re-checks the **same** expected postcondition after every actuation, so intermediate steps of a multi-step plan are correctly `REFUSED`. Real defect, under repair by a separate agent, **not fixed**. No row above may be read as multi-step actuation working. |
| G6 | execution → OCEL + receipts + replay | autofde-lab + gymact | `ALIVE` *(scoped to the two providers)* | 7 real receipts in a real `SQLiteReceiptLedger`; the emitted `episode.ocel.json` validated against **gymact's own OCEL 2.0 schema** with **0 referential-integrity violations** (`validate_ocel_referential_integrity`); `replay_ledger` → **0 mismatches**. Real artifacts on disk: `commitment.ttl`, `episode.ocel.json`, `receipts.sqlite3`. |
| G7 | frozen ≥10-trial crown run | autofde-lab | `UNKNOWN` | **Not executed.** `level4_crown_runner.py` exists and its tamper falsifier is real (`CROWN_MANIFEST_TAMPERED` fires on a one-byte seed edit; `SUPPRESSED_TRIAL` + `DENOMINATOR_CHANGED` fire on an 8-of-10 execution against a 10-trial manifest), but no frozen run has produced a manifest-verified result set. **Level 4 is not complete.** |

### Bounds on the above

- Scoped to two GymAct providers (`cube_counter`, `cube_container_counter`). Nothing
  generalizes to other providers without executing them.
- The DSPy advisory layer runs a deterministic fallback path unless an LM is configured; no
  LM-backed run was executed, so no claim is made about LM-driven discovery quality.
- An earlier in-session solver-inventory figure of "55 registered / 6 `UNSUPPORTED`" is
  **retracted**: the re-run this pass measures 57 and 8. Kept visible per this file's rule that
  corrections are written beside the claim, not edited away.

### Falsifiers for this section

- A frozen ≥10-trial crown run that does not reproduce → G7 stays `UNKNOWN`, and G1–G6 are
  single-shot observations rather than a rate.
- Any reading of G4 as POWL workflow execution → refuted by S3c and by
  `.claude/rules/ecosystem-boundary.md`'s projection-is-not-execution rule.
- Multi-step `execute_verified` succeeding today → would contradict G5b; it does not.

## Pass 3 — the FDE authority boundary (2026-08-06)

All of this section is **deferred/scoped** — a gap named, a vocabulary written, a repair plan
opened — with exactly one exception, the measured win in §"The sunset gate already splits the
two standings" below. Nothing else here has executed. The FDE rail does not exist.

### 1. This is a newly-named gap, not a newly-solved one

The technical chain and the enterprise chain are **different closures**. Everything above
ledgers the technical one: authority → plan → geometry → schedule → manufacture →
verification. The enterprise closure is customer reality → admitted customer model → bounded
organizational authority → technical consequence → accountable acceptance → adopted
organizational capability.

Closing G1, G2 and G3 would close the technical chain and would leave every one of these
predicates unanswered, because each is **customer-relative** and none is computable by the
system that would be asking:

1. Is the observation materially complete for the decision it will support?
2. Does this person hold the authority they are exercising?
3. May this system touch that production environment?
4. Does the implementation satisfy the actual operating obligation, not merely the spec?
5. May the predecessor be retired?
6. Will the organization adopt the new process?

Naming these does not advance them. This section exists so that a future pass reading a fully
green technical ledger does not conclude the enterprise consequence closed.

### 2. A standing axis: technical / organizational / enterprise

| dimension | means | today |
|---|---|---|
| `technicalStanding` | manufactured, verified, replayed as specified | the subject of every row in both ledgers |
| `organizationalStanding` | accountable customer authority validated, granted, accepted, owned, authorized | `UNSUPPORTED` — nothing computes it |
| `enterpriseStanding` | **both** of the above admitted | `UNSUPPORTED` by construction |

**Every existing standing claim in `docs/STATUS.md` and in this file is a `technicalStanding`
claim.** `S3 = ALIVE` means the engine runs, not that any customer authorized anything. Re-reading
a technical `ALIVE` as enterprise standing is the same error class as reading a green in-repo
row in `STATUS.md` as a closed cross-repo consequence — the error this file's scope note already
guards against, one level up.

`enterpriseStanding` is `ALIVE` only when both other dimensions are admitted. No component
computes `organizationalStanding` today, so no `enterpriseStanding` claim is currently
constructible by any component in the portfolio.

### 3. The sunset gate already splits the two standings — **measured win**

The technical/organizational split is **not a new idea imposed on the architecture**. It
already exists, at exactly one point, in real running code.
`~/ggen-legacy/appliance/bin/decision-engine.py` (38 lines) was driven directly this session —
not simulated — in a temp portfolio, with the technical evidence held **constant and fully
green** in every run (`verifier.standing=ALIVE`, `replay.status=REPLAY_MATCH`,
`cross_check.standing=ALIVE`, all seven `capability_closure` counters zero). Only
`customer_authorized_retirement` varied:

```text
customer_authorized=true     {"release_admitted": true, "sunset_admitted": true}
customer_authorized=ABSENT   {"release_admitted": true, "sunset_admitted": false}
customer_authorized=STRING   {"release_admitted": true, "sunset_admitted": false}
customer_authorized=false    {"release_admitted": true, "sunset_admitted": false}
```

Three separable findings:

1. **`release_admitted` is `true` in all four rows.** Release is the purely technical admission
   and it closes every time; `sunset_admitted` flips solely on the organizational predicate. The
   two dimensions are already independent variables here.
2. **Fail-closed is real, not incidental.** The `"true"`-as-**string** row returns
   `sunset_admitted: false`, because `m.get("customer_authorized_retirement") is True` rejects a
   truthy string. A JSON config that *looks* approved is refused. That is the difference between
   a gate and a checkbox.
3. **Row 1 is a control, not a success.** `sunset_admitted: true` there is evidence that a
   boolean set to `true` satisfies a boolean check — nothing more. It proves the other three
   rows are refusals rather than a gate that never passes. It is **not** evidence that
   organizational admission works.

**What is missing is narrower than "no FDE rail exists."** The gate's *shape* is correct and must
be preserved and invoked, never replaced by a local simulation. The defect is that
`customer_authorized_retirement` is a naked boolean with **no referent**. A true value there is
currently unattributable. For the flag to carry organizational authority it must resolve to a
record naming all of: a named authority holding the retirement decision right; the specific
predecessor identity being retired; the specific, independently verified replacement identity;
the evidence set actually reviewed; a timestamp; and the scope conditions under which the grant
holds. Absent that record, writing `true` is an assertion by whoever wrote the JSON.

RP-8 is therefore scoped as **"give the existing boolean a referent"**, not "build an authority
system." An earlier pass in this file oversized RP-7 the same way ("build a POWL execution
controller", when the driver already existed) and had to retract it; the correction is applied
in advance here rather than after.

### 4. The second crown question

The final question above is technical:

> Did a blocked parent cause a child workflow to be planned, executed, manufacture and verify a
> capability, admit it, and resume without unreceipted actuation?

There is a second, and it is not a refinement of the first:

> Did accountable customer authority validate the model, grant the bounded transition, accept
> the verified consequence, assign operating ownership, and explicitly authorize any
> irreversible sunset?

**The crown is closed only when BOTH are yes.** The first is `BLOCKED` (S3c, S7). The second is
**no — and not yet even askable**: no organizational-authority rail has run, and no component
accepts a named customer authority as an input. A future pass that answers the first question
yes and reports the crown closed will have answered half of it.

### 5. New file: `ontology/fde-authority-schema.ttl`

A **hand-authored T-Box** defining the FDE vocabulary: 12 entities, 8 capabilities, 12
relations, and the 3 standing dimensions as first-class terms.

It is **different in kind** from `ontology/autofde-lab-capabilities.ttl`, and the distinction is
stated in its own header. The capability graph is an **A-Box of standing claims** — what is true
right now — generated from entry points plus a live import probe, and its credibility rests on
the probe being the same act as the use; hand-editing it is a defect and is now blocked by a
`PreToolUse` hook. The FDE schema is a **T-Box**: what kinds of thing exist and how they relate.
Hand-authoring a vocabulary is legitimate; hand-authoring a standing claim is precisely what the
generator exists to prevent.

**Nothing in it is `ALIVE`.** Every capability carries `UNSUPPORTED` (nothing implements it) or
`UNKNOWN` (implementation status genuinely unobserved) with an evidence string. A term existing
in that file is not evidence that anything implements it.

### 6. mfw refuses a planner that is its own witness — **recorded negative**

Attempted this pass: register the scikit-decide engine in mfw's `classical` role and admit it
through mfw's own gate. No console script is needed — `program` is the venv python, with
`args = ["-m", "autofde_lab.fabric.pddl_engine", "{domain}", "{problem}", "{plan}"]`,
`version_args = ["-m", "autofde_lab.fabric.pddl_engine", "--help"]`, `output_mode = "file"`,
`success_codes = [0]`. The real binary was then run:

```text
$ mfw-planner probe classical
Error: InvalidEngineConfiguration("exactly one independent validator role is required; observed 0")
```

A search for a validator binary (`Validate`, `validate`, `val`, `VAL`) found **none on this
machine**.

**mfw refuses to load a planner-only configuration at all** — not at solve time, not as a
warning, but at *config load*. A planner cannot be registered without exactly one **independent**
validator role alongside it. The anti-self-attestation law is therefore **structurally enforced,
not conventional**: the architecture will not permit a planner to be its own witness even when
every other input is valid.

That reframes this whole pass. Independent verification is enforced at **both ends** of the
chain already — at engine admission here, and at sunset admission in §3's
`decision-engine.py` result. The FDE authority boundary is the **third instance of an existing
pattern**, not new architecture being imposed. That is both the more accurate reading and the
more defensible one.

**Accuracy bounds, so this is not over-read:**

- `~/mfw/mfw-planner/engines.toml` was **not modified**. The registration was written in a temp
  directory (mfw reads `engines.toml` from cwd) and is uncommitted.
- It is **not** verified that the engine would pass admission once a validator exists — only
  that it cannot reach that check today. No predicted pass is recorded.
- The blake3 executable pin was **never exercised**: config validation refuses before any digest
  is computed.

## Measured wins

### S3 — classical PDDL engine (new capability, fills a real vacancy)

`src/autofde_lab/fabric/pddl_engine.py`. Satisfies mfw's *existing* external-engine contract
(`mfw-planner/src/config.rs`: roles are a closed set; `classical` + `output_mode="file"`
requires exactly `{domain} {problem} {plan}`) — the reference case mfw already registers is
`fast-downward.py`, so a Python engine in this slot is the norm, not a novelty.

```
$ uv run python -m autofde_lab.fabric.pddl_engine --help
usage: autofde_lab-classical-engine <domain.pddl> <problem.pddl> <plan-file>

$ uv run python -m autofde_lab.fabric.pddl_engine \
    tests/domains/python/pddl_domains/blocks/domain.pddl \
    tests/domains/python/pddl_domains/blocks/probBLOCKS-3-0.pddl /tmp/blocks.plan
autofde_lab-classical-engine: plan found, 4 step(s), cost 4 -> /tmp/blocks.plan

$ cat /tmp/blocks.plan
(unstack a b)
(put-down a)
(pick-up b)
(stack b c)
; cost = 4 (unit cost)
```

Format matches the real committed artifact `~/mfw/runs/ticket-10/work/candidate.plan`.

### S3b — POWL2 projection

`src/autofde_lab/fabric/powl.py`. PDDL selects among admitted transitions; POWL is the process
geometry that transition becomes (`CHATMAN-EQUATION.md`, "Recursive Process Manufacture").
Emits the vocabulary of the real committed `~/mfw/runs/ticket-10/plan.powl.ttl`:

```turtle
<urn:skdecide:plan/plan> a powl2:Model, powl2:PartialOrder ;
    mfwp:domainDigest "blake3:b11c0b44765957b790404ec9c8ec5e8e5b590353dcc98a50f794a469314406e2" ;
    mfwp:problemDigest "blake3:8a43b3cd62188ce5f366de4f2175825ae3d5c10f69a908115a26ef579ba7e143" ;
    mfwp:projection "total-order" ;
    mfwp:activityCount "4"^^xsd:integer .
```

Digests are **real blake3** via `b3sum`. The projector raises `DigestUnavailable` rather than
emitting another algorithm under a `blake3:` label — a forged identity would mismatch mfw's
`PLANNER_ENVIRONMENT_DRIFT` check with a misleading reason.

**Independent cross-check — measured win, pass 2.** With `mfw-planner` now building (RP-2),
`mfw-planner export-powl` was run from `~/mfw/mfw-planner` (the directory holding
`engines.toml`) over the same blocks domain. It computed:

```text
domain_digest   blake3:b11c0b44765957b790404ec9c8ec5e8e5b590353dcc98a50f794a469314406e2
problem_digest  blake3:8a43b3cd62188ce5f366de4f2175825ae3d5c10f69a908115a26ef579ba7e143
```

**Byte-identical** to the digests quoted above, which `powl.py` produced independently. Two
implementations in two languages agreeing on blake3 identity is a real cross-check, not a
self-report — it is the one part of S3b that is unambiguously `ALIVE`.

Minor mismatch, recorded so it is not rediscovered: mfw writes `"projection": "total_order"`
(underscore); `powl.py` writes `mfwp:projection "total-order"` (hyphen). Cosmetic today,
load-bearing the moment either string is compared rather than displayed.

**Defect from a prior pass — since repaired, and now independently checked, this pass.**
A concurrent agent had already added `mfwp:implementsAction`, `prov:wasDerivedFrom`, and
real `powl2:precedes` edges to `project_plan_to_powl` by the time this pass started
(`mfwp:projection` is still the literal `"total-order"`, matching mfw's own Turtle emitter —
see the "minor mismatch" note above, which is about the JSON receipt field, not this Turtle
literal). What had never been done — the condition this doc itself set for S3b to return to
`ALIVE` — was running the real shapes against the real output. That gap is now closed, not by
hand-reimplementing the shapes again (the mistake that let the original defect ship
undetected), but by running an independent, spec-compliant SHACL engine:

`src/autofde_lab/fabric/shacl_conformance.py` (new this pass) calls
`pyshacl.validate(turtle, shacl_graph=<~/mfw/mfw-planner/shapes/powl2.shacl.ttl>, ...)` —
`pyshacl`/`rdflib` are real, installed dependencies in this repo's own `.venv` (declared
under the `ofmf` extra; `powl.py`'s existing docstring claim that `rdflib` "is not
installed" describes the core package's dependency list, not this environment). Run for
real, this pass, against the same blocks-world plan quoted above:

```text
$ .venv/bin/python -c "
from autofde_lab.fabric.powl import project_plan_to_powl
from autofde_lab.fabric.shacl_conformance import check_shacl_conformance
turtle = project_plan_to_powl(
    ['(unstack b a)', '(put-down b)', '(pick-up a)', '(stack a c)'],
    base_iri='urn:skdecide:plan',
)
result = check_shacl_conformance(turtle)
print('conforms=', result.conforms)
print('violation_count=', result.violation_count)
print(result.report_text)
"
conforms= True
violation_count= 0
Validation Report
Conforms: True
```

And the same check wired into the test suite —
`tests/ecosystem/test_powl_roundtrip_chicago.py::TestShaclConformance::
test_projection_conforms_to_real_pyshacl_validation` — `1 passed`, not skipped (skips only
if `~/mfw`'s shapes file or `pyshacl` itself is absent, named `BLOCKED:MFW_SHAPES_ABSENT`/
`BLOCKED:PYSHACL_ABSENT`, never substituted). This is a real conformance verdict from a real
engine against the real committed shapes, run and quoted — the exact bar this entry set.
**S3b returns to `ALIVE`.**

### S3c — silent-wrong-answer refusal (the most important behavior added)

scikit-decide's PDDL backend **parses** `:derived-predicates`, `:constraints` and
`:preferences` and then does not implement them. Verified: `grep -rn "derived"
cpp/src/hub/domain/pddl/semantics/` → **zero hits**. Derived atoms are never true, so any
action gated on one is silently never applicable. `GoalChecker::is_goal` never reads
`problem->get_constraints()`. `Preference::holds` returns the inner formula, making a *soft*
preference a *hard* constraint. **None of these raise.**

Without a gate, the engine would emit a confident, plausible, wrong plan — strictly worse than
refusing, because a wrong plan can be admitted downstream. The engine now refuses:

```
$ uv run python -m autofde_lab.fabric.pddl_engine \
    ~/ggen-legacy/planning/v26.8.1/domains/ggen-v2681-core.pddl \
    ~/ggen-legacy/planning/v26.8.1/problems/01-governance.pddl /tmp/gl.plan
autofde_lab-classical-engine: REFUSED: UNSUPPORTED_REQUIREMENT:
:derived-predicates,:constraints,:preferences declared by .../ggen-v2681-core.pddl.
scikit-decide's PDDL backend parses these but does not implement them; planning would
silently return an incorrect plan. Refusing rather than emitting one.
$ echo $?
2
```

This matters concretely for that corpus: `admit-sunset`'s precondition is the derived predicate
`sunset-safe`. Under the unimplemented semantics it would be unreachable — a planner would
report "no sunset possible" with total confidence and no error.

### S3d — two latent defects found in ggen-legacy's corpus

Parsing that corpus **for the first time** surfaced defects `verify_planning.py`'s
paren-balance-and-substring check cannot detect:

1. `ggen-v2681-core.pddl@50:29` — `variable '?x' unknown to the current parsing context`,
   inside the `(:derived (fully-evidenced ?x - object) ...)` body. The `:derived` head's
   parameters are not bound into body scope. Attribution is genuinely ambiguous between a
   corpus bug and a scikit-decide parser gap; consistent with derived-predicate support being
   absent end-to-end. **Unresolved — needs a second parser to disambiguate (RP-3).**
2. `10-legacy-sunset.pddl@5:3` — `object 'preserved' already existing in problem`.
   **Unambiguously a corpus bug**: the domain declares `preserved` in
   `(:constants ... preserved subsumed replaced archived refused unknown-disposition -
   disposition)`, and the problem redeclares it in `(:objects ...)`. PDDL forbids this.

### S8 — ontology-governed capability discovery and coverage

`ontology/autofde-lab-capabilities.ttl`, generated by `src/autofde_lab/fabric/ontology.py` from
entry points + a live import probe + `get_domain_requirements()` MRO derivation. **83
capabilities** (26 domains, 57 solvers, all `ALIVE` here) plus 16 PDDL requirements, 4 of them
`UNSUPPORTED` — encoding the silent-wrong-answer hazard as a first-class fact rather than a
constant in one module.

`src/autofde_lab/fabric/coverage.py` classifies **every** declared solver against a concrete
domain. Measured over `CareerAdmission`, all 57 accounted for:

| disposition | n | detail |
|---|---|---|
| `tied_optimal` | 26 | ran, all reached cost 3 — a tie is reported as a tie, not 26 "wins" |
| `excluded` | 8 | `UNMET_DOMAIN_CHARACTERISTICS`, naming the exact missing characteristic |
| `failed` | 23 | `REQUIRES_OTHER_DOMAIN_TYPE` 8, `REQUIRES_CONFIGURATION` 7, `DID_NOT_CONVERGE` 5, `RUNTIME_ERROR` 3 |

Applicability is derived (ontology requirements evaluated by `isinstance`), and comparison is
**measured** — necessary because `match_solvers(..., ranked=True)` accepts the flag and
ignores it, so an unmeasured "dominated" verdict would be an empty claim.

**Limitation this surfaced.** `get_domain_requirements()` describes the *domain
characteristics* a solver needs but says nothing about its *constructor* requirements. Seven
solvers are ontology-applicable yet not runnable with defaults (`IW`, `RIW`, `RayRLlib`,
`StableBaseline`, `UPSolver`, `MAHD`, …). That is a distinct, actionable category —
`REQUIRES_CONFIGURATION` — not the same as inapplicable, and it is now machine-readable.

### S4 — a real bounded ggen manufacture in a clean workspace (pass 2)

`~/ggen/examples/star-toml-verify` was copied into a temp workspace, `[packs]` repointed at an
absolute `~/ggen/packs/star-toml-pack`, the pre-existing generated outputs deleted, then real
`ggen sync run --format json` — **not** `--dry-run`:

```text
written  : 7
   + docs/star_toml/CARGO_DEPENDENCIES.md
   + src/star_toml_config.rs
   + tests/star_toml_config_proof.rs
   + tests/star_toml_config_sparql_derived_proof.rs
   + src/star_toml_lib_wiring.rs
   + docs/star_toml/admission.md
   + docs/star_toml/telemetry.md
skipped  : 0
graph_hash: a3b0b66476ef6c5afcfeddb8...
exit=0
```

Files confirmed on disk afterwards. **Determinism cross-check**: an earlier run of the *same*
workspace with the outputs still present returned `written: []` and all 7 entries
`"skipped: unchanged: content identical"` — with an **identical** `graph_hash_hex
a3b0b664...`. Same graph hash across both the writing and the no-op path.

This is direct evidence for **RP-4**, reproduced outside `~/ggen`'s own root: the no-op run is
exactly the shape RP-4 records — `sync run` succeeds while reporting zero generated outputs,
because the "unchanged: content identical" admission path never registers ownership. **RP-4 is
not closed by this**; the run strengthens its evidence and proves it is not root-specific.

### S5 — independent verification of a manufacture performed this session

That manufacture wrote `.ggen-v2/receipt.json` (4784 bytes) and `.ggen-v2/receipt-log.jsonl`
(56675 bytes). `ggen receipt verify --format json`, run from the temp workspace under two
builds:

| build | result |
|---|---|
| `~/.cargo/bin/ggen` | `valid=True chain=98e756627c789118 sig_valid=True outputs=7` |
| `~/ggen/target/debug/ggen` | `valid=True chain=98e756627c789118 sig_valid=True outputs=7` |

Byte-identical chain hash from both, and **the verifying build is not the writing build** — so
this is genuine independent verification, not self-attestation. It is also a *fresh* receipt,
distinct from the pre-existing `~/ggen/.ggen-v2/receipt.json` that EV-1 concerned.

**Caveat, and it keeps RP-1 open.** `/opt/homebrew/bin/ggen` **no longer exists on this
machine**, so only two builds were reachable. EV-1's residual risk — a `brew link` reintroducing
the stale Cellar binary and silently restoring the disagreement — is therefore **untested here,
not disproven**. Two agreeing builds out of two reachable is weaker than three out of three.

### Crown test

```
$ uv run pytest tests/ecosystem/ tests/domains/python/test_career_admission_unit.py
27 passed
```

EV-1 was red here earlier in the session and is now green because the defect it found was
actually fixed (see below), not because the assertion was weakened.

## What this session changed epistemically

Not "the project looks more achievable." The change is that an **undefined architectural
absence became a bounded integration problem with one genuinely hard component**.

Before: *"implement recursive multifractal workflow manufacture"* — a description that bundled
six unresolved questions (does a scheduler exist? a broker? can anything actuate? is there an
execution receipt model? can standing close at plan level? how does a parent resume?). Bundled,
it read as research-scale.

After, the gaps separate and their characters differ sharply:

| Gap | Condition | Character |
|---|---|---|
| **G1+G3 ingestion-and-authorization** | the runtime's POWL requires authorization metadata no planner can produce | **genuine architecture** |
| **G2 scheduling** | `bcinr-powl` already supplies the bounded loop | existing capability, needs composition |
| **RP-6 recursion** | no child manufacture / admission / attachment / resumption | higher-order orchestration |

**Correction, recorded rather than edited away.** Pass 1 split this into *G1 representation*
("conventional integration") and *G3 actuation* ("genuine architecture"). That split is
**retracted: G1 and G3 are one gap.** Evidence, measured this pass:

- `mfw-planner export-powl` emits **JSON**, schema `urn:mfw:powl:document:v2` — a nested tree
  with `model.children[]` and explicit `order: [{before, after}]` edges. That schema string
  occurs **only** in `mfw-planner` (`solve_rdf.rs:407`, `plan.rs:173`, `powl.rs:439`, plus two
  tests) and **never** in `mfw-rmcp`.
- `mfw-rmcp`'s ingested shape (`mfw-rmcp/src/powl.rs:38-105`) is structurally different: a
  **flat** `nodes: BTreeMap<String, PowlNode>` with `root: String`, each node carrying
  `predecessors`, `read_set`, `write_set`, `authorization_class`, and
  `NodeKind::Action { operation: NativeOperation }`.

The decisive part is not the shape mismatch — it is that the runtime's POWL demands
`authorization_class`, `read_set`, `write_set`, and a concrete `NativeOperation` drawn from a
closed **3-variant** algebra (`WriteLevel5Pack`, `RecordLevel5Evidence`, `GenerateRmcpModule`).
**A planner has no way to produce any of those.** So no planner-emitted plan becomes
runtime-ingestible POWL without a step that assigns authorization classes and binds each
activity to a native operation — and *that step is exactly* the "what maps a POWL activity to
an executable operation?" question filed under G3. A format converter alone cannot close G1,
because the target format's required fields are authorization decisions. Ingestion and
actuation are the same problem; treating them as two made the cheaper one look independently
closeable, which it is not.

The accurate diagnosis is **not** "mostly unbuilt." It is **densely implemented but
operationally discontinuous**: planners without execution, scheduling without actuation,
actuation without plan traversal, POWL projections without canonical ingestion, receipts
without complete plan coverage, standing without N-of-N closure, capability implementations
without an ecosystem-wide capability authority.

That is **connective-tissue debt**, and it is the failure mode component-centric architecture
structurally cannot see: every repository can truthfully demonstrate a local capability while
the enterprise-level consequence remains impossible. The relevant unit of correctness is not
the component, it is the closed causal chain.

Honest current claim:

> The core planning, scheduling, manufacturing, authorization, evidence, and replay primitives
> exist. The remaining work is canonical representation, brokered plan-scale actuation,
> complete standing closure, and recursive parent-child orchestration. **The system is
> closable; the crown is not yet closed.** The unknown was whether the machinery existed — it
> does. The open question is whether it can be lawfully connected without collapsing planning,
> authority, actuation, and verification into self-attestation.

### Why the ontology is an epistemic control, not documentation

This session produced a false ecosystem-wide claim — *"no POWL executor exists"* — from a
search that had never looked at `~/bcinr`, which contains one. The error was not carelessness
about a single repo; it is structural. **Any architecture conclusion drawn from "whichever
repositories the investigator happened to inspect" is unsound by construction.**

An ontology makes such a claim mechanically falsifiable. The question stops being "have I
looked everywhere?" (unanswerable) and becomes "which admitted capability implements POWL
scheduling?" (a query). The ecosystem-level ontology this implies must model repositories,
crates, capabilities, **renamed or absorbed components** (`bcinr-powl-receipt` →
`bcinr-powl::receipt` is exactly the case that broke a build and hid an executor),
implementations, interfaces, I/O, standing, evidence, dependencies, compatible and
incompatible representations, authoritative owners, available actuators, planners, schedulers,
and verification rails.

`ontology/autofde-lab-capabilities.ttl` is the first instalment — scoped to this repo, generated
from entry points, and asserted against the live registry so it cannot drift. The
ecosystem-wide graph is not yet built and is recorded here as scoped, not done.

**The same failure reproduced inside this session — the strongest available evidence for the
above.** Two of this session's own investigation agents, given the same question about
`EvaluateSunsetStanding`, returned contradictory answers:

- Agent A: *"no executable exists — only prose in three docs."* It had searched
  scikit-decide's `docs/` only.
- Agent B found `~/ggen-legacy/appliance/bin/decision-engine.py` (38 lines, confirmed), which
  implements the real gate:
  `release = verifier.standing=="ALIVE" and cross_check.standing=="ALIVE" and
  replay.status=="REPLAY_MATCH"`, then a 7-field zero-closure check, then
  `sunset = release and closed and m.get("customer_authorized_retirement") is True` —
  fail-closed, and the `is True` deliberately rejects a truthy string.

This is the `~/bcinr` miss again, one pass later, with the lesson already written down in this
very file. A negative finding is exactly as broad as the search that produced it, and neither
good faith nor a recorded prior instance prevents the recurrence. Only a queryable authority
does — which is the argument for the ecosystem-wide ontology, not a stylistic preference.

**Third instance, same pass — and this one cost a standing row.** S2 was recorded
`BLOCKED:VALIDATOR_ABSENT` on the claim *"no VAL binary exists anywhere on this machine."* The
search behind it was `command -v Validate validate val VAL` — `PATH` only — and the conclusion
was stated over the whole filesystem. **Four exist**, and the most relevant one is vendored
inside the very component under test: `~/mfw/mfw-planner/.vendor-val/build/bin/Validate`
(Mach-O arm64, VAL Version 4), alongside `~/VAL/build/bin/Validate`,
`~/ferroplan/benchmarks/.val/VAL/build/bin/Validate`, and `~/pigsty/bin/validate`. Registering
it took S2 from `BLOCKED` to `ALIVE` in one step.

The pattern across all three is identical and worth naming precisely: **a search bounded by one
mechanism (one repo, one doc tree, `PATH`) reported as a fact about the world.** The failure is
not insufficient effort — each search was competently executed within its bound. It is that the
bound was not carried into the claim. `UNKNOWN` is the correct standing for "I did not find it
with the method I used"; `UNSUPPORTED` and `BLOCKED` assert absence and require a search whose
bound is stated. Prefer `UNKNOWN` and name the method.

**Phase 0 mitigation, done this session (in this repo, in scope).** `.claude/rules/*.md` now
carry YAML `paths:` front-matter, so a rules file loads only when a matching file is read.
Previously all six loaded unconditionally — verifiable from this session's own system prompt,
which contained all six in full. An `@` import expands at session start, so the earlier
`CLAUDE.md` split reorganised text without reducing context; that is now actually fixed rather
than nominally. The root `CLAUDE.md` additionally documents that cross-repo work requires
`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` alongside `--add-dir`, because `--add-dir`
grants **file access but not instruction loading** — the exact condition under which the
`~/bcinr` miss occurred.

## Capability surface (measured, for the ontology)

Inventoried from `pyproject.toml` entry points — the authoritative registry — and verified by
importing every one in this environment:

- **26 registered domains**, all import OK. `ChatmanCleanSession` is the only one with **no
  extras marker** (pure core). `TPDDLDomain` sits behind the `pddl` extra (needs `z3`).
- **57 registered solvers**, **all 57 import OK** — none `UNSUPPORTED` here. The compiled hub
  is present (`.venv/.../__autofde_lab_hub_cpp.cpython-313-darwin.so`), which is what makes the
  ~35 C++-backed solvers live.
- Applicability is **programmatically derivable**, not a matter of opinion:
  `Solver.get_domain_requirements()` (`src/autofde_lab/solvers.py:85`) derives the requirement set
  from the solver's `T_domain` MRO, and `check_domain` (`solvers.py:123`) tests
  `all(isinstance(domain, req) ...)` plus the `_check_domain_additional` hook.
  `match_solvers(domain, candidates, ranked)` (`src/autofde_lab/utils.py:126`) applies it across
  the whole registry.

Two findings that constrain how a coverage report may be built:

1. **`ranked` is accepted but ignored** — `utils.py:126` carries `# TODO: implement ranking
   heuristic` and always returns a plain list. So "compare alternatives where several
   capabilities solve the same subproblem" cannot be delegated to `match_solvers`; comparison
   must be genuinely measured (run them, compare plans/costs) or the claim is empty.
2. **Failed solver loads surface as `None`, never as an exception** —
   `_load_registered_entry` (`utils.py:94`) swallows and `logger.warning`s. A coverage report
   must therefore treat `None` as positive `UNSUPPORTED` evidence rather than as absence, or a
   silently-unloadable solver would simply vanish from the tally.

These are the mechanisms the ontology must be generated *from*. A hand-written Python list of
capabilities would not be ontology-backed, it would be a decorative catalog that happens to
sit next to one.

## Recorded negatives

### EV-1 — ggen verifier builds disagreed about identical bytes — **FOUND, DIAGNOSED, FIXED**

Found by the crown test (this is what a test that can fail is for). Three binaries, all
self-reporting `26.8.6`, on the same git-tracked, unmodified
`/Users/sac/ggen/.ggen-v2/receipt.json`:

| binary | verdict (before fix) |
|---|---|
| `/opt/homebrew/bin/ggen` | **INVALID** — chain hash mismatch, recomputed `23386d67ba4fe290…` |
| `/Users/sac/ggen/target/debug/ggen` | `{"valid":true,"chain_hash":"918c5b0980…","signature_valid":true}` |
| `/Users/sac/.cargo/bin/ggen` | `{"valid":true,"chain_hash":"918c5b0980…","signature_valid":true}` |

Severity: not a normal test failure. If which build sits on `PATH` determines whether an
artifact is admitted, "independently verified" is not a property of the artifact. The stale
build additionally **misattributed** the cause — *"the receipt's own record fields … were
tampered with — restore from `receipt history`/git"* — which would send an operator chasing a
tampering incident that did not occur. The receipt was unmodified; the verifier differed.

**Root cause — corrected after checking git state.** An earlier draft of this entry called the
homebrew build "stale/out of date." That was wrong and is retracted. `v26.8.6` is the correct
version, and the released binary is a faithful `v26.8.6`:

```
$ cd ~/ggen && git tag -l '*26.8.6*'   -> v26.8.6
$ git rev-list --count v26.8.6..HEAD   -> 37
$ git log --oneline -1                 -> ebb16b657 (branch feat/hygen-parity-e2e)
$ grep -m1 '^version' Cargo.toml        -> version = "26.8.6"
```

HEAD is **37 unreleased commits past tag `v26.8.6`**, on a feature branch, still declaring
`26.8.6` — normal mid-development CalVer practice. The chain-hash computation changed
somewhere in those 37 commits, and `.ggen-v2/receipt.json` was written by that newer code.

So the released verifier is **not malfunctioning**: it correctly rejects a receipt produced by
an algorithm it predates. The real defect is narrower and more serious than "stale install":

> **An unreleased breaking change to the receipt chain-hash algorithm is carried on a feature
> branch with no version discriminator.** Any receipt written by that branch is unverifiable
> by the released tool, and the resulting error blames tampering.

`brew outdated` reports nothing and `brew upgrade` refuses, correctly — the formula's `stable`
genuinely *is* the latest release. There is nothing for homebrew to fix.

**Fix applied** (source rebuild + unlink stale Cellar copy — the receipt was never touched):
```
$ cargo install --path crates/ggen-cli --force     # Replacing /Users/sac/.cargo/bin/ggen
$ brew unlink seanchatmangpt/ggen/ggen             # 1 symlinks removed
$ which -a ggen
/Users/sac/.cargo/bin/ggen
$ cd ~/ggen && ggen receipt verify --format json
{"valid":true,"chain_hash":"918c5b09...","outputs":46,"signed":true,"signature_valid":true}
```
Both reachable builds now return byte-identical verdicts; the crown test went 15p/1f → **17
passed**. `git status --porcelain .ggen-v2/receipt.json` empty — evidence untouched.

**Residual risk, not closed.** The stale binary still exists at
`/opt/homebrew/Cellar/ggen/26.8.6/bin/ggen` and still fails. Any `brew link` or an unrelated
`brew upgrade` could relink it and silently reintroduce the disagreement. RP-1 below is
therefore **still open** — the machine is fixed, the *class of defect* is not.

**Pass-2 update.** `/opt/homebrew/bin/ggen` is now absent entirely, so only two builds are
reachable and they agree (S5 above). That reduces the *reachable* disagreement to zero without
closing RP-1: two-of-two agreeing is a weaker check than three-of-three, and a `brew link`
still reintroduces the third. Fewer disagreeing builds because one became unreachable is not
the same as reconciled builds.

**Stale docstring, recorded not fixed.** `tests/ecosystem/test_chatman_chain_chicago.py:364`
still says the test is *"Left deliberately failing rather than xfail-ed or skipped."* That was
true when EV-1 was red; it is now stale. The test is *conditionally* red — it hard-fails only
when two reachable ggen builds disagree, and skips with `BLOCKED:INSUFFICIENT_VERIFIER_BUILDS`
when fewer than two exist. Needs a one-line docstring correction. Not edited here: `tests/` is
owned by a concurrent agent this session, and leaving the discrepancy recorded is preferable to
leaving it silent.

### RP-2 — `BUILD_BROKEN`: `cargo build -p mfw-planner` — **CLOSED this pass**

The failure below was real and is preserved verbatim as the pass-1 record. It no longer
reproduces; see RP-2 under repair plans for the fix, the retraction of its "one-line" diagnosis,
and the exact residual (uncommitted).

```
error: failed to get `bcinr-powl-receipt` as a dependency of package
       `praxis-graphlaw v26.7.9 (/Users/sac/praxis/crates/praxis-graphlaw)`
    ... which satisfies path dependency `praxis-graphlaw` (locked to 26.7.9)
        of package `mfw-shacl v0.1.0 (/Users/sac/mfw/mfw-runtime/mfw-shacl)`
Caused by: unable to update /Users/sac/bcinr/crates/bcinr-powl-receipt
Caused by: failed to read /Users/sac/bcinr/crates/bcinr-powl-receipt/Cargo.toml
Caused by: No such file or directory (os error 2)
```

Chain: `mfw-planner → mfw-shacl → praxis-graphlaw → bcinr-powl-receipt (absent)`.
`/Users/sac/bcinr/crates/` exists and contains `bcinr-powl`, but **not** `bcinr-powl-receipt`,
referenced by absolute path at `/Users/sac/praxis/crates/praxis-graphlaw/Cargo.toml:41`.
Consequence: mfw's solve → OCEL → receipt path cannot be re-run, so the autofde_lab engine cannot
be admitted through mfw's own admission gate this session. Its *contract conformance* is
tested instead (S3), which is weaker and labelled as such.

### EV-2 — a second dangling absolute path dep, recorded by the ontology and connected to nothing

Fixing RP-2 uncovered the next one immediately. `~/praxis/crates/rust-fable-testbed/Cargo.toml:11`:

```toml
ggen-core = { path = "../../../ggen/crates/ggen-core" }
```

`ls ~/ggen/crates/ggen-core` → `No such file or directory`. ggen deleted the crate.

The point is not the broken dep. It is that **the ecosystem's own ontology already records the
deletion that breaks the sibling build, and nothing connects the record to the build.**
`~/ggen-legacy/ontology/v26.8.1/legacy-capabilities.ttl:21-28` carries
`legacy:legacy_ggen_core_pipeline` with
`ggen:historicalSourceCommit "9cef6e40f (delete) / cbf173f82 (disconnect, PR #255)"`,
`ggen:legacySourcePath "crates/ggen-core/ (deleted; …)"`, disposition `REPLACED`, standing
`UNKNOWN`. A build broke on a fact the portfolio had already written down. That is the
connective-tissue-debt thesis below, demonstrated live rather than argued.

**Scope, stated so this is not over-read.** This does **not** block mfw: mfw pulls
`praxis-graphlaw` only, not `rust-fable-testbed`, and `cargo metadata --format-version 1` in
`~/mfw` exits 0. Recorded negative scoped to `~/praxis`; not a crown blocker. Owner `~/praxis`
(decide whether the testbed follows `ggen-core` to its successor or is retired to match the
ontology's `REPLACED` disposition).

## Repair plans

Format per the correction that prompted this file: missing capability, evidence + exact
blocker, owning repo, required I/O, proposed interface, implementation steps, negative
fixtures, acceptance test, falsifiers, resume condition.

### RP-1 — reconcile ggen verifier builds  *(owner: `~/ggen`)*

Status: **local symptom fixed this session; the underlying defect class is open.**

- **Missing capability**: a version identity that actually identifies a build, so that two
  binaries claiming `26.8.6` cannot compute different chain hashes.
- **Blocker**: EV-1 above. Fixed on this machine by rebuilding from source and unlinking the
  Cellar copy, but the stale binary remains on disk and any `brew link` reintroduces it. The
  formula cannot be upgraded — its `stable` *is* `26.8.6`; upstream must cut a new tag.
- **Required I/O**: in → `.ggen-v2/receipt.json` + `receipt-log.jsonl`; out → identical
  `{valid, chain_hash, payload_hash, signature_valid}` from every build.
- **Interface**: no new interface. Version string must become a real identity — a build whose
  chain-hash computation differs must not report the same version.
- **Steps**: (1) diff the homebrew formula's pinned rev against `~/ggen` HEAD; (2) rebuild /
  reinstall from source (`cargo install --path`), or unlink the stale Cellar copy;
  (3) add the chain-hash algorithm version to the receipt schema so a mismatch is reported as
  *version skew*, not as *tampering*; (4) correct the misattributing remediation text.
- **Negative fixtures**: a genuinely tampered receipt must still be rejected; a receipt written
  by build A must verify under build B.
- **Acceptance test**: `test_all_verifier_builds_agree_on_the_same_receipt` (already written,
  currently red).
- **Falsifier**: a fourth build disagreeing with the reconciled majority.
- **Resume condition**: S5 leaves `BUILD_BROKEN` when all builds agree.

### RP-2 — restore `bcinr-powl-receipt`  *(owner: `~/bcinr`, consumed by `~/praxis` → `~/mfw`)*

Status: **CLOSED — measured win this pass. The build succeeds.**

```text
$ cd ~/mfw && cargo build -p mfw-planner -p mfw-pcp-cli
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 47.23s
$ echo $?
0
$ ls -la target/debug/mfw-planner target/debug/mfw-pcp-cli
-rwxr-xr-x  54215280  target/debug/mfw-planner
-rwxr-xr-x   6813552  target/debug/mfw-pcp-cli
```

Both run. `mfw-planner --help` → *"Receipted external planner runner"*, subcommands `probe`,
`run`, `export-powl`, `solve-rdf`, `solve`. `mfw-pcp-cli --help` → *"Proof-carrying plan
lifecycle verifier"*, subcommands `demo`, `verify-bundle`, `verify-replay`, `render-rdf`.

**Retraction, in place.** The pass-1 heading read *"the crate was RENAMED, not deleted. This is
a one-line fix."* The rename half is correct; **"one-line fix" was wrong** and is retracted. The
actual blast radius, measured:

- **four** `bcinr-powl-receipt` declarations, not one — `~/praxis/Cargo.toml:100`,
  `crates/multifractal-workflow/Cargo.toml:111`, `crates/praxis-core/Cargo.toml:20`,
  `crates/praxis-graphlaw/Cargo.toml:41`;
- **26 code import sites across 12 files** using `bcinr_powl_receipt::`.

A single-line edit would have moved the error, not removed it. This is the same
under-estimation pattern the file exists to catch, so the wrong estimate stays visible.

**Fix applied** on branch `fix/bcinr-powl-receipt-rename` in `~/praxis`: deleted all four
declarations (the successor `bcinr-powl` was already a dependency in 3 of the 4 crates), added
it to `praxis-core`, rewrote `bcinr_powl_receipt::` → `bcinr_powl::receipt::`, and replaced the
absolute `/Users/sac/…` paths with relative ones. Successor confirmed present:
`~/bcinr/crates/bcinr-powl/src/lib.rs:35` declares `pub mod receipt;` and all 13 successor
modules exist.

**Residual — not closed, and it is why S2 is `PARTIAL_ALIVE` and not higher.**

1. **The fix is NOT COMMITTED.** `~/praxis` carried 47 pre-existing dirty files, some in files
   also edited here; committing would entangle unrelated uncommitted work. A build that depends
   on an uncommitted working tree is not reproducible from a clean clone — the exact defect
   class this repair plan was opened for.
2. **Admission is still not demonstrated.** The autofde_lab engine has not been registered in
   `engines.toml` with a blake3 pin, so nothing has passed through mfw's own gate. "Builds" is
   not "admitted," and this pass claims only the former.

- **Missing capability**: none, actually. The dependency target moved.
- **Root cause**: commit `251f3af5` in `~/bcinr` — *"refactor(powl): collapse
  bcinr-powl-receipt into bcinr-powl::receipt"*. The successor is
  `~/bcinr/crates/bcinr-powl/src/receipt/` (14 files), whose `mod.rs:7` states outright:
  *"This was the standalone `bcinr-powl-receipt` crate through 26.7.28."* It shipped —
  `release/v26.7.24.toml:10,23` lists it — and per `~/bcinr/CHANGELOG.md:29`,
  **`bcinr-powl-receipt 26.7.28` is still on crates.io and is NOT yanked.**
- **Why it breaks anyway**: `praxis-graphlaw/Cargo.toml:41` uses an absolute **path** dep
  (`path = "/Users/sac/bcinr/crates/bcinr-powl-receipt"`) into a directory that the rename
  removed. A registry dep on `26.7.28` would still resolve; the path dep dangles.
- **Steps** (either closes it):
  - **(a) preferred** — `bcinr-powl = "26.7.29"` in `praxis-graphlaw/Cargo.toml` and update
    imports to `use bcinr_powl::receipt::…`. Moves onto the maintained successor.
  - **(b) minimal** — `bcinr-powl-receipt = "26.7.28"` from the registry. Unblocks the build
    immediately but pins a crate its own repo has retired.
  - **In both cases**, replace the absolute path with a registry or workspace-relative dep.
    An absolute `/Users/sac/...` path is why this was invisible to CI and unreproducible on
    any other machine — that is the durable defect, not the rename.
- **Negative fixture**: build must fail loudly if the crate is missing again — never silently
  feature-gate it away.
- **Acceptance test**: `cargo build -p mfw-planner` succeeds; then `cargo test -p mfw-planner`.
- **Falsifier**: build succeeds locally but not from a clean clone (absolute paths remain).
  **This falsifier is currently live** — the fix is uncommitted, so no clean clone has been
  tested. Treat the measured build above as machine-local until the branch lands.
- **Resume condition**: S2 → `PARTIAL_ALIVE` **(reached in pass 2)**. S2 → `ALIVE` requires the
  branch committed *and* the autofde_lab engine registered in `engines.toml` with a blake3 pin and
  admitted through mfw's real gate, upgrading S3 from *contract-conformant* to *admitted*.

  **Correction, pass 3, recorded in place.** That resume condition is **necessary but not
  sufficient** — it omits the validator requirement. Measured this pass (pass 3 §6):
  `mfw-planner probe classical` refuses at config load with *"exactly one independent validator
  role is required; observed 0"*, and no VAL-compatible validator binary exists on this machine.
  Registration with a blake3 pin cannot even be attempted; config validation refuses before any
  digest is computed. The corrected, narrow, nameable remaining gap: **obtain or build a
  VAL-compatible plan validator, register it in the `validator` role, then re-probe.** Only then
  does the blake3-pin step become reachable. Engine admission standing is
  `BLOCKED:VALIDATOR_ABSENT`.

### RP-3 — planner for ggen-legacy's orphan corpus  *(owner: `~/ggen-legacy`, needs `~/scikit-decide`)*

- **Missing capability**: anything that plans over `planning/v26.8.1/`. Today only
  `verify_planning.py` touches it — a paren-balance + substring checker. Its justfile runs
  `cargo test -p bcinr-pddl`, and that package does not exist in that repo (0 hits in any
  `Cargo.toml`; it lives in `~/bcinr/crates/bcinr-pddl`).
- **Blocker**: `UNSUPPORTED:derived-predicates,constraints,preferences` (S3c) — scikit-decide
  cannot correctly plan this domain, and now says so instead of guessing.
- **Two independent paths**, either sufficient:
  - **(a) Implement derived-predicate expansion in scikit-decide's C++ semantics.** Largest
    work, widest payoff. Steps: expand derivation rules to fixpoint during grounding in
    `cpp/src/hub/domain/pddl/semantics/`; wire `problem->get_constraints()` into
    `GoalChecker`; make `Preference` soft with a violation counter feeding `:metric`. Negative
    fixture: a domain where a derived atom gates the only goal-reaching action must go from
    unsolvable → solvable, proving expansion actually fires.
  - **(b) Rewrite the corpus to the supported subset.** Compile derived predicates away by
    inlining their bodies. Cheaper, but loses expressiveness and must be justified per domain.
- **Also fix regardless**: the two defects in S3d, and the dangling `-p bcinr-pddl` reference.
- **Acceptance test**: `test_unimplemented_requirements_are_refused_not_planned` inverts —
  a plan is produced *and* independently validated by VAL.
- **Falsifier**: a plan is produced whose steps VAL rejects — meaning expansion is wrong rather
  than absent, which is the S3c hazard reintroduced.
- **Resume condition**: S3 extends from `blocks`-class domains to the governance corpus.

### RP-4 — close ggen's root-regeneration gate  *(owner: `~/ggen`)*

- **Missing capability**: byte-identical re-manufacture; `Root Dogfood` 8/8 red.
- **Blocker**: `verify_root_regeneration.py` reports `generated_output_paths: []` and 5 of 21
  declared `output_file` values are un-expanded Tera placeholders
  (`crates/{{ crate_name }}/Cargo.toml`, `.specify/gates/{{ gate_id }}.rq`, …). The verifier
  compares them as literal paths. Fails *after* `sync run` succeeds.
- **Steps**: (1) decide whether those 5 rules are per-row fan-out (then the verifier must
  expand bindings before comparing) or authoring errors (then fix the manifest); (2) make the
  "unchanged: content identical" admission path still register ownership, so a clean checkout
  does not report zero generated outputs; (3) only then enable the byte-identical second-run
  step.
- **Falsifier**: gate goes green while `generated_output_paths` is still empty — that would be
  the gate being disabled, not satisfied.
- **Resume condition**: S4 → `ALIVE`; receipt `standing_ceiling` should rise above
  `LegacyObserved` and obligations above 5/9.

### RP-5 — exemplar → candidate authority  *(owner: `~/ggen-create`)*

- **Missing capability**: the reverse compiler. 0 lines.
- **Blocker**: not a bug — unbuilt, and the repo says so honestly in code.
- **Required I/O**: in → an exemplar (repo/service/document set); out → candidate
  `ontology.ttl` + templates + `ggen.toml` that `ggen sync run` can consume unmodified.
- **Interface note**: the output contract is already pinned by what `ggen` consumes —
  `[ontology] source/imports`, `[[generation.rules]]{query,template.file,output_file,mode}`.
  Build against that, not a new schema.
- **Negative fixtures**: an exemplar with no recoverable structure must REFUSE, not emit an
  empty ontology; a candidate ontology failing the SPARQL gates must not be admitted.
- **Acceptance test**: reverse-compile a small known project, run real `ggen sync run` on the
  output, and verify the receipt — with the exemplar and the regenerated artifact compared by
  `ggen-legacy`'s existing `equivalence_runner.py`.
- **Resume condition**: S1 → `PARTIAL_ALIVE`; the chain gains its front end and the career
  payload can enter as an exemplar rather than as hand-authored authority.

### RP-7 — wire bcinr's executor to mfw's broker  *(owner: `~/mfw` + `~/bcinr`)* — **the crown capability**

**Revised after discovering `~/bcinr`.** This was originally written as "build a POWL execution
controller." That was wrong — the driver already exists in `bcinr-powl`. The job is
composition, not construction, and it is materially smaller than first stated.

- **Missing capability**: the connection between bcinr's *symbolic* plan driver (walks the
  partial order, emits OCEL + BLAKE3, refuses on deadlock) and mfw's *actuating* broker
  (authorizes against model/proof digests, performs confined writes, chains receipts). Each
  half is real; neither is useful alone.
- **Evidence / exact blockers**: the two disjoint gaps proven above.
  - **G1 (ingestion)**: planner emits Turtle (`solve_rdf.rs:459`); runtime ingests JSON
    (`mfw-rmcp/src/config.rs:86`). Nothing reads `.powl.ttl` outside the planner's own tests.
  - **G2 (driver)**: `broker.actuate` (`broker.rs:118`) takes a singular `node_id`;
    `ready_actions`/`maximal_cohort` (`powl/validation.rs:156-158`) compute the next legal set
    but their only callers are read-only MCP advisory tools (`server.rs:145`, `:160`). The
    client is the scheduler.
- **Required I/O**: in → a validated POWL model + its `model_digest`/`proof_digest` + an
  authorization context; out → an ordered receipt chain covering **every** activity, an
  execution-time OCEL log, and a plan-level standing verdict.
- **Proposed interface** (composes only what already exists; invents no new primitive):
  ```
  loop:
    ready := ready_actions(model, completed)      # powl/validation.rs:156 — exists
    if ready.is_empty(): break
    for node in ready:
      receipt := broker.actuate(ActuationRequest{ # broker.rs:118 — exists
                    model_digest, proof_digest, node_id: node, occurrence, operation })
      completed.insert(node)
      emit_ocel_event(node, receipt)              # DOES NOT EXIST at execution time
  standing := close_standing(bundle, records, ...) # mfw-pcp-standing:106 — exists but
                                                   # compares digests only; must be extended
                                                   # to assert full activity coverage
  ```
  The loop body is three existing calls. What is missing is the loop itself, execution-time
  OCEL emission, and a coverage check inside `close_standing`.
- **Implementation steps** (revised — reuse, don't rebuild):
  1. **Close G1 (format) first — this is now the critical path.** Three representations exist
     with zero converters: mfw Turtle, mfw-runtime JSON, bcinr `Pddl8Tape`/`PowlModel`. Write
     **one** converter and declare **one** canonical form. Cheapest defensible option: a
     Turtle→`PowlModel` reader in `bcinr-powl` (it already owns the model types), making mfw's
     existing `plan.powl.ttl` the interchange format instead of a dead end.
     **Contested as of pass 2** — Turtle is the weakest of the three representations (it cannot
     express exclusive choice or guards, which the runtime JSON can), and the runtime's target
     fields are authorization decisions a converter cannot compute. See "which representation
     should be canonical" below. Do not execute this step before that decision has an owner.
  2. **Do not write a new scheduler.** Use `execute_and_seal_v2_with_selector`
     (`bcinr-powl/src/receipt/execution_v2.rs:129`) — it already provides the tick loop,
     `max_ticks` bound, deadlock refusal, and BLAKE3 chaining that step 5 of the original plan
     asked for.
  3. **G3 — brokered plan-scale actuation. This is NOT a matter of calling
     `broker.actuate()` inside the loop, and an earlier draft of this plan said it was.**
     That framing is retracted: G1 and G2 are integration work, but G3 crosses from symbolic
     state into *authorized consequence*, and that boundary carries design questions no
     amount of wiring answers. The contract needed is:

     ```
     POWL activity becomes ready
       → scheduler selects an occurrence
       → activity maps to a canonical operation
       → broker validates model, proof, pre-state, authority, occurrence
       → actuator causes a bounded external effect
       → observed POST-state is captured
       → receipt and OCEL event refer to the SAME consequence
       → scheduler advances only after accepted evidence
     ```

     Open architecture questions, each of which must be answered before code:
     - What maps a POWL activity to an executable operation? (Today mfw has 3 file-write ops;
       bcinr has PDDL add/del effects. Neither is a general mapping.)
     - What external effects are *legally* available, and who decides?
     - What proves an effect **occurred** rather than merely being **requested**? A receipt
       for a request is not a receipt for a consequence.
     - Does failed actuation leave symbolic scheduler state unchanged? (bcinr ORs into
       `done_mask` immediately — that is correct for symbolic firing and wrong for actuation.)
     - Retries and duplicate occurrences — idempotency semantics.
     - What constitutes terminal completion of an activity?
     - How are compensating or irreversible actions represented?
     - How does the broker stay an authority boundary instead of becoming the scheduler?
     - How does plan-level standing prove N-of-N required consequences?

     Keep scheduling and authorization in separate components. The single most likely failure
     here is collapsing planning, authority, actuation, and verification into one component
     that then attests to itself.
  4. Execution-time OCEL: bcinr already emits `OCELEvent` per step (`execute.rs:128`). Route
     that through mfw's receipt store so the OCEL log and the receipt chain describe the same
     run. Today mfw's OCEL logs only the *solve* (`solve_rdf.rs:67`), never execution.
  5. Extend `close_standing` (`mfw-pcp-standing/src/lib.rs:106`) to compare bcinr's
     `state.done_mask` against the model's full activity set and refuse unless every required
     activity has a terminal receipt. Today it compares `goal_digest` only, so N=1 closes.
- **Negative fixtures** (each must refuse, not pass):
  - A POWL model where one activity's predecessor never completes → standing must NOT close.
  - A model whose `model_digest` disagrees with the proof → broker must refuse before any
    actuation (this path already works; the test guards against regression).
  - An execution that completes N-1 of N activities → must report `PARTIAL_ALIVE`, never
    `ALIVE`. This is precisely the N=1 hole in `demo()`.
  - Two activities in an exclusive choice both executing → must refuse.
- **Chicago acceptance test**: a multi-activity POWL model, executed end to end, where the
  resulting receipt chain replays (`mfw-pcp-replay::verify`) AND covers every activity in the
  model — asserted against the model, not against a digest.
- **Falsifiers**:
  - Standing closes `ALIVE` while some activity has no terminal receipt → the coverage check
    is not actually walking the model.
  - The driver executes activities in an order the partial order forbids → `ready_actions` is
    being bypassed.
  - Execution "succeeds" using `RecordingActuator` (`mfw-pcp-broker/src/lib.rs:499`), which
    pushes a digest onto a `Vec` and has zero world effect. A green run on that actuator is
    theater; the acceptance test must assert a real workspace effect.
- **Resume condition**: crown leaves `BLOCKED`. Only then is RP-6 (recursion) coherent.

### RP-6 — the recursive controller  *(owner: undecided — see note)*

- **Missing capability**: `Blocked → derive prerequisite → spawn child workflow → manufacture
  → independently verify → admit → resume parent`.
- **Blocker**: absent everywhere. `GallStatus::Blocked` exists as a *status label*; nothing
  consumes it to spawn anything.
- **Ownership is genuinely undecided and should be decided before implementation.** It cannot
  live in scikit-decide (planning must not authorize), and putting it in `ggen` would make one
  component infer, generate, evaluate and certify — the circular self-attestation the
  architecture exists to prevent. `mfw` is the doctrine owner and the only component already
  holding broker + receipt + replay, so it is the least-bad home, but it is `BUILD_BROKEN`
  (RP-2) today.
- **Prerequisite**: **RP-7 above, first and hardest** — plus RP-2, RP-1, and at least one of
  RP-3/RP-5. The controller composes stages that must each work alone first, and a recursive
  controller that spawns child workflows is incoherent while nothing executes a single
  workflow to completion.
- **Falsifier for any future claim**: a controller that resumes a parent without re-admitting
  the child's output is not the doctrine — *"A child's claim of completion is raw observation
  until re-admitted."*
- **Resume condition**: S7 leaves `UNSUPPORTED` only when a bounded, terminating loop is
  demonstrated on a real blocked workflow, with the child's admission independently receipted.

### RP-8 — give `customer_authorized_retirement` a referent  *(owner: `~/ggen-legacy` + `~/mfw`)*

Status: **deferred/scoped — nothing under this plan has executed.** Opened pass 3.

- **Missing capability**: an organizational-authority rail. Concretely and narrowly: a record
  that a bare boolean in a manifest can resolve to, so that `sunset_admitted: true` becomes
  attributable rather than an assertion by whoever wrote the JSON. **Not** an authority system
  built from scratch — the gate already exists and works (pass 3 §3).
- **Evidence / exact blocker**: `~/ggen-legacy/appliance/bin/decision-engine.py` gates sunset on
  `release and closed and m.get("customer_authorized_retirement") is True`. Driven over four
  manifests this session with technical evidence held constant and green, it fail-closes on
  absent, string and `false`, and passes on boolean `true`. The gate's **shape is correct**. The
  blocker is that the flag has **no referent**: no named authority, no decision right, no
  predecessor identity, no verified replacement identity, no reviewed evidence set, no
  timestamp, no scope conditions.
- **Ownership — the part that matters.** The rail **cannot live in scikit-decide.** This repo is
  the search graph; it computes candidate plans and does not actuate. It may at most **compile
  and check** an authority envelope — a structural well-formedness check over a grant record.
  It may **never mint or enforce** one. Minting belongs to the accountable customer authority;
  **enforcement belongs to mfw's broker**, which already holds admission, receipts and replay
  and already refuses planner-only configurations (pass 3 §6). Putting authority in the planner
  is the organizational instance of the self-attestation circularity the whole separation exists
  to prevent.
- **Required I/O**: in → a `SunsetAuthorization` record naming the six fields above, plus the
  predecessor and replacement identities and the verifier reports already consumed by
  `decision-engine.py`; out → the same fail-closed verdict as today, plus an attributable record
  of *who* authorized *what*, on *what evidence*, *when*, and under *what scope*.
- **Proposed interface** — extend, never replace:
  ```text
  decision-engine.py keeps its exact current conjunction, and additionally requires
    resolve_authority(manifest.customer_authorized_retirement)
      -> AuthorityGrant { authority, decision_right, predecessor_id,
                          replacement_id, evidence_set, timestamp, scope }
      -> or REFUSE
  ```
  The boolean stays; it gains a resolution step in front of it. Vocabulary for the record is in
  `ontology/fde-authority-schema.ttl` (T-Box only — nothing there is `ALIVE`).
- **Steps**: (1) define the grant record against the schema's `AuthorityGrant` terms; (2) add
  resolution in front of the existing conjunction in `decision-engine.py`, leaving the
  conjunction itself untouched; (3) have mfw's broker enforce the grant's `boundedToEnvironment`
  and scope conditions at actuation time; (4) optionally, a compile-and-check-only envelope
  validator in scikit-decide — **read-only**, minting nothing.
- **Negative fixtures** (each must refuse, not pass):
  - A grant naming no authority → refuse. (Today this passes as `true`.)
  - A grant whose `replacement_id` is not independently verified → refuse.
  - A grant naming a different predecessor than the one being retired → refuse.
  - An expired grant, or one outside its scope conditions → refuse.
  - The existing string-`"true"` and `false` cases must **continue** to refuse — a regression
    here would mean the resolution step replaced the gate instead of preceding it.
- **Acceptance test**: a sunset admitted only when a fully-resolved grant is present, with the
  four existing fail-closed rows still red, asserted against a real `decision-engine.py`
  invocation — never a local simulation of it.
- **Falsifiers**:
  - `sunset_admitted: true` with no resolvable authority record → resolution is not being
    invoked.
  - The gate is reimplemented anywhere outside `~/ggen-legacy` → a local simulation has replaced
    the authority, which is the failure this plan exists to prevent.
  - scikit-decide mints or enforces a grant → the ecosystem boundary has been crossed.
- **Resume condition**: `organizationalStanding` becomes computable for the sunset transition
  specifically — one transition, not the axis. The second crown question stays **no** until an
  organizational-authority rail runs across validate / grant / accept / own / sunset, not just
  sunset.

## THE DECISIVE QUESTION — ANSWERED

**Which implemented component executes the complete POWL plan today?**

> **`~/bcinr` does — symbolically. `~/mfw` does not. They are not wired together.**

**Correction, recorded rather than quietly edited.** An earlier version of this section answered
"None. Definitively none." That was **wrong**: the search was scoped to `~/mfw` and the
conclusion was stated over the whole ecosystem. `~/bcinr` — a fifth repo, surfaced only when
the user asked about it — contains a real POWL executor. The prior claim is retracted, and the
lesson is recorded because it is the same failure mode this file exists to catch: a negative
finding is only as broad as the search that produced it.

The corrected picture is sharper and more actionable than the wrong one. **mfw and bcinr are
complementary halves of one executor, and nothing connects them:**

| | plan driver (walks the model, fires activities) | world effect (actuation) |
|---|---|---|
| `~/mfw` | **ABSENT** — `broker.actuate` takes a singular `node_id` | **REAL** — confined atomic writes under a workspace root |
| `~/bcinr` | **PRESENT** — partial-order tick loop + OCEL + BLAKE3 | **ABSENT** — mutates an in-memory `BTreeSet<Pddl8GroundAtom>` |

### The executor that does exist (`~/bcinr`)

`crates/bcinr-powl/src/receipt/execution_v2.rs:129` `execute_and_seal_v2_with_selector`:

```rust
for _ in 0..max_ticks {
    match scheduler_tick_v2(tape, &mut state, selector, guards) {
        PowlV2TickOutcome::Fired(mask) => fired_masks.push(mask),
        PowlV2TickOutcome::Complete => break,
        PowlV2TickOutcome::Deadlock { remaining_mask } =>
            return Err(PowlV2ReceiptError::Deadlock { remaining_mask }),
    }
    if state.is_complete(tape) { break; }
}
let chain_root = digest_chain(&tape_root, &guard_root, &fired_masks, state.done_mask);
```

The tick body (`scheduler_v2.rs:67`) computes `ready_mask`, applies a pluggable selector, and
ORs the fired set into `done_mask`. `crates/bcinr-pddl/src/execute.rs:128` `execute_tape` is
the full BRCE loop — Prolog8 `may_fire` gate (`Pddl8Error::StepDenied` on refusal) → apply
add/del effects → BLAKE3 chain step → push `OCELEvent` → returns
`(Pddl8ExecutionLog, Pddl8ExecutionReceipt, OCEL)`.

Note the architectural contrast: mfw's broker returns to the caller after authorizing one
action; bcinr puts the admission gate *inside* the loop. Both are defensible; they are not
composable as-is.

### The three gaps that remain (revised)

**G1 — format/ingestion.** mfw emits POWL as **Turtle** (`solve_rdf.rs:459`); mfw's runtime
ingests **JSON** (`config.rs:86`); bcinr consumes **Rust structs / `Pddl8Tape`**. There is no
Turtle→`PowlModel` reader **in either repo**. Three representations, no converters. This is now
confirmed from both ends rather than inferred from one.

**G2 — driver placement.** mfw has no plan loop. But bcinr *has* one, so RP-7 changes from
"build an executor" to "**wire the existing executor to the existing broker**" — a materially
smaller and better-specified job.

**G3 — actuation, and this one is genuinely open.** Neither repo closes it. bcinr fires masks
and mutates in-memory state — zero external effect. mfw actuates for real but only through 3
file-write operations, and its PCP lane's sole `Actuator` (`RecordingActuator`,
`mfw-pcp-broker/src/lib.rs:499`) pushes a digest onto a `Vec`. **The step where a fired POWL
activity causes an effect in the world is absent from both.**

**Pass-2 correction: G1 and G3 above are ONE gap, not two.** See the merged row in the gap
table earlier — the runtime's POWL requires `authorization_class`, `read_set`, `write_set` and
a concrete `NativeOperation`, none of which a planner can emit, so "write a converter" (G1) and
"decide what an activity actuates" (G3) are the same decision. The two-headed framing in this
subsection is preserved for the record and is superseded.

**Which representation should be canonical is now an OPEN DECISION with source evidence
against the obvious answer.** Measured this pass: `mfw-rmcp`'s `NodeKind` has
`ChoiceGraph { start, end, nodes, edges: Vec<ChoiceEdge> }` where `ChoiceEdge` carries a
`guard_digest`, plus `Cycle { body, invariant_theorem, variant_theorem }` and
`CommutationWitness`. So exclusive choice, guards, and bounded loops **are** representable in
the runtime JSON. They are **not** representable in Turtle (`powl2.shacl.ttl` defines only 3
shapes, none for choice) and **not** in bcinr's `PowlModel` (no choice variant —
`~/bcinr/crates/bcinr-powl/src/model/mod.rs:148`).

Therefore **Turtle is the weakest of the three representations, not the canonical one.** RP-7
step 1 below proposes a Turtle→`PowlModel` reader making Turtle the interchange format; that
proposal is now **contested by this evidence** — it would canonicalise the only representation
that cannot express choice or guards. Recorded as an open decision. Not decided here: deciding
it requires an owner and a stated cost, neither of which a ledger row can supply.

### Caveats that bound the above

- `~/bcinr` has **no `target/`** — nothing compiled locally. The executor is CI-tested code;
  there is no local build artifact to cite as a run this session. Requires nightly Rust.
- `bcinr-powl` is an **optional** dependency of `bcinr-pddl`, behind the `mfw-planner` feature
  (`bcinr-pddl/Cargo.toml`, `lib.rs:16-18`). So `cargo test -p bcinr-pddl` — the line in
  `ggen-legacy`'s justfile — does **not** compile the POWL execution path by default. Anyone
  citing that command as proof of execution is citing the wrong thing.
- bcinr's own `CLAUDE.md` is stale (documents `bcinr-api`, `bcinr-mcp`, `bcinr-pddl-lsp`,
  `bcinr-bench`; those directories are gone, removed as out-of-scope per `Cargo.toml:7-25`).

The crown remains **`BLOCKED`** — but for a corrected reason: not "no executor exists," rather
"an executor exists, it is symbolic, and it is not connected to the actuating half."

### Per-transition ownership

| # | Transition | Standing | Evidence |
|---|---|---|---|
| 1 | receive selected plan | **ABSENT** | `mfw-planner/src/solve_rdf.rs:459` writes `plan.powl.ttl`. Repo-wide, the only readers are the planner's own tests (`tests/solve_rdf.rs:45`, `ticket11_fixture.rs:26`, `ticket11_jira_bundle.rs:53`). **No executor, broker, or runtime crate parses Turtle POWL.** Write-only export format. |
| 2 | project/admit as POWL | OWNED (planner-internal) | `mfw-planner/src/projection/powl_rdf.rs:132` `emit_powl_ttl`. Runtime-side admission is `mfw-rmcp/src/proof.rs:309`, fed by a *different* source (see gap G1). |
| 3 | SHACL-validate POWL | **OWNED, genuinely invoked** | `solve_rdf.rs:27` `include_str!("../shapes/powl2.shacl.ttl")`, called at `solve_rdf.rs:457` `shacl_validate(&powl_ttl, POWL_SHAPES, ...)`. A real call, not a file on disk. Validates at *write* time; nothing re-validates at execution time. |
| 4 | bind model/proof digests | OWNED, per single node | `mfw-rmcp/src/broker.rs:24-33`, enforced ~`:239-260`. Bound to one node, never to a plan. |
| 5 | authorize **each** action | OWNED, **one per request** | `mfw-rmcp/src/broker.rs:118` `pub async fn actuate(&self, request: ActuationRequest) -> Result<Receipt>` — `node_id: String`, singular. The broker never iterates a model's activities. PCP lane同: `mfw-pcp-broker/src/lib.rs:234` takes one `CanonicalAction` and `:216` rejects concurrency outright. |
| 6 | execute the actions | OWNED but trivial | "Closed native operation algebra" = 3 variants (`mfw-rmcp/src/powl.rs:8-25`): `WriteLevel5Pack`, `RecordLevel5Evidence`, `GenerateRmcpModule`. Runtime tree likewise 3 (`CreateDirectory`, `WriteFile`, `MaterializeLevel5Pack`). **No spawn, no process exec, no network.** Effect = bytes appear under a canonicalized workspace root. In the PCP lane the only `impl Actuator` is `RecordingActuator` (`lib.rs:499`, `actuate` at `:505`) which pushes a digest onto a `Vec` — **zero world effect**. |
| 7 | OCEL + hash-chained receipts | **SPLIT ACROSS LANES** | Receipts real: `broker.rs:122/154/186` via `ReceiptStore::append`, chain verify `:109`. But OCEL exists **only in the planner** (`projection/ocel_rdf.rs`, `solve_rdf.rs:67`) and logs the *solve*, not execution. **Execution emits no OCEL at all.** |
| 8 | verify / replay | OWNED (PCP lane only) | `mfw-pcp-replay/src/lib.rs:45` `verify(records)`, `:60` `records.chunks_exact(2)`. Replays *receipts*; has no POWL model in scope. |
| 9 | **plan** completed with standing | **STRUCTURALLY ABSENT** | `mfw-pcp-standing/src/lib.rs:106` `close_standing(...)` compares `goal.goal_digest != bundle.plan.body.goal_digest` — "plan" is only a **digest**. The POWL structure is never walked, so **nothing checks that every required activity ran**. Standing can close on a single action, and in its only caller it does: `mfw-pcp-cli/src/main.rs:94` `demo()` builds ONE hard-coded `CanonicalAction` (`:97-118`), one `open`, one `actuate`, then `close_standing` (`:154`) prints `ALIVE`. Plan-completion over N=1. |

### The two disjoint gaps — *superseded, kept for the record*

**Pass-2 note.** "Disjoint" is retracted. G1 (ingestion) and G3 (actuation) are one gap; see the
gap table earlier for the measurement. Also note that `export-powl` emits **JSON**
(`urn:mfw:powl:document:v2`), so "the planner emits Turtle" below is incomplete: it emits both,
and the JSON it emits is still not the flat `nodes`/`root` shape the runtime ingests.

**G1 — ingestion gap.** The planner emits POWL as **Turtle**; the runtime ingests POWL from
**hand-authored JSON** (`mfw-rmcp/src/config.rs:86` `load_json_files(&config.powl_models)`,
field at `config.rs:28`). These are two unconnected pipes. A plan computed by any planner
cannot reach the broker without a human retyping it as JSON.

**G2 — driver gap.** No loop anywhere walks a plan and drives execution. The only
POWL-topology-aware functions are `ready_actions` / `maximal_cohort`
(`mfw-rmcp/src/powl/validation.rs:156-158`), and their only non-test callers are the
**read-only MCP advisory tools** `server.rs:145` (`powl_ready_set`) and `:160`
(`powl_maximal_cohort`). They compute what *could* run next and return it. Nothing consumes
that answer and actuates it — **the client (a human, or an LLM) is the scheduler.**

Architecturally: `planner → plan.powl.ttl → (dead end)`. Separately and unconnected:
`JSON POWL → broker → one authorized file-write per request → receipt`.

This does not diminish what is real — SHACL validation, digest binding, receipt chaining,
replay, and confined atomic writes are all genuinely implemented. It locates precisely what is
not: **the connective tissue that turns a validated plan into an executed workflow.**

## How to read this

- **measured win** — command run this session, output quoted above, passed.
- **recorded negative** — attempted, genuinely blocked, blocker named precisely enough that
  the next pass does not rediscover it from zero.
- **deferred / scoped** — a plan exists; nothing under it executed. Every repair plan above is
  in this category until it appears as a measured win.

## See also

- `docs/STATUS.md` — the in-repo WIP ledger this file extends across repositories.
- `tests/ecosystem/test_chatman_chain_chicago.py` — the crown test.
- `tests/domains/python/test_career_admission_unit.py` — the demoted unit checkpoint; carries
  a scope warning so it is not cited as ecosystem evidence.
- `.claude/rules/standing-law.md` (status vocabulary), `.claude/rules/actuation-boundary.md`,
  `.claude/rules/ecosystem-boundary.md` (why this repo claims candidate plans and nothing more),
  `.claude/rules/fde-authority-boundary.md` (the organizational layer added in pass 3).
- `ontology/fde-authority-schema.ttl` — hand-authored **T-Box** for the FDE vocabulary and the
  three standing dimensions. Distinct in kind from the **generated** A-Box
  `ontology/autofde-lab-capabilities.ttl`. Nothing in it is `ALIVE`.
