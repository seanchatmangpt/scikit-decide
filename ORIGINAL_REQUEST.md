# Original User Request

## Initial Request — 2026-08-09T16:11:54Z

Implement all high-yield Category-B fault detection and remediation mechanisms in `autofde-lab` and resolve missing Helm chart environment dependencies to achieve SOTA performance on the SREGym benchmark suite.

Working directory: `/Users/sac/autofde-lab`
Integrity mode: development

## Requirements

### R1. Implement High-Yield Category-B Fault Mechanisms
Expand `src/autofde_lab_planner` (or equivalent general planner modules in `autofde-lab`) to implement deterministic detectors and remediators for remaining high-yield Category-B fault patterns in SREGym:
- **B6 (OTel Trace Diffing)**: Compare active Jaeger/OpenTelemetry span trees against baseline traces to detect broken downstream RPC paths or latency anomalies.
- **B9 (flagd Config Drift)**: Diff live `flagd` feature flag configurations against public defaults to identify misconfigured feature flags.
- **B4 (Probe Heuristics & Liveness/Readiness Faults)**: Detect probe endpoint misconfigurations or failing readiness checks and revert spec/probe parameters.
- **B13 (Missing/Corrupted Object Reconstruction)**: Reconstruct missing Kubernetes ConfigMaps, Secrets, or Services from Helm manifests or baseline definitions.

### R2. Resolve Environment Dependencies
Download and vendor missing Helm charts (`opentelemetry-demo` for `astronomy-shop`, `FleetCast`, and `train-ticket`) into `SREGym-applications/` so that all 123 active registered SREGym problems can deploy without `Helm chart_path does not exist` errors.

### R3. Systematic Benchmark Evaluation & SOTA Verification
Execute an unbiased, programmatically generated systematic sample across the full SREGym problem suite (using `ProblemRegistry().get_problem_ids(all=True)`). Verify diagnosis and mitigation performance against published SOTA baselines (Diagnosis > 72.6%, Mitigation > 78.5%).

## Acceptance Criteria

### Task Coverage & Solver Performance
- [ ] All 10 environment-blocked problems (AstronomyShop, FleetCast, TrainTicket) successfully deploy without `BLOCKED:ENVIRONMENT` chart errors.
- [ ] At least 4 high-yield Category-B fault mechanisms (B6, B9, B4, B13) are implemented, increasing structural task coverage by 30+ problems.
- [ ] On an unbiased, representative sample of SREGym tasks, achieve Diagnosis success rate >= 75% and Mitigation success rate >= 75%.

### Code Quality & Verification
- [ ] All existing and new unit/integration tests in `tests/sota/` pass with zero mocks (`just test` passes cleanly).
- [ ] Detailed evaluation results are saved to `docs/` with complete per-problem breakdown tables and raw TSV outputs.
