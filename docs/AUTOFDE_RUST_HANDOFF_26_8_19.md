# AutoFDE Lab v26.8.19 → Rust AutoFDE handoff

Status: **PARTIAL_ALIVE** until the exact-graph qualification workflow emits a replayable
`autofde-lab.rust-handoff-receipt/1` for the exact candidate head.

## Boundary

`autofde-lab` remains the SELECT/search control plane. It does not acquire DO authority.

```text
O → O* → autofde-lab SELECT
        → autofde.manufacture-request/1
        → ggen CONSTRUCT
        → autofde.capability-bundle/1
        → Rust AutoFDE admission
        → BRCE DO
        → execution receipt / replay / standing
```

The Lab and Rust repositories intentionally retain separate canonical ontologies. The
handoff is revision-bound interoperability, not ontology aliasing.

## Admitted graph

The machine-readable graph is `ecosystem/autofde-rust-handoff.toml`.

- Lab admitted base: `d3537444802beb8b5c9fe94d37f31b062309b6d6`
- ggen manufacturer: `7fc324df397973004059c37b752a365315d7bfb8`
- Rust AutoFDE consumer: `91daa89c9f29fc69b8997ac8d3ad8981641e239a`
- GymAct currently admitted by Lab: `524d0bcab71e414b47a4cc6ee5baa80b43b9f9c5`
- GymAct candidate for re-admission: `04bccc45ea0c0793ca2efbb0d08cc610880e5bb8`

The final Lab candidate SHA is deliberately not embedded into its own source tree. The
qualifier observes exact `HEAD`, proves it descends from the admitted base, and binds that
SHA into the qualification receipt. This avoids a self-referential commit-hash contract.

## Contract

Rust AutoFDE already defines the handoff ABI:

- manufacture request: `autofde.manufacture-request/1`
- manufacture receipt: `autofde.manufacture-receipt/2`
- manufacturer validator: `ggen:autofde-capability-bundle/2`
- capability bundle: `autofde.capability-bundle/1`
- runtime ABI: `autofde.runtime/26.8.8`

A manufacture request carries exact `lab_revision` and `ggen_revision` and is forced to
`authority_mode = "external-only"` with `do_authority = false`. Construction therefore
cannot smuggle runtime authority across the boundary.

## GymAct promotion

`pyproject.toml` remains pinned to the currently admitted GymAct revision until the
candidate is qualified against the exact Lab/ggen/Rust graph. The v26.8.19 closure does
not mutate that dependency or `uv.lock` from inspection alone.

After a successful exact-graph qualification, dependency promotion is a separate
admission transition:

1. preserve the successful qualification receipt;
2. update the GymAct exact revision and regenerate the lockfile;
3. execute the Lab test/packaging boundary against the new lock;
4. re-run exact-graph qualification;
5. admit the new pin only if both receipts replay.

## Replay

The CI workflow `.github/workflows/autofde-rust-handoff.yml` checks out all four exact
subjects and runs:

```bash
python scripts/verify_autofde_rust_handoff.py \
  --lab . \
  --ggen _deps/ggen \
  --autofde _deps/autofde \
  --gymact _deps/gymact
```

The verifier emits a deterministic JSON receipt. CI independently recomputes the receipt
digest and requires `REPLAY_MATCH`.

## Standing law

A source manifest, branch, PR, checkout, or green unrelated workflow is not the crown.
This handoff reaches **ALIVE** only for the exact subject SHA that executed all checks and
produced a replayable receipt. That standing does not transfer to Rust AutoFDE runtime
DO, a cloud deployment, or GymAct promotion.
