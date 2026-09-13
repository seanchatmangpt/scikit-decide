# AutoFDE → mmdio planning export

AutoFDE-Lab is the planning-semantic authority. `mmdio` is the non-actuating,
human-legible documentation/I/O plane.

```text
PDDL / PPDDL / PDDL+ / RDDL / POWL 2.0
                │
                ▼
        native AutoFDE semantics
                │
                ▼
   bounded mmdio PlanningGraph carrier
                │
                ▼
              mmdio
                │
     Mermaid planning documents
                │
        receipts + replay
```

## Export modes

| Formalism | Export mode | Evidence boundary |
|---|---|---|
| PDDL | bounded runtime state-space enumeration | deterministic native successors |
| PPDDL | bounded runtime state-space enumeration | native successor distributions, normalized probabilities |
| PDDL+ / TPDDL | bounded temporal runtime enumeration | observed state time and transition duration |
| RDDL | bounded observed rollout | actual reset/step observations and values; no false full-model enumeration |
| POWL 2.0 | structural traversal | transitive-reduced precedence, choice transitions, guards and cycles |

Every state-space export is explicitly finite through `ExportLimits`. Exhaustion
of a bound is represented by `metadata.truncated`; it is never reported as
complete exploration.

## Authority

The carrier claim ceiling is:

```text
NATIVE_PLANNING_SEMANTICS_TO_MMDIO_PROJECTION_ONLY
```

The exporter cannot actuate a planner, GymAct world, external API, filesystem
outside an explicitly requested JSON write, or BRCE consequence. Generated
Mermaid is a projection, not planning authority.

## Example

```python
from autofde_lab.interchange import ExportLimits, export_ppddl_domain

planning = export_ppddl_domain(
    domain,
    subject="sony-enterprise-release-policy",
    limits=ExportLimits(max_states=256, max_depth=24),
)
planning.write_json("enterprise-planning-graph.json")
```

`mmdio planning enterprise-planning-graph.json --output planning-docs/` then
manufactures the applicable Mermaid views and receipt set.

## Cross-repository crown

The dedicated GitHub Actions crown pins the exact `mmdio` planning-contract
commit, lifts all five AutoFDE export families with the real `mmdio` loader,
manufactures every applicable Mermaid planning document, verifies each receipt,
and passes all generated Mermaid through the pinned Mermaid 11.16.0 parser.
