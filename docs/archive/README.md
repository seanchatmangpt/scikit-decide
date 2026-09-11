# Archive

Docs moved here are superseded — their claims are fully carried by a later, still-live
document — never deleted, per `docs/CLAUDE.md`'s convention ("Dead docs... should be moved to
`docs/archive/` with a note on why they were superseded") and the repo-wide rule that
historical corrections stay visible (`docs/CLAUDE.md` invariant 2). Each archived file keeps
its original content unmodified below a one-line "Archived <date> — superseded by X" header.

This directory is populated by a real, per-file triage pass (32 dated `docs/2026-08-*.md`
snapshots reviewed for the v26.9.1 documentation sweep, 2026-09-01), not a blanket date cutoff.
31 of 32 were kept in place — most are either still cited by an active `.claude/rules/*.md`
file, cited by another live doc, or standalone records with no specific named successor that
fully covers their claims. Archiving requires both: (a) no real inbound reference from outside
`docs/archive/` itself, and (b) a specific, named, still-live successor document that actually
covers the archived doc's claims (verified by reading both, not assumed from filenames).

## Archived

- [`2026-08-08-corrections.md`](2026-08-08-corrections.md) — superseded by `docs/STATUS.md`.
  One-off note on commit `070cc3a`'s wrong planner-inventory figures; the corrected numbers
  are carried verbatim in `docs/STATUS.md`. No inbound references from any other doc or
  active rule file.
