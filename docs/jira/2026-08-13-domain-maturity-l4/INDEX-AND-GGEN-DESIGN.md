# Job 1 — Prioritized Ticket Index

Sorted by (a) weakest current domain first — approximated from the dimension scores stated in the batch write-ups (exact sums not independently re-derived here; several domains' "already meets L4" dimensions were stated without a numeric score, so this ordering is UNVERIFIED against a canonical maturity matrix, not a re-computation of it) — then (b) effort ascending within domain.

## Weakest domains first (most/heaviest gaps)

**flight_planning**
- Verification independence — Independent re-derivation for flight-plan verification — L
- OCEL evidence — Committed OCEL 2.0 log for a flight-planning episode — M
- Actuation authority — Typed precondition+plan-order gating, sabotage test — M
- Standing honesty — Module-level standing tag (possible false-claim correction) — S/M

**cloudgoat_iam_privesc** *(actuation + verif tickets are INFRA-BLOCKED proxies, not true L4)*
- OCEL evidence — Real OCEL 2.0 log for simulated episode — L
- Domain fidelity — Automated drift check vs vendored README/cheat sheet — M
- Solver/planning integration — Registered-solver verified plan — M
- Actuation authority [INFRA-BLOCKED] — Typed BRCE refusal proxy over simulated plan — M
- Verification independence [INFRA-BLOCKED] — Independent re-check of simulated goal state — S

**k8s_goat_rbac_escalation**
- OCEL evidence — Real OCEL 2.0 log from materialize→act→verify→teardown — L
- Actuation authority [INFRA-BLOCKED proxy] — Typed refusal gate for DO capabilities — L
- Verification independence [INFRA-BLOCKED proxy] — Independent re-derivation of scenario completion — L
- Domain fidelity — Automated drift check vs vendored scenario-16 — M
- Solver/planning integration — Registered solver + verified plan through the gate — M

**breach_clock**
- Domain fidelity — Ground in a real IR reference (NIST 800-61 etc.) or explicitly own as synthetic — L
- OCEL evidence — Real OCEL 2.0 log from simulated episode — M
- Actuation authority — Typed refusal for out-of-order containment/notification — M
- Verification independence — Fresh-instance replay re-derivation (proxy, no external system) — S
- Solver/planning integration — Verified plan through divergence/replan hook — S

**chatman_clean_session**
- Domain fidelity — Locate/vendor real reference or own as synthetic — L
- Solver/planning integration — Register solver + verified plan — L
- OCEL evidence — Real OCEL 2.0 log for episode — L
- Verification independence — Independent verify() distinct from broker's own receipt — M

**tai_v30_1_1**
- Solver/planning integration — Replace hardcoded plan constants with real solver — L
- Domain fidelity — Automated drift check vs source spec — M
- Verification independence — Subprocess-isolated verify_receipt_replay — M
- OCEL evidence — Real OCEL 2.0 log — M

**up**
- Verification independence — Subprocess-based independent plan verification — M
- OCEL evidence — Real OCEL 2.0 log — M
- Standing honesty — Explicit standing tag + STATUS.md entry — S/M

**rddl**
- OCEL evidence — Real OCEL 2.0 log (instrument existing SB3 rollout) — L
- Actuation authority — Typed refusal wrapping pyRDDLGym constraints — M
- Verification independence — Independent second-instance replay — M
- Standing honesty — Module tag + STATUS.md entry — S

**pddl**
- OCEL evidence — Real OCEL 2.0 log for blocks-world episode — M
- Verification independence — Subprocess-based independent plan verification — M
- Standing honesty — Module tag citing STATUS.md evidence — S

**plado**
- OCEL evidence — Real OCEL 2.0 log — L
- Verification independence — Independent goal re-derivation via fresh Task/GoalChecker — M
- Solver/planning integration — Verified plan via fresh-instance replay — M
- Standing honesty — Docstring tag (PARTIAL_ALIVE, cites existing ~15 NotImplementedError gaps) — S

**maze**
- Actuation authority — gymact_bridge.py with typed refusal — L
- Domain fidelity — Vendor real source or own as synthetic — M
- OCEL evidence — Real OCEL 2.0 log — M
- Test coverage — First test file from zero — M
- Verification independence — Fresh-parse goal re-derivation — M
- Standing honesty — Tag (depends on above landing) — S

**simple_grid_world**
- Actuation authority — gymact_bridge.py with plan-cursor refusal — L
- OCEL evidence — Real OCEL 2.0 log — M
- Test coverage — First test file from zero — M
- Domain fidelity — Vendor real source or own as synthetic — S/M
- Verification independence — Fresh-formula goal re-derivation — S/M
- Standing honesty — Tag — S

**mastermind**
- Solver/planning integration — POMDP solver + verified plan (may need new solver adaptation) — M/L
- Test coverage — First test file from zero — M
- Domain fidelity — Property-invariant proxy (no external ref) — S
- Actuation authority — Guard clause + typed refusal — S
- Verification independence — Standalone re-scoring module — S
- OCEL evidence — Real OCEL 2.0 log — S
- Standing honesty — Tag — S

**gym**
- Actuation authority — Capability gate on `_state_step` — M
- Verification independence — Subprocess-replay verifier — M
- OCEL evidence — Real OCEL 2.0 log — M
- Solver/planning integration — Verified plan (depends on above) — M
- Standing honesty — Tag — S

**rock_paper_scissors**
- Solver/planning integration — Real multi-agent solver + verified plan — M
- Domain fidelity — Zero-sum/antisymmetry invariant proxy — S
- Actuation authority — Typed refusal for invalid `Move` — S
- Verification independence — Standalone reimplementation — S
- OCEL evidence — Real OCEL 2.0 log — S
- Standing honesty — Tag — S

**rcpsp**
- Verification independence — Standalone PSPLIB-reparse verifier — M
- OCEL evidence — Real OCEL 2.0 log — M
- Solver/planning integration — Verified plan (depends on above) — M
- Test coverage — Rewrite zero-assertion test — S
- Actuation authority — Precedence-order guard — S
- Standing honesty — Tag — S

**career_admission**
- Verification independence — Subprocess independent re-read of authority ontology — M
- Actuation authority — Typed refusal for blocked-capability admission — M
- OCEL evidence — Real OCEL 2.0 log — M
- Domain fidelity — Drift assertion vs already-parsed ggen-legacy TTL — S
- Solver/planning integration — Wire existing Astar plan through gate+verify — S

**graph_domain**
- Actuation authority — `merge()` conflict-detection guard — S
- Domain fidelity — Docstring + invariant check — S
- Verification independence — `to_networkx()`-based independent check (port to `GraphDomain` if needed) — S
- OCEL evidence — Real OCEL 2.0 log — S
- (Solver/planning integration folds into the verify ticket — no separate ticket)

**azuregoat_privesc**
- Verification independence — Disk-backed independent fact ledger — M

**fix_git**
- OCEL evidence — First-ever OCEL episode (blocked on bridge below) — L
- Actuation authority — gymact_bridge.py with typed refusal — M

**terragoat**
- Actuation authority — Real gated DO capability + refusal sabotage test — M

**gym_procedure** — already meets L4 on all 7 dimensions; no tickets.

---

# Job 2 — ggen-first closure design (not built, not proven)

**Stated plainly:** nothing below has been implemented or run. This is a design for the next step only.

## Why one pack, not 19 scripts

Every domain's OCEL-evidence and verification-independence gap has the same shape: (1) an episode runner that materializes a domain, drives it through a real action sequence, and emits a schema-valid OCEL 2.0 log; (2) a standalone verifier that re-derives the terminal claim from a source other than the in-process actor (fresh subprocess/fresh instance/independent re-parse). Per CLAUDE.md's ggen-first mandate, this is exactly the case for modeling the *facts that vary per domain* in RDF and generating both artifacts from two Tera templates, instead of hand-writing ~19 near-identical scripts + ~19 near-identical verifiers.

## Pack name

`autofde-domain-evidence-pack`

## Ontology shape (`ontology.ttl`)

One class, `afl:Domain`, with individuals — one per hub domain — carrying:

```turtle
@prefix afl: <https://autofde-lab/ontology/domain-evidence#> .

afl:Domain a rdfs:Class .
afl:Capability a rdfs:Class .

afl:domainName        a rdf:Property .  # e.g. "terragoat"
afl:pythonModulePath  a rdf:Property .  # e.g. "src.autofde_lab.hub.domain.terragoat.terragoat_remediation"
afl:domainClassName   a rdf:Property .  # e.g. "TerraGoatRemediation"
afl:bridgeClassName   a rdf:Property .  # e.g. "gymact_bridge.actuate" — literal "" if no bridge exists yet
afl:hasCapability     a rdf:Property .  # ordered list of afl:Capability individuals
afl:goalCheckExpr     a rdf:Property .  # a Python boolean expression string, evaluated against a fresh re-derived state
afl:verifyMode        a rdf:Property .  # closed enum: "subprocess-replay" | "fresh-instance-replay" | "independent-reparse" | "standalone-reimpl"
afl:evidenceOutPath   a rdf:Property .  # e.g. "docs/evidence/terragoat/episode.ocel.json"

afl:Capability >
  afl:capabilityName   a rdf:Property .  # e.g. "checkout_recovery"
  afl:consequence       a rdf:Property .  # closed enum: "DO" | "OBSERVE"
  afl:preconditionExpr  a rdf:Property .  # Python expression string
```

`afl:verifyMode` is the key closed-world admission gate: it maps 1:1 to which Tera template branch the verifier generator uses (subprocess launch vs. fresh in-process object vs. re-parse-from-disk vs. hand-reimplemented pure function), so the generator never has to guess — the ontology author (a human, reading the real domain source once) commits to the honest independence mechanism up front, matching this project's evidence-first discipline.

## Two Tera templates

**1. `templates/run_domain_episode.py.tera`** (OCEL episode generator)
- SPARQL-selects one `afl:Domain` individual + its ordered `afl:Capability` list
- Emits a runnable script: imports `{{ pythonModulePath }}.{{ domainClassName }}`, materializes it, iterates capabilities calling `{{ bridgeClassName }}` if non-empty else the domain's raw `_get_next_state`, emits OCEL events (`materialize`, `act` per capability, `verify`, `teardown`) via the shared `gymact.ocel.write_ocel_log` helper (already proven real in `scripts/run_azuregoat_gymact_ocel_episode.py`), writes to `{{ evidenceOutPath }}`.

**2. `templates/standalone_verifier.py.tera`**
- Branches on `{{ verifyMode }}`:
  - `subprocess-replay` → shells a fresh `python -m {{ pythonModulePath }}` process and diffs output against the claimed state (pddl/up/plado pattern)
  - `fresh-instance-replay` → constructs a brand-new `{{ domainClassName }}` instance and replays the recorded action sequence (maze/rcpsp/breach_clock pattern)
  - `independent-reparse` → re-reads the domain's own source file(s) fresh from disk and re-evaluates `{{ goalCheckExpr }}` against the fresh parse (career_admission/graph_domain pattern)
  - `standalone-reimpl` → emits a hand-authored pure-function reimplementation stub the human fills in once (rock_paper_scissors/mastermind pattern, since those have no file/subprocess boundary to re-cross)
- Every branch enforces the same import-discipline check already proven in `gym_procedure/standalone_verifier.py` (`FORBIDDEN_RUNTIME_MODULES` via `sys.modules`, so the verifier can't accidentally import the actor's live module).

## Worked example — 3 real domains as RDF individuals

```turtle
afl:terragoat a afl:Domain ;
  afl:domainName "terragoat" ;
  afl:pythonModulePath "src.autofde_lab.hub.domain.terragoat.terragoat_remediation" ;
  afl:domainClassName "TerraGoatRemediation" ;
  afl:bridgeClassName "" ;  # AFL-TERRAGOAT-1 not yet landed
  afl:hasCapability afl:terragoat_cap_1 ;
  afl:goalCheckExpr "len(state.open_findings) == 0" ;
  afl:verifyMode "fresh-instance-replay" ;
  afl:evidenceOutPath "docs/evidence/terragoat/episode.ocel.json" .

afl:terragoat_cap_1 a afl:Capability ;
  afl:capabilityName "close_finding" ;
  afl:consequence "DO" ;
  afl:preconditionExpr "finding_id in state.open_findings" .

afl:career_admission a afl:Domain ;
  afl:domainName "career_admission" ;
  afl:pythonModulePath "src.autofde_lab.hub.domain.career_admission.career_admission" ;
  afl:domainClassName "CareerAdmissionDomain" ;
  afl:bridgeClassName "" ;
  afl:hasCapability afl:career_cap_1 ;
  afl:goalCheckExpr "not is_blocked_capability(admitted_id, fresh_authority_graph)" ;
  afl:verifyMode "independent-reparse" ;
  afl:evidenceOutPath "docs/evidence/career_admission/episode.ocel.json" .

afl:career_cap_1 a afl:Capability ;
  afl:capabilityName "admit_capability" ;
  afl:consequence "DO" ;
  afl:preconditionExpr "all(p in admitted for p in fact.prerequisite_ids)" .

afl:rock_paper_scissors a afl:Domain ;
  afl:domainName "rock_paper_scissors" ;
  afl:pythonModulePath "src.autofde_lab.hub.domain.rock_paper_scissors.rock_paper_scissors" ;
  afl:domainClassName "RockPaperScissors" ;
  afl:bridgeClassName "" ;
  afl:hasCapability afl:rps_cap_1 ;
  afl:goalCheckExpr "state.moves_played >= max_moves" ;
  afl:verifyMode "standalone-reimpl" ;
  afl:evidenceOutPath "docs/evidence/rock_paper_scissors/episode.ocel.json" .

afl:rps_cap_1 a afl:Capability ;
  afl:capabilityName "play_move" ;
  afl:consequence "DO" ;
  afl:preconditionExpr "move in Move" .
```

## What this closes and what it doesn't

Generating from this ontology would produce a real `run_<domain>_episode.py` and `<domain>_verifier.py` for every domain with an individual — closing the OCEL-evidence ticket and (for `fresh-instance-replay`/`independent-reparse`/`standalone-reimpl` modes) the verification-independence ticket directly. It does **not** close:
- Actuation-authority tickets (those need real precondition-gated bridges written per domain first, since `afl:bridgeClassName` is often empty — the pack consumes a bridge, it doesn't author one)
- The `subprocess-replay` mode's correctness (still needs a real, working `python -m <module>` entrypoint per domain to shell out to)
- Domain-fidelity tickets (those require a human judgment call — real external reference vs. honest synthetic-fixture disclosure — that isn't mechanizable from a closed ontology)
- The two infra-blocked domains' true (non-proxy) actuation/verification tickets (k8s_goat_rbac_escalation, cloudgoat_iam_privesc) — still gated on live cluster/cloud access no ontology closes