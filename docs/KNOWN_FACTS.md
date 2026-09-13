# Known Facts — Read Before Re-Deriving

Standing-facts file for autofde-lab. Purpose: stop paying the cost of
re-deriving construction/roster/idempotency facts every session when they
were already established. Read this before re-implementing domain
construction fallback logic, re-deriving which domains are zero-arg
constructible, or re-running a manual "diff two runs" idempotency check by
hand.

Each entry: dated, one line of claim, one pointer to where to verify it
directly. If a fact looks stale, verify against its pointer and correct the
entry in the same pass.

## Domain construction

- **2026-08-13** — There is one real, single-source-of-truth zero-arg
  domain-construction helper: `domain_factory(name, kwargs)` in
  `src/autofde_lab/openclaw_runtime.py:211-213`. It resolves `name` via
  `load_registered("domain", name)` and returns a zero-arg closure
  (`lambda: cls(**dict(kwargs))`). Do not re-derive or hand-roll a
  domain-construction fallback in a new call site — call this helper, or if
  a call site needs domain construction and doesn't yet route through it,
  that is itself a finding worth fixing (see the ranked mechanisms doc's
  #2, "collapse the 4x-duplicated fallback logic," for the known
  duplication this file's own callers still carry as of this date).
  Verify: `src/autofde_lab/openclaw_runtime.py:211-213`;
  `load_registered` for the domain registry it reads from.

## Actuation boundary

- **2026-08-13** — This repo computes candidate plans; it does not
  actuate. `gymact` (the real, standalone sibling package at `~/gymact`)
  is the one real actuation surface for any gym — every real
  diagnosis/mitigation trial goes through it, never through a direct
  `vendor/gyms/` import or subprocess launch. `vendor/gyms/` (sregym,
  devops-gym, enterprisebench, ...) are real, exact-pinned checkouts kept
  strictly for reference (read the source, cite file:line, audit/
  materialize the git pin) — this repo never imports or subprocess-launches
  them directly. Verify: `.claude/rules/gym-actuation-boundary.md`;
  `CLAUDE.md`'s opening section.

## Idempotency

- **2026-08-13** — Byte-identical / idempotent-rerun is a recurring,
  already-established invariant in this repo, not a fact to rediscover per
  feature: e.g. `docs/level4-migration-matrix.md`'s
  `SIX_GYM_KERNEL_GATE = PASSED` note documents `level4_witness.py`,
  `verify.py`, and the SHACL shapes being byte-identical across all six
  gyms; `docs/ecosystem-standing.md` documents a receipt verified
  byte-identical across two independent builds (S5). When a new
  materializer/generator needs an idempotency check, look for whether the
  target already has a committed byte-identical-rerun test or documented
  check (e.g. `ontology/CLAUDE.md`'s drift tests) before manually running
  it twice and diffing by hand — and if you do write a new check, make it
  a committed, re-runnable script/test (per this file's own convention),
  not a one-off manual ritual repeated from memory each session.
  Verify: `docs/level4-migration-matrix.md:18`, `docs/ecosystem-standing.md`
  (search "byte-identical"), `ontology/CLAUDE.md:96`.

## How to use this file

Before re-implementing domain-construction fallback logic, re-deriving the
actuation boundary from scratch, or manually re-running a "diff two runs"
idempotency ritual, check this file first. If what you need isn't here, do
the real investigation, then add a dated entry so the next session doesn't
pay the same cost.
