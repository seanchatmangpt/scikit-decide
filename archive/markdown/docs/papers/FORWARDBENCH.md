# ForwardBench manufacturing contract

`papers.ttl` models papers, benchmark subjects, official software projects, adapter families, and generic P-PLAN/PROV execution plans. ggen performs CONSTRUCT/SELECT/Tera manufacture; AutoFDE Lab selects candidate interactions; no generated MCP or registry surface owns DO authority.

Preferred interoperability order: **CUBE -> Harbor -> BrowserGym -> MCP -> bounded native adapter**. CUBE is preferred because it standardizes Tool/Task/Benchmark/Observation/Action. Harbor collapses terminal/container benchmarks behind one harness. BrowserGym collapses web/enterprise browser benchmarks behind Gymnasium-compatible environments.

The design intentionally keeps all benchmark submodules lazy (`update = none`) so ordinary recursive project checkout does not download the entire corpus. `generated/forwardbench/sync-gyms.sh <vendor>` materializes only a requested subject.
