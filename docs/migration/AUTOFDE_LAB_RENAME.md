# AutoFDE Lab rename contract

Four categories. Every renamed or preserved surface must be classifiable into exactly one.

## RENAME_NOW
Repository identity, distribution metadata, Python modules/imports, entry-point groups,
generated ontology module names, docs, badges, examples, Binder config, internal scripts,
OpenClaw package references, C++ extension.

## COMPATIBILITY_ALIAS
`import skdecide` forwards to `autofde_lab` with a `DeprecationWarning`, bounded to one
removal milestone (`LEGACY_NAMESPACE_REMOVAL_AFTER`, set when Phase 3 lands). No new
implementation may live in the shim.

## VERSIONED_MIGRATION
Cannot rename by substitution — identifies persisted or externally consumed artifacts:
`urn:skdecide:*` IRIs, receipt/decision-fabric/cache schema identifiers, `SKDECIDE_DATA` /
`~/skdecide_data`, existing MCP tool names and URIs. Dual-read, single-write: new readers
accept both old and new identifiers; writers emit only new.

## DO_NOT_RENAME
Inherited AIRBUS copyright notices, MIT license attribution, citations to Airbus
scikit-decide, unrelated Airbus projects in docs. Renaming a fork does not transfer
inherited copyright — a `NOTICE` records the fork relationship instead.

## Acceptance gates (final, not this commit)

```
distribution name == autofde-lab · 26 domains discovered · 57 solvers discovered
native extension imports · ontology has no stale skdecide.* module ownership
clean recursive checkout succeeds · no PyPI action can target Airbus's package
```

## See also
- `docs/autofde/EXPLORE.md` — the explore/exploit boundary this rename does not change.
- `.claude/rules/standing-law.md` — the vocabulary for classifying migration debt.
