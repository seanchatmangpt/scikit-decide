# Persisted and externally-consumed artifacts

Not everything renames by substitution. `docs/migration/AUTOFDE_LAB_RENAME.md`'s
`VERSIONED_MIGRATION` category exists for identifiers that are **persisted to disk, embedded in
a cache, or consumed by something outside this process** — renaming those in place would break
every reader of data written before the rename. The rule: **dual-read, single-write**. New
readers accept both the old and new identifier; writers emit only the new one going forward.

## The general pattern

```
old identifier  ─┐
                  ├─▶  reader accepts either  ─▶  writer emits new only
new identifier  ─┘
```

Concretely, this means: a schema/version string embedded in a persisted record should be checked
against both the pre-rename and post-rename value on read, but every write after the rename lands
uses the post-rename value exclusively. Once no reader depends on the old value anymore (a
question this repo's `docs/STATUS.md` ledgers, not this page), the old-value branch can be
removed as its own follow-up — that removal is not part of the rename itself.

## What this repository's schema identifiers actually look like right now

This is a snapshot, not a completion claim — check the source for current values before relying
on this table.

| Identifier | Location | Value |
|---|---|---|
| Decision fabric cache schema | `src/autofde_lab/fabric/cache.py::_CACHE_SCHEMA` | `autofde_lab.fabric.errc-cache/1` |
| Decision fabric schema | `src/autofde_lab/fabric/service.py::_FABRIC_SCHEMA` | `autofde_lab.decision-fabric/2` |
| Agent epoch receipt schema | `src/autofde_lab/agent/models.py::EPOCH_RECEIPT_SCHEMA` | `skdecide.agent.epoch_receipt/1` |
| Agent outcome schema | `src/autofde_lab/agent/models.py::AGENT_OUTCOME_SCHEMA` | `skdecide.agent.outcome/1` |

Two of these four (`cache.py`, `service.py`) already carry the renamed `autofde_lab.` prefix. The
two in `agent/models.py` still carry the pre-rename `skdecide.` prefix — this is not yet closed
out under the `VERSIONED_MIGRATION` category and should not be read as done. No dual-read branch
(code that explicitly accepts both an `skdecide.*` and `autofde_lab.*` value for the same
identifier) was found in this tree as of this writing; whichever value is written is currently
also the only value any reader accepts.

## IRIs (deliberately unrenamed)

`urn:skdecide:*` IRIs are used as-is, unrenamed, in:

- `src/autofde_lab/fabric/fde.py` (`FDE`, `FDET` namespace prefixes)
- `src/autofde_lab/fabric/ontology.py` (`SKD`, `SKDT` namespace prefixes)
- `src/autofde_lab/fabric/pddl_engine.py` (`powl_base_iri` default)

These are exactly the kind of externally-consumed identifier `VERSIONED_MIGRATION` names —
renaming an IRI changes the identity of every triple and every previously-emitted document that
referenced it. They stay as `urn:skdecide:*` rather than becoming `urn:autofde_lab:*` by
substitution; any future rename of these follows the same dual-read discipline as the schema
strings above, not a find-and-replace.

## `SKDECIDE_DATA` / `~/skdecide_data`

`docs/migration/AUTOFDE_LAB_RENAME.md` names the `SKDECIDE_DATA` environment variable and
`~/skdecide_data` default data directory as `VERSIONED_MIGRATION` surfaces. This page does not
independently re-verify their current renamed/unrenamed state beyond what's listed above — check
`src/autofde_lab/hub/` and `src/autofde_lab/utils.py` for the current environment-variable name
before relying on either form in a script.

## See also

- `docs/migration/AUTOFDE_LAB_RENAME.md` — the four-category contract, `VERSIONED_MIGRATION`
  section.
- `docs/migration/python-namespace.md` — the Python import path rename this page does not cover.
- `docs/migration/from-scikit-decide.md` — the user-facing migration summary.
- `.claude/rules/standing-law.md` — why this page states a snapshot, not a completion claim.
