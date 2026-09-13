# Reconstitution: what should happen next

Records the decision from the adversarial review of whether `autofde-lab` should join the
reconstitution system built this session, and the concrete follow-ups from that review.

## Standing

`technicalStanding`: `ALIVE` for the reconstitution artifacts themselves (schema, verifier,
two manifests, drift script) — all independently re-verified this session against their final
committed paths in `authority/ecosystem-reconstitution/` (0 schema errors, all 5 cross-field
checks pass on both manifests, real digests re-fetched against live GitHub content).

`autofde-lab` as a reconstitution *subject* (as opposed to *author*, which it already is):
`UNKNOWN`, tending no. Not decided by default — decided by review, per
`.claude/rules/absence-is-not-evidence.md`: eligibility (no rule blocks it) is not a case (a
real reason to do it), and only the former was found.

## Decision

**Do not add `autofde-lab` as a `repositories[]` subject in either manifest**, and do not add
it to `ggen-legacy`'s own independent 19-repo reconstitution program, absent an explicit
request from that program's own authority.

Grounds, each independently verified this session:

1. **Eligibility is clear but not a reason.** `ggen-legacy`'s architecture doc defines
   subject-hood as a read-only fetch-and-receipt operation that explicitly disclaims standing
   promotion, tree-combination, or authority transfer. This does not conflict with
   `autofde-lab`'s own law ("computes candidate plans, does not actuate") — the two are
   orthogonal, not in tension. But clearing a blocker is not itself a reason to proceed.
2. **The real dependency edge does not point where inclusion would need it to.** Confirmed via
   real code inspection (not prose): `autofde-lab` has a genuine dependency on `gymact` — an
   editable path dependency locked in `uv.lock`, real `import gymact.*` statements across 6
   files in `src/`, a real `gymact.providers` entry-point registration. It has **zero** real
   dependency on `ggen` or `ggen-marketplace` — no references anywhere in `pyproject.toml`,
   `uv.lock`, `vendor/`, or as an import in `src/`. The one textual mention of
   "ggen-marketplace" in the codebase is a comment documenting that no such integration
   exists. `ggen-legacy`'s 19-repo program is built around the `ggen` product family;
   `autofde-lab` isn't part of it by any real dependency evidence.
3. **The authority-side record is silent, both ways.** Grepped the real local `~/ggen-legacy`
   checkout directly (including `authority/` and `foundry/`) for any reference to
   `autofde-lab` — zero matches. The two commits the local checkout was behind `main` by were
   confirmed (via `gh api`) to be unrelated CI-workflow-count plumbing, not reconstitution
   scope changes. The authority that would need to name `autofde-lab` a subject never has.

## If this is revisited

Two concrete options, with real costs stated rather than assumed:

- **Option A (status quo)**: leave both manifests as they are. Zero cost, matches the
  reviewed default.
- **Option B (add it)**: append to `ggen-legacy`'s own existing manifest (not a new file here
  — a second manifest would fragment the single-authority record its own Preserve/Fence
  clauses depend on). Requires: (1) a clean checkout of `master` (not a dirty feature branch —
  the illustrative entry computed during review was rejected for exactly this reason,
  `receipt_basis: WORKING_TREE_NOT_HEAD_COMMIT`); (2) every `content_receipts` digest
  regenerated via `git show <sha>:<path>`, never a plain filesystem read; (3) landed via a real
  PR against `seanchatmangpt/ggen-legacy`, following this session's own real-branch,
  real-CI-poll, merge-only-when-green discipline.

## See also

- `authority/ecosystem-reconstitution/` — the real artifacts this record describes.
- `.claude/rules/absence-is-not-evidence.md` — the doctrine this decision applies directly.
- `.claude/rules/standing-law.md` — the vocabulary this record's Standing section uses.
