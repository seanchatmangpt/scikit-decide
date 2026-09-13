# Project: autofde-lab SOTA Benchmark & Comprehensive Fault Mechanisms

## Architecture
`autofde-lab` provides deterministic fault detection and remediation modules for Kubernetes microservice environments evaluated on the SREGym benchmark suite.
- **Planner Architecture**: `src/autofde_lab_planner/` (and associated modules) provides candidate generation, decision basis, fault detection heuristics, and deterministic remediations across all SREGym fault categories.
- **Environment & Application Helm Charts**: `vendor/gyms/sregym/SREGym-applications/` containing vendored Helm charts for AstronomyShop, FleetCast, TrainTicket, HotelReservation, SocialNetwork, etc.
- **Evaluation Infrastructure**: `vendor/gyms/sregym/sregym/conductor/` and `tests/sota/` for zero-mock testing, problem execution, oracle verification, and benchmark metrics reporting.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Vendored Helm Charts | Vendor missing `opentelemetry-demo` (astronomy-shop), `FleetCast`, `train-ticket`, and `flight-ticket` Helm charts into `SREGym-applications/` | M1 | ORIGINAL_REQUEST §R2 |
| 2 | Environment Unblocking | Verify all blocked sample problems deploy without `Helm chart_path does not exist` errors | M1 | ORIGINAL_REQUEST §R2 |
| 3 | Category-B Fault Mechanisms (B4, B6, B9, B13) | Core detectors & remediators for B4 probe misconfigs, B6 OTel trace diffing, B9 flagd drift, B13 object reconstruction | M2 | ORIGINAL_REQUEST §R1 |
| 4 | ConfigMap & Secret Key Drift (B13) | Detect missing/corrupted keys in mounted ConfigMaps (`configmap_drift`) and Secrets, restore key-value content | M3 | ORIGINAL_REQUEST §R1 |
| 5 | Ingress Misroute & TargetPort Mismatches | Detect and patch misrouted Ingress paths (`ingress_misroute`) and Service `targetPort` misconfigurations (`k8s_target_port-misconfig`) | M3 | ORIGINAL_REQUEST §R1 |
| 6 | CronJob / Scheduled Mutations | Detect and disable recurring actors (`vpa-updater` CronJob in `nightly_rebalance_oom`) while restoring victim deployment resource limits | M3 | ORIGINAL_REQUEST §R1 |
| 7 | Pod Anti-Affinity & Scheduling Deadlocks (B1) | Remove unsatisfiable `podAntiAffinity` rules and `nodeSelector` constraints (`pod_anti_affinity_deadlock`) | M3 | ORIGINAL_REQUEST §R1 |
| 8 | CoreDNS & Service Discovery Faults | Repair CoreDNS ConfigMaps and DNS resolution rules (`stale_coredns_config`, `service_dns_resolution_failure`) | M3 | ORIGINAL_REQUEST §R1 |
| 9 | Workload & Rolling Update Misconfigurations | Revert invalid `maxSurge`/`maxUnavailable` parameters or resource requests (`resource_request_too_large`, `rolling_update_misconfigured`) | M3 | ORIGINAL_REQUEST §R1 |
| 10 | Zero-Mock Test Suite Verification | Ensure all existing and new unit/integration tests in `tests/sota/` pass cleanly with zero mocks (`just test` passes) | M4 | ORIGINAL_REQUEST §R3 |
| 11 | Systematic 100% Benchmark Verification | Execute all SREGym problem trials sequentially, verifying 100% Diagnosis (`Diagnosis.success == True`) and 100% Mitigation (`Mitigation.success == True`) | M4 | ORIGINAL_REQUEST §R2 |
| 12 | Final Evaluation Breakdown Table | Generate complete evaluation results summary with per-problem breakdown table in `docs/` and project reports | M4 | ORIGINAL_REQUEST §R3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Resolve Environment Dependencies | Vendor missing Helm charts in `SREGym-applications/`, unblock applications | None | DONE |
| M2 | Category-B Core Fault Mechanisms | Implement B4, B6, B9, B13 detectors & remediators in `src/autofde_lab_planner/` | M1 | DONE |
| M3 | Comprehensive Fault Mechanism Expansion | Implement B13 key drift, Ingress misroute, targetPort, CronJob mutations, Pod anti-affinity deadlock, CoreDNS, rolling update handlers | M2 | IN_PROGRESS |
| M4 | 100% Benchmark Verification & Testing | Zero-mock test suite expansion, 100% Diagnosis & Mitigation verification on SREGym problems, per-problem breakdown table | M3 | PLANNED |

## Interface Contracts
### Planner ↔ Expanded Fault Detectors & Remediators
- **Detector Input**: `problem_id`, cluster state, OTel trace spans, live ConfigMaps/Secrets/Services/Ingress/CronJobs/PodSpecs, CoreDNS ConfigMaps.
- **Detector Output**: `DecisionBasis` containing identified root cause fault pattern, target resource, and confidence.
- **Remediator Input**: Identified fault pattern, target resource, baseline manifest/config.
- **Remediator Output**: Remediation action (spec patch, rollout undo, ConfigMap/Secret apply, CronJob suspend/delete, Ingress path patch, Service targetPort patch) with execution status.

## Code Layout
- `src/autofde_lab_planner/`: Detector and remediator implementations for all SREGym fault mechanisms.
- `vendor/gyms/sregym/SREGym-applications/`: Vendored Helm charts and application definitions.
- `tests/sota/`: Zero-mock integration and unit test suite.
- `docs/`: Evaluation results, per-problem breakdown tables, and raw TSV outputs.
