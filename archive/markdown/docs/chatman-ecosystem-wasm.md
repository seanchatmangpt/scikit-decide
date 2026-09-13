# Chatman ecosystem WebAssembly federation

`autofde_lab.wasm` packages sixteen executable, exact-source-pinned WebAssembly
adapters and exposes each one through a typed Python binding. The adapters are
embedded in the wheel, require no filesystem materialization, import no ambient
host capabilities, and execute through Wasmtime or Node.js WebAssembly.

```python
from autofde_lab.wasm import ChatmanEcosystem

ecosystem = ChatmanEcosystem()
result = ecosystem.ggen.self_test()
assert result.status == "ALIVE"
assert result.receipt["artifact"]["sha256"] == result.component.artifact_sha256
```

Bindings include `ggen`, `ggen_legacy`, `ggen_create`, `wasm4pm`,
`wasm4pm_compat`, `lsp_max`, `star_toml`, `mfact`, `powl`, `fgn`, `mfw`,
`mmdio`, `mu_mcpp`, `mu_truex`, `cargo_cicd`, and `ferroplan`. Compatibility
aliases include `POWL`, `mcpp`, and `truex`.

## Scope of standing

Every embedded module implements the federation operations `self_test`,
`describe`, and `admit`. These operations prove the Wasm transport, exact
component/source identity, capability-free import boundary, artifact digest,
Python binding, response ABI, and receipt binding. The receipt scope is
`federation-adapter`, and `output.semantic_execution` is explicitly `false`;
the adapter does not pretend that a component-specific command such as ggen
rendering or POWL planning ran when it did not.

Unknown operations return the typed standing `REFUSED` rather than collapsing
unsupported semantics into success.

### ERRC standing invariant

`BLOCKED` is not an admissible ERRC standing. It cannot be returned by a guest,
recorded as a successful checkpoint, or used to defer unfinished manufacture.
A denied or unavailable authority is `REFUSED`. A failed manufacture or rebuild
is `BUILD_BROKEN`. Verified execution is `ALIVE`. Any guest response containing
`BLOCKED` is rejected as an ABI violation.

## Materialization and replay

```bash
python -m autofde_lab.wasm.build --output build/chatman-wasm
```

The command writes all sixteen `.wasm` files, the canonical WIT contract, the
exact registry, and `build-report.json`. It then reloads the materialized bytes,
verifies their SHA-256 identities, executes every module, and records sixteen
`ALIVE` self-test receipts.

The core ABI exports `memory`, `chatman_alloc`, `chatman_invoke`, and
`chatman_dealloc`. Modules have zero imports and a fixed three-page memory
maximum. The host rejects artifact drift, missing exports, ambient imports,
invalid response lengths, malformed JSON, receipt identity mismatch, and any
attempt to return the non-standing `BLOCKED`.
