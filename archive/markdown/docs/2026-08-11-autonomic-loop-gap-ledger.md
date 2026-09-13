# Autonomic loop gap ledger — 2026-08-11

Real, evidence-backed standing of the `gymact -> autofde-lab -> ggen ->
(governed execution)` autonomic loop, per stage, in **this repo, this
session**. Uses `.claude/rules/standing-law.md`'s vocabulary
(`ALIVE`/`PARTIAL_ALIVE`/`BLOCKED:<reason>`/`UNKNOWN`/`UNSUPPORTED`) with
`technicalStanding` only — no `organizationalStanding` claim is made or
implied anywhere in this document, per that file's own dimension split.

This is the concrete output of an 80/20 ERRC pass on the
gymact/autofde-lab/ggen doctrine (see
`.claude/rules/autonomic-loop-doctrine.md`): not a redesign, a map of what
is real versus aspirational, so future work targets the actual gaps.

## Stage-by-stage standing

| Stage | Standing | Evidence |
|---|---|---|
| `gymact`: observe/actuate/verify | **ALIVE**, in `~/gymact`, confirmed real but **out of this repo's scope to re-verify** (see boundary note below) | `~/gymact/src/gymact/providers.py`'s real `Environment`/`EnvironmentProvider` protocol (`materialize`/`observe`/`actuate`/`verify`/`checkpoint`/`restore`/`teardown`); `~/gymact/src/gymact/kernel.py:80`'s `class GymAct`; real gym providers under `~/gymact/src/gymact/gyms/` (`sregym.py`, `kubernetes_reconciliation.py`, `multicloud.py`, `terraform_docker_apply.py`, ...). Confirmed present via direct read this session, not re-tested here — a fresh trial run belongs in `~/gymact`'s or this repo's `docs/2026-08-09-powl-actuation-sregym-progress.md` ledger, not this one. |
| `autofde-lab`: infer/plan | **PARTIAL_ALIVE** | Real, independently-testable pieces exist and pass: `src/autofde_lab/reasoning/planner_federation.py` (real PDDL `Astar`/`FF` solvers, `tests/reasoning/test_planner_federation_chicago.py`), `sre_troubleshooting_pipeline.py` (real DSPy stages, GROQ-gated tests), `breed_ensemble.py` (real wasm4pm-mediated ensemble, live-tested this session). No single caller wires observe -> infer -> plan -> candidate end-to-end across all of these for one real scenario yet — each is independently real, not yet composed. |
| `autofde-lab`: falsify/admit | **ALIVE** | `autofde_lab.powl.validate.validate_model` is real, exercised by every generated fixture this session (`k8s_fault_universes.py`, `world_transformation_scenarios.py`) and by `planner_federation_ensemble.py`'s per-solver re-validation discipline. |
| `ggen`: manufacture | **ALIVE** | Real, independently re-verified this session: `scripts/verify_ggen_generation.py` recomputes every generated count (378 k8s-fault universes, 1 world-transformation scenario, 8 constitution modules' dataclass counts) directly from `ontology/*.ttl` via `rdflib`, never trusting `ggen`'s self-report — `standing: ALIVE`, 10/10 checks match, run this session. |
| `ggen/packs` distribution layer | **BLOCKED:NOT_YET_BUILT** | `packs/` does not exist at this repo's root (confirmed this session: `ls packs` -> no such directory). A marketplace-pack-conformance plan for `packs/k8s-fault-taxonomy-pack/` was approved earlier this session but not yet executed — real, scoped, outstanding work, not silently dropped. Also worth naming honestly: the `world-projection`/`lab-projection`/`production-projection` subdirectory layout proposed in this doctrine does **not** match any real convention in `~/ggen-marketplace/packs/` (checked directly: real packs use `ontology.ttl`/`ontology/` + `gates/` + `queries/` + `templates/`, nothing resembling that three-projection split) — that layout is this session's own proposal, not an adopted external standard, and should be built (if built) as a genuinely new convention, not represented as matching an existing one. |
| Governed production execution (`"autofde"` stage) | **UNKNOWN — does not exist as a named system** | Checked directly this session: no `~/autofde` repository exists anywhere on this machine. The doctrine's fourth stage has no real referent here yet. `gymact.actuate()` (real, scoped to gym trials) and this repo's own OpenClaw bridge (real, scoped to this repo's domains/solvers) are adjacent but distinct systems — see `autonomic-loop-doctrine.md` invariant 4 for why neither should be read as satisfying this stage. |

## What this ledger is not

- Not a claim that the loop runs end-to-end for any real scenario today —
  it does not; the "infer/plan" row is explicitly `PARTIAL_ALIVE` for
  exactly this reason.
- Not a claim about `~/gymact`'s own internal test standing — this repo
  does not re-run that repo's tests; the `ALIVE` mark there is scoped to
  "confirmed real and present," not "independently re-verified passing
  this session."
- Not `organizationalStanding` — see `standing-law.md`; nothing here has
  been accepted by an accountable customer, and this ledger doesn't claim
  otherwise.

## See also

- `.claude/rules/autonomic-loop-doctrine.md` — the four boxed invariants
  this ledger's rows correspond to.
- `.claude/rules/gym-actuation-boundary.md` — the code-import-level rule.
- `docs/STATUS.md` — the general in-repo WIP ledger this file is scoped
  narrower than (autonomic-loop doctrine only, not the whole repo).
