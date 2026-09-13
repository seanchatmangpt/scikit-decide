# autofde-lab-k8s-fault-taxonomy-pack

Internal, marketplace-pack-shaped wrapper around this repo's existing
`ontology/k8s-fault-taxonomy.ttl` generation. See `pack.toml` for the full
description and canonical-surface paths. Not published externally.

## Replay

```bash
.venv/bin/python -m pytest tests/test_k8s_fault_taxonomy_shacl_chicago.py -v
.venv/bin/python scripts/verify_ggen_generation.py
```

Both must pass for this pack to be `ALIVE` — the SHACL shape checks
ontology structure independently of `ggen`; `verify_ggen_generation.py`
checks the generated Python output independently of `ggen`'s own
self-report. Neither call is authoritative alone.
