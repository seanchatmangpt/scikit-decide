# PRD/ARD — mmdio Executive-Projection Engine & Deterministic AI-DLC

Status: PROPOSED. Dated 2026-08-14.

> **Standing disclaimer, read first.** This document proposes a capability —
> `mmdio` as a deterministic executive-projection engine over the Chatman
> Ecosystem's canonical graph — that **does not exist today**, in this repo or
> in any sibling repo. Every claim below about an *existing* capability cites a
> real file path and carries a standing tag from
> [`.claude/rules/standing-law.md`](../.claude/rules/standing-law.md)
> (`ALIVE` / `PARTIAL_ALIVE` / `BLOCKED:<reason>` / `UNSUPPORTED` / `UNKNOWN`).
> Every claim about a *proposed* capability is marked `PROPOSED` and is not to
> be read as shipped. This document follows the precedent set by
> [`docs/2026-08-11-v26.8.11-fortune5-togaf-prd.md`](2026-08-11-v26.8.11-fortune5-togaf-prd.md).

## 1. Problem statement

A representative external requirement (a Principal Forward Deployed Engineer
role) asks for AI-DLC: LLM-assisted coding tools, RAG, agent frameworks, and
"repeatable development patterns" that raise engineering velocity. Those two
asks are in tension. If a pattern produced by an LLM-assisted workflow is truly
repeatable, re-asking a probabilistic model to reproduce it on every occurrence
is not the destination — the destination is formalizing the pattern once and
generating it deterministically thereafter. Stated as a product thesis:

> Successful AI-assisted engineering work should be continuously convertible
> into deterministic, generated enterprise capability, until the AI is no
> longer required for that class of work.

This repo's own doctrine already states the narrow version of this for its own
execution path:
[`docs/agentic-fabric.md`](agentic-fabric.md) restricts DSPy/LLM use to
*unmodeled* natural language and keeps the registered domain/solver match-and-solve
path LLM-free (`ALIVE`, ceiling claim
`REGISTERED_DOMAIN_SOLVER_MATCH_AND_BOUNDED_ROLLOUT_ONLY`). This PRD/ARD
generalizes that principle to a proposed cross-repo capability: reconstituting
an *external* system (a network, a cloud estate) into a canonical graph, closing
generator gaps, manufacturing artifacts deterministically, and projecting the
result to a human audience without an LLM in the rendering path.

## 2. Product requirements (PRD)

| ID | Requirement | Precedent / owner | Standing today |
|----|-------------|--------------------|-----------------|
| R1 | Reconstitute an existing system into a canonical graph, emitting an explicit `observed / inferred / contradiction / invariant / UNKNOWN` decomposition. `UNKNOWN` is never collapsed into a value. | `ggen-legacy`'s decision-engine gate (`~/ggen-legacy`, real 38-line gate) | `PARTIAL_ALIVE` — the gate exists; a full reconstitution pipeline over an arbitrary external system does not |
| R2 | Close generator gaps: manufacture a new generator for any canonical-graph primitive no existing generator covers. | `ggen-create`'s reverse compiler (`~/ggen-create`) | `UNSUPPORTED` — reverse compiler is 0 lines |
| R3 | Manufacture artifacts from admitted graph state, with a content-addressed receipt per artifact. | `ggen` (`~/ggen`) | `ALIVE` — `ggen sync run` has been executed for real in this ecosystem, producing real BLAKE3 receipts (`docs/STATUS.md` pass 9; `ggen receipt verify`) |
| R4 | Render the *same* admitted canonical graph differently per audience/objection, selected deterministically from classified conversational or query state — not narrated by an LLM. | `mmdio` (`github.com/seanchatmangpt/mmdio`) | `UNSUPPORTED` — registered in this repo only as a loadable WASM component descriptor (`src/autofde_lab/wasm/_registry.py:133-135`, `_artifacts.py:76`); no choreography/projection logic exists here or is confirmed in the mmdio repo itself |
| R5 | Every projection and every generated artifact is traceable through one identity chain: candidate → admission → authority → actuation → observation → receipt. | Already required repo-wide | `ALIVE` as a *rule* (`.claude/rules/no-dual-bookkeeping.md`, `.claude/rules/level4-completion-law.md`); `PARTIAL_ALIVE`/`BLOCKED` as an end-to-end *chain*, see §4 |

R1–R4 are new proposed work. R5 is a reuse requirement: the identity-chain
discipline this repo already enforces internally must extend to any
reconstitution/projection pipeline built under R1–R4, not be re-derived.

## 3. Architecture requirements (ARD)

The actuation law already governs this repo and must bound any new component:

> "A planner selects; the broker authorizes; the executor performs; the
> verifier evaluates." — [`.claude/rules/ecosystem-boundary.md`](../.claude/rules/ecosystem-boundary.md)

Mapped onto R1–R5:

```
external system (network, cloud, ...)
        │
        ▼  R1 reconstitution         [ggen-legacy, PARTIAL_ALIVE]
canonical graph (observed/inferred/contradiction/invariant/UNKNOWN)
        │
        ▼  R2 generator-gap closer   [ggen-create, UNSUPPORTED]
generator set covering the graph's primitives
        │
        ▼  R3 manufacture (μ)        [ggen, ALIVE]
artifacts + BLAKE3 receipts
        │
        ▼  R5 identity chain          [rule ALIVE, chain PARTIAL_ALIVE/BLOCKED]
admission → authority → actuation → observation → receipt
        │
        ▼  R4 executive projection   [mmdio, UNSUPPORTED / PROPOSED]
audience-specific, deterministic rendering of admitted evidence only
```

**Hard architecture requirement**: `mmdio` (R4) is read-only over already-admitted
evidence. It must never gain ambient authority to actuate, and must never render
un-admitted or predicted state as though observed — this is the same law
[`.claude/rules/absence-is-not-evidence.md`](../.claude/rules/absence-is-not-evidence.md)
already states for planners: `UNKNOWN` survives every projection until evidence
discharges it, or the projection returns `UNREPRESENTABLE:<typed_reason>`.

**Governing law for R3+R5**, restated from
[`FORWARD_DEPLOYMENT.md`](../FORWARD_DEPLOYMENT.md):

```
A = μ(O*)
R = receipt(A)
```

This repo (`autofde-lab`) is explicitly and only the planner (candidate-plan
computation over admitted `O*`) in this chain — it "computes candidate plans, it
does not actuate." Any implementation of R1/R2/R4 built to satisfy this PRD must
respect that boundary and route actuation, if any is ever required, through the
existing broker/executor surfaces (`mfw`, `bcinr`/`gymact`), never directly.

## 4. Current cross-repo standing baseline (cited, not restated optimistically)

From [`docs/ecosystem-standing.md`](ecosystem-standing.md), the S1–S7 crown
chain this PRD's R1–R5 sit on top of:

| Stage | Owner | Standing |
|---|---|---|
| S1 exemplar → candidate authority | ggen-create | `UNSUPPORTED` |
| S2 candidate → admitted | mfw | `ALIVE` |
| S3 plan computation | autofde-lab (this repo) | `ALIVE` |
| S3b plan → POWL2 projection | autofde-lab | `ALIVE` (projection only) |
| S3c admitted POWL → executed | mfw + bcinr | `PARTIAL_ALIVE` (executor not wired to broker) |
| S4 manufacture (μ) | ggen | `PARTIAL_ALIVE` |
| S5 independent verification | ggen / ggen-legacy | `PARTIAL_ALIVE` |
| S6 replay / sunset | ggen-legacy | `PARTIAL_ALIVE` |
| S7 recursive bootstrap | — | `UNSUPPORTED` |

**The crown is `BLOCKED` end-to-end.** S3c is named there as the decisive gap:
"a plan that is never executed makes every downstream stage moot." R1–R4 in
this PRD do not close S3c and must not be read as doing so.

Three-axis standing (`docs/ecosystem-standing.md` pass 4):
`technicalStanding` can reach `ALIVE` on a verified artifact;
`organizationalStanding` and `enterpriseStanding` are `UNSUPPORTED` — nothing in
the ecosystem computes them yet, including anything proposed here.

## 5. Non-goals / boundaries

- **Not** a claim that the S1–S7 crown is closed. It remains `BLOCKED`.
- **Not** a claim that this repo's planner is competitive with published
  benchmark SOTA. Per `docs/STATUS.md` pass 20, an unbiased stride-5 sample of
  sregym problems scored this repo's non-LLM planner at 6.7% (Diagnosis) /
  6.7% (Mitigation) against a published SOTA range of 38.9–72.6% /
  57.3–78.5%. This PRD does not change that number and must not be cited
  alongside it as though it does.
- **Not** an organizational- or enterprise-standing claim. Both remain
  `UNSUPPORTED` by construction (`.claude/rules/standing-law.md`).
- `mmdio` is **not implemented** as a choreography/projection engine anywhere
  in this ecosystem today. Its only presence in this repo is a WASM component
  registration entry.

## 6. Verification / definition of done

Each requirement moves from `PROPOSED`/`UNSUPPORTED` to `ALIVE` only on a
Chicago-style test or artifact run this session, per
[`.claude/rules/testing-chicago-style.md`](../.claude/rules/testing-chicago-style.md) —
never on a description:

- **R1**: a real reconstitution run over one real sample system (e.g. a small
  real network or cloud config, not a synthetic fixture), producing a real
  observed/inferred/contradiction/invariant/UNKNOWN decomposition, inspectable
  after the run.
- **R2**: a real generator, previously absent, manufactured for one concrete
  primitive the R1 output needed and no existing generator covered; verified by
  `ggen`/`ggen-create`'s own real build/test path, not a design doc.
- **R3**: a real `ggen sync run` against the R1/R2 output producing a real
  artifact with a verifiable BLAKE3 receipt (`ggen receipt verify`).
- **R4**: a real `mmdio` render, driven by real classified query/conversation
  state and real admitted evidence from R1–R3 — never a canned deck or a
  hand-authored slide sequence standing in for the render.
- **R5**: the same identity-chain mutation-falsifier discipline already
  required by `.claude/rules/level4-completion-law.md` — construct an
  otherwise-complete R1–R4 run, mutate one identity edge, and confirm the chain
  refuses rather than silently admitting it.

## 7. See also

- [`FORWARD_DEPLOYMENT.md`](../FORWARD_DEPLOYMENT.md) — the portfolio law this
  document's R3/R5 restate rather than reinvent.
- [`docs/ecosystem-standing.md`](ecosystem-standing.md) — the S1–S7 crown
  baseline cited in §4; re-read before citing further, per its own instruction.
- [`.claude/rules/ecosystem-boundary.md`](../.claude/rules/ecosystem-boundary.md) —
  the actuation law and the ggen/ggen-create/ggen-legacy/mfw/bcinr role table.
- [`.claude/rules/absence-is-not-evidence.md`](../.claude/rules/absence-is-not-evidence.md) —
  the `UNKNOWN`-preservation law R1 and R4 must both satisfy.
- [`.claude/rules/no-dual-bookkeeping.md`](../.claude/rules/no-dual-bookkeeping.md) and
  [`.claude/rules/level4-completion-law.md`](../.claude/rules/level4-completion-law.md) —
  the identity-chain discipline R5 reuses.
- [`docs/agentic-fabric.md`](agentic-fabric.md) — the existing, narrower,
  `ALIVE` precedent for keeping LLM use out of a normal execution/rendering
  path.
- [`docs/STATUS.md`](STATUS.md) — in-repo WIP ledger, including the pass 20
  sregym benchmark result cited in §5.
- [`docs/2026-08-11-v26.8.11-fortune5-togaf-prd.md`](2026-08-11-v26.8.11-fortune5-togaf-prd.md) —
  the PRD/ARD precedent this document's format follows.
