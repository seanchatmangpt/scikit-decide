# GymAct handoff: what to seed `seanchatmangpt/gymact` from

This is a lab-side (`autofde-lab`) prep artifact, not GymAct implementation. GymAct itself
is a separate, standalone Python library (`seanchatmangpt/gymact`); autofde-lab stays
EXPLORE-only. This document freezes what was learned and validated on the
`agent/gymact-ggen-abstraction` branch here so the new repo can be seeded from real,
committed, ggen-round-tripped artifacts instead of re-deriving them.

## Source artifacts (exact paths, this branch)

- `gymact/ontology/gymact.ttl` — the protocol-facing TBox (`ga:Gym`, `ga:Operation`,
  `ga:InteractionProfile`, `ga:Observation`, `ga:Effect`, `ga:Score`, `ga:Receipt`, etc.) and
  the 12 `ga:op-*` lifecycle operation instances (discover → materialize → configure → reset
  → start → observe → act → verify → score → checkpoint → restore → teardown).
- `gymact/ontology/profiles.ttl` — the four `ga:InteractionProfile` instances
  (`profile-episodic-step`, `profile-task-harness`, `profile-tool-session`,
  `profile-reconciliation`) and their `ga:mapsAdapterFamily` bindings.
- `gymact/ontology/errc.ttl` — ERRC migration-policy facts (not read in detail this pass;
  drives `queries/errc*.rq` and the generated ERRC report/migration queue).
- `gymact/ggen.toml` — the 11-rule ggen manufacture pipeline (protocol/profiles/subjects
  JSON, MCP tools, A2A skills, BPMN, Rust ABI, WIT ABI, ERRC json/report/migration-queue)
  plus 3 SPARQL validation gates, run via `ggen sync run` inside `gymact/`.
- `docs/papers/papers.ttl`, `docs/papers/gym-lock.ttl`, `docs/papers/smoke-lock.ttl` — the
  80-subject ForwardBench corpus, its 52 pinned-revision vendored submodules, and the
  *observed* (not declared) smoke-test standings.

## Public-vocabulary mapping table (additive, not a rewrite)

This session's ontology review concluded GymAct's TBox could in principle be replaced
entirely by public vocabularies (PROV-O, SOSA/SSN, WoT TD/TM, ODRL, SHACL, EARL, DQV, QUDT,
P-PLAN, PROF). That refactor was **not** applied wholesale on this branch: all 10 generation
rules and 3 validation gates in `ggen.toml` query `ga:*` predicates directly, so a full
TBox swap is a separate, larger migration than lab prep should attempt on a green branch.

Instead, `gymact/ontology/gymact.ttl` now carries additive `owl:equivalentClass` /
`rdfs:subClassOf` alignment triples pointing each `ga:*` class at its nearest public term,
verified by a real `ggen sync run` (11/11 files written, all 3 gates passing, graph hash
`b20e4213db9a55c1681934e9ed08d8ba23f431f72ba213fbddc9a0e1b393ec0a`) after the edit:

| `ga:` class | Public alignment |
|---|---|
| `ga:Gym` | `rdfs:subClassOf schema:SoftwareApplication` |
| `ga:Scenario` | `rdfs:subClassOf prov:Entity, pplan:Plan` |
| `ga:Episode` | `rdfs:subClassOf prov:Activity` |
| `ga:Operation` | `rdfs:subClassOf pplan:Step` |
| `ga:InteractionProfile` | `rdfs:subClassOf prov:Plan, prof:Profile` |
| `ga:ActuationIntent` | `rdfs:subClassOf prov:Entity` |
| `ga:Observation` | `owl:equivalentClass sosa:Observation` |
| `ga:Effect` | `rdfs:subClassOf prov:Entity, sosa:Result` |
| `ga:Score` | `owl:equivalentClass qudt:QuantityValue`, `rdfs:subClassOf dqv:QualityMeasurement` |
| `ga:Receipt` | `rdfs:subClassOf prov:Entity, prov:Bundle` |
| `ga:Verification` *(new)* | `rdfs:subClassOf earl:Assertion`, `ga:realizesOperation ga:op-verify` |

**Recommendation for `seanchatmangpt/gymact`**: when the real library's TBox is authored,
drop the `ga:*` prefix entirely and use `prof:Profile` + PROV/SOSA/WoT/ODRL/SHACL/EARL/DQV
ABox instances directly, per the mapping above — this repo's `ga:*` classes were always the
provisional/protocol-first draft, not the intended production ontology.

## The four interaction profiles, validated against real vendored gyms

Confirmed live in `gymact/generated/subjects.json` after `ggen sync run` on this branch
(each row cross-references `docs/papers/gym-lock.ttl`'s pinned revision and, where present,
`docs/papers/smoke-lock.ttl`'s *observed* standing):

| Profile | `interaction_model` | Example bound subjects (real, in `subjects.json`) |
|---|---|---|
| `profile-episodic-step` | `EPISODIC_STEP` | `cube-standard` (smoke: `SCENARIO_RUNS`), `browsergym` (smoke: `BOOTSTRAPS`), `agentgym`, `agentlab` |
| `profile-task-harness` | `TASK_HARNESS` | `harbor` (smoke: `BOOTSTRAPS`), `agentbench`, `agentdojo` |
| `profile-tool-session` | `TOOL_SESSION` | MCP-family subjects (`mcpmark`, etc.) |
| `profile-reconciliation` | `RECONCILIATION` | `aiopslab` (Kubernetes-family), Terraform-family subjects |

Only 3 of 80 subjects have moved past `NOT_RUN` smoke standing so far (`cube-standard`,
`harbor`, `browsergym`) — this is real, observed evidence, not a claim that all four
profiles are fully qualified. The mapping held for every subject inspected; no subject
required a fifth interaction model.

## Worked Verifier example: `ocel/wasm4pm_bridge.py`

The one place in `autofde-lab` with a real, independently-verified
acknowledgement-≠-effect-≠-verification chain is
`src/autofde_lab/ocel/wasm4pm_bridge.py::discover_and_check`, tested in
`tests/ocel/test_wasm4pm_bridge.py`:

1. **Acknowledgement** — `wpm mining discover`/`conformance` exit `SOLVED` (subprocess
   return code, via `run_subprocess_bounded`). This is *not* evidence of a correct result.
2. **Effect** — a real Petri net is mined (`discover_ilp_petri_net_from_log`, ILP-based
   discovery, `DiscoveryResult{places, transitions, arcs, simplicity, self_fitness}`).
3. **Verification** — the mined net is independently replayed against the *same* log with a
   real token-based-replay engine (`token_replay_pure`) plus ETConformance precision
   (`compute_precision`), producing `ConformanceReport{avg_fitness, precision,
   conforming_cases, deviations}` — a non-trivial, checkable number (e.g. fitness=0.9841,
   precision=0.4965 against `notebooks/artifacts/mcp_user_simulation.ocel.json`), not a
   boolean "it worked."

This is the reference pattern for GymAct's `Verifier` role / `earl:Assertion` alignment
(`ga:Verification` above): a gym's `act` returning success is `sosa:Result`, not
`earl:Assertion` — the assertion is a *separate*, independently-computed judgment over the
resulting state, exactly as `check_conformance` never trusts `discover_petri_net`'s own
exit code as proof the discovered model is any good.

## Python-native dependency decision (for the actual library, not this repo)

Per this session's discussion: GymAct-the-library should compose mature Python frameworks
directly rather than have ggen generate Python source.

- **Use directly**: `pydantic` (canonical typed realization of the semantic profile),
  `fastapi` (HTTP + OpenAPI, derives from Pydantic), `fastmcp` (agent/MCP surface),
  `typer` (CLI, derives from the same typed operation definitions), `faststream`
  (event-driven/AsyncAPI — the one addition this session's research flagged as missing from
  the original day-zero list), `rdflib` + `pyshacl` (semantic graph + constraint
  validation), `gymnasium`/`pettingzoo` (episodic and multi-agent interaction compatibility).
- **Reserve ggen for**: the Rust/WIT/WASM manufacture bridge only —
  `gymact/generated/rust/lib.rs` and `gymact/generated/wit/gymact.wit` on this branch are
  the concrete precedent. Do not generate Pydantic models, FastAPI routes, FastMCP tools, or
  Typer commands from ggen; let those frameworks derive their own surfaces from
  hand-authored Pydantic types instead.
- **Equivalence checkpoint**: where both a Python and a ggen-manufactured Rust
  implementation exist for the same admitted graph fact, they should agree on
  accepted/refused, normalized intent, and standing — this is a test to add in the new repo,
  not something this branch attempts (no Rust GymAct executor exists yet, only the
  generated ABI surface).

## What this handoff explicitly does not do

- Does not create any new Python package, submodule, or runtime code in `autofde-lab`.
- Does not replace the `ga:*` TBox — only adds alignment triples, verified not to break the
  existing 11-file/3-gate `ggen sync run` pipeline (see graph hash above).
- Does not claim GymAct is production-ready; 77 of 80 vendored subjects remain
  `smoke_standing: NOT_RUN` per `docs/papers/smoke-lock.ttl`.
