# Role

The crown suite. `test_chatman_chain_chicago.py` drives the **real binaries and real corpora**
of the sibling repositories as subprocesses — `~/mfw`, `~/ggen`, `~/ggen-legacy`, `~/bcinr`,
`~/ggen-create`. Nothing here is mocked.

The crown scenario covers two closures, not one: **technical causal closure** (an authority
becomes a verified artifact) and **organizational adoption closure** (a verified artifact
becomes an adopted organizational capability). The second is not a formality appended to the
first; it has its own issuers, its own evidence, and its own standing dimension — see
`.claude/rules/fde-authority-boundary.md`.

## The 18 stages

1. FDE arrives with a compiled legacy-replacement hypothesis — falsifiable, not asserted.
2. Customer authority validates or corrects the model.
3. Admitted facts become O*.
4. Parent reaches `BLOCKED(replacement-capability)`.
5. scikit-decide proposes the child transition — a candidate, never an actuation.
6. MFW manufactures and admits POWL geometry.
7. The authority grant permits **only** the bounded crown operations.
8. bcinr schedules.
9. MFW's broker authorizes each occurrence — per occurrence, not once for the plan.
10. ggen manufactures.
11. Independent verification and replay succeed.
12. The FDE presents evidence against the **agreed** business postconditions.
13. The customer operating owner accepts or refuses.
14. Organizational capability standing admitted.
15. Parent resumes.
16. Explicit retirement authority evaluated by ggen-legacy's **real** decision engine —
    `~/ggen-legacy/appliance/bin/decision-engine.py` (38 lines; fail-closed on 3 reports,
    7 zeroed closure counters, and `customer_authorized_retirement is True`).
    Never replace it with a local simulation; a simulated gate proves nothing about the gate.
17. Sunset succeeds or refuses.
18. Enterprise standing closes only after the whole evidence chain — never on stage 11 alone.

Stages 1–2, 7, 12–14 and 16–18 have no rail in this repo today. They are scenario, not
coverage.

# Authority

- Establish that scikit-decide's engine conforms to `mfw`'s external-engine contract, that the
  POWL projection uses `mfw`'s committed vocabulary with real BLAKE3 digests, and that the
  generated ontology matches the live registry.
- **Defend the boundary**: explicit tests assert this repo emits no receipt and claims no
  admission (`test_engine_emits_no_receipt`, `test_powl_projection_claims_no_admission`),
  because "planning selects, the broker authorizes" is a line a passing suite should defend
  rather than quietly erode.
- Assert a capability is *absent* so the claim cannot drift silently
  (`test_recursive_bootstrap_controller_is_absent_across_ecosystem`).

# Non-authority

- Cannot establish end-to-end closure. The chain does not close: `ggen-create` is
  `UNSUPPORTED` (0 lines), `mfw-planner` is `BUILD_BROKEN`, POWL execution is `PARTIAL_ALIVE`
  and unwired, the recursive controller is `UNSUPPORTED`.
- Cannot admit anything. It observes `mfw`'s and `ggen`'s verdicts; it does not issue them.
- Cannot establish **organizational** closure at all. No test here can stand in for a customer
  operating owner's acceptance (stage 13) or a retirement decision right (stage 16). A green
  row is `technicalStanding` only.

# Inputs

Sibling repos at their real paths; installed `ggen` binaries; `b3sum`;
`~/mfw/runs/ticket-10/{work/candidate.plan,plan.powl.ttl}`;
`~/ggen-legacy/planning/v26.8.1/`; `ontology/autofde-lab-capabilities.ttl`.

# Outputs

Pass / typed skip / hard fail, plus a machine-readable coverage report fixture.

# Invariants

1. **Skip only on genuine absence, and always with an exact blocker token**:
   `pytest.skip("BLOCKED:<TOKEN>: <detail>")` — e.g. `BLOCKED:MFW_ARTIFACT_ABSENT`,
   `BLOCKED:GGEN_BINARY_ABSENT`, `BLOCKED:B3SUM_ABSENT`,
   `BLOCKED:INSUFFICIENT_VERIFIER_BUILDS`, `BLOCKED:GGEN_LEGACY_CORPUS_ABSENT`.
   A **present-but-misbehaving** prerequisite is a hard `pytest.fail`, never a skip.
2. **Never substitute a fixture for an absent prerequisite and proceed.** A green run on a
   broken ecosystem is worthless.
3. No artifact is admitted because its producer says so — `ggen sync run`'s output is checked
   by the separate `ggen receipt verify` path.
4. **This suite is not expected all-green.**
   `test_all_verifier_builds_agree_on_the_same_receipt` is left deliberately red when the
   verifier builds disagree, rather than `xfail`-ed or skipped: the independent-verification
   stage genuinely is broken and `docs/ecosystem-standing.md` records it (EV-1 / RP-1). Making
   it green by relaxing the assertion is the one prohibited fix. A red row here is a finding.
5. Comparison claims must be measured by running, never delegated — `match_solvers(ranked=True)`
   ignores the flag.
6. **Never simulate the sunset gate.** Stage 16 runs the real
   `~/ggen-legacy/appliance/bin/decision-engine.py`, or the stage is
   `BLOCKED:GGEN_LEGACY_CORPUS_ABSENT`. A local reimplementation would test the reimplementation.
7. **Never synthesize a customer decision.** Writing `customer_authorized_retirement: true` into
   a fixture manufactures the authority the gate exists to require. If organizational stages are
   exercised at all, they are exercised as refusals.

# Neighboring components

`src/autofde_lab/fabric/{pddl_engine,powl,ontology,coverage}.py`; `ontology/`;
`docs/ecosystem-standing.md` (per-stage ledger S1–S8 and repair plans RP-1…RP-7);
`tests/domains/python/test_career_admission_unit.py` (the demoted unit checkpoint this suite
is explicitly *not*).

# Verification

```bash
uv run pytest tests/ecosystem/ tests/domains/python/test_career_admission_unit.py -v
```

Read the skip reasons, not just the count: a high skip count means the ecosystem was absent,
which is a different result from green.

# Standing ceiling

Strongest establishable claim: **`ALIVE` for S3 (candidate-plan computation) and S3b (POWL
projection) only** — the engine ran against real corpora, the projection matched `mfw`'s
committed vocabulary, digests cross-checked against independent `b3sum`.

Explicitly not establishable, and must not be reported otherwise: the crown. Closure requires
ontology-governed discovery → complete applicable-capability coverage → plan computation →
POWL manufacture → **MFW admission → brokered execution of the whole plan → execution-time
OCEL + receipts → replay → verified plan-level standing**. Steps five onward are absent. S3c is
decisive: a plan never executed makes every downstream stage moot. Reporting the crown as
anything but `BLOCKED` would require a projector to stand in for an executor — the exact error
this suite exists to prevent.

**Ceiling on the dimension, not just the stage.** Even a fully green technical chain would
establish `technicalStanding` only. This suite can at most establish technical standing until an
organizational-standing rail exists — nothing here observes stages 12–14 or 16–18, and no
component computes `organizationalStanding` as of this session. `enterpriseStanding` is
therefore `UNKNOWN` by construction, not pending. Reporting a green crown as enterprise closure
is the organizational form of letting a projector stand in for an executor.

# Update obligations

- New skip → it must carry a `BLOCKED:<TOKEN>:` reason, and the token should appear in
  `docs/ecosystem-standing.md`.
- A red test turning green → record *why* in `docs/ecosystem-standing.md` (defect fixed vs.
  assertion changed). Only the former is progress.
- Any sibling-repo path or binary assumption changing → update the ledger's stage row in the
  same change; a stale absolute path is the defect class RP-2 was written for.
- An organizational stage (1–2, 7, 12–14, 16–18) gaining a rail → say which dimension it moves,
  and update the standing ceiling above; a new test does not by itself raise the ceiling.
