# ForwardBench / AutoFDE research corpus

This directory is an **EXPLORE** source surface for papers, executable agent/cloud gyms, and ggen-manufactured ForwardBench integration.

## Canonical source

`papers.ttl` is the semantic source of truth. It currently describes **52 papers**, **80 logical benchmark subjects**, and **52 physical vendor projects**. Public vocabularies carry scholarly/software/provenance semantics; the small `afb:` vocabulary is limited to execution metadata that those standards do not define.

`ggen sync run` projects the graph into `generated/forwardbench/`: registry, plans, MCP tool declarations, benchmark matrix, paper manifest, and lazy submodule sync/probe helpers. Do not manually fork those projections.

Observed facts do not get written back into the declaration graph. Exact git pins, PDF hashes, and executed smoke standing live in `gym-lock.ttl`, `paper-lock.ttl`, and `smoke-lock.ttl` respectively and are imported by ggen.

## Authority

The generated AutoFDE adapter is SELECT-only. Cloud-security labs that require AWS/Azure/GCP authority remain `REFUSED:LIVE_AUTHORITY_REQUIRED` until a named allowlisted environment is explicitly authorized. Vendoring a repository is not permission to deploy it.

## Standing ladder

`UNKNOWN_REPOSITORY -> PINNED -> BOOTSTRAPS -> SCENARIO_RUNS -> AUTOFDE_ADAPTER_ALIVE`.

A higher standing is recorded only from exact execution evidence. Paper retrieval and paper-result reproduction are separate: a vendored PDF remains `NOT_REPRODUCED` until its reported result is actually reproduced.
