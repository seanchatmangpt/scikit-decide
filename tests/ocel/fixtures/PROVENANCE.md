# OCEL 2.0 parse fixtures — provenance

`out.json`, `gundam_factory_trace.json`, and `vision_ocel_trace.json` were copied verbatim
on 2026-08-06 from `~/powlv2lsp` (ISC-licensed), where they were produced by an
implementation independent of this package. They are used here only as *parse* fixtures:
they check that `OcelLog.from_ocel2_json` reads a document this package did not write.

`ocel_fig3b.json` in that repo was deliberately **not** copied: it is OCEL **1.0**
(`ocel:events` / `ocel:omap` / `ocel:vmap`), not the OCEL 2.0 schema this package targets.

Notes on what these files exercise:

- Event attributes carry a `time` field, which the OCEL 2.0 schema does not define for
  event attributes (only object attributes are time-versioned). The parser ignores it.
- Some objects carry no `attributes` and no `relationships` arrays at all.

These fixtures are optional. `tests/ocel/test_ocel.py` skips the fixture tests with
`BLOCKED:POWLV2LSP_ABSENT` if the directory is empty, so the package remains testable on a
clean checkout with no sibling repositories.
