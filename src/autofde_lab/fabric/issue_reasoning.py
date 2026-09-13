"""Generalized compiled issue reasoning for recurring structured failures.

This module is deliberately candidate-only.  It recognizes admitted troubleshooting
archetypes, eliminates hypotheses from structured evidence, and constructs a repair
*intent*.  It never admits or actuates that intent; downstream authority remains in
mfw/BRCE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from autofde_lab.fabric.canonical import sha256


class IssueRoute(str, Enum):
    """Candidate routing outcome; not an admission standing."""

    MATCHED = "MATCHED"
    REFUSED_EVIDENCE = "REFUSED_EVIDENCE"
    FALLBACK_NOVELTY = "FALLBACK_NOVELTY"


@dataclass(frozen=True)
class DiagnosticArchetype:
    id: str
    domain: str
    required: frozenset[str]
    contradictory: frozenset[str]
    hypotheses: tuple[str, ...]
    repair_intent: str
    compiled: bool = True


@dataclass(frozen=True)
class IssueReasoningResult:
    route: IssueRoute
    archetype: str
    domain: str
    matched_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    hypotheses_considered: tuple[str, ...]
    hypotheses_eliminated: int
    repair_intent: str | None
    evidence_identity_sha256: str
    candidate_identity_sha256: str
    actuation: str = "REFUSED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "archetype": self.archetype,
            "domain": self.domain,
            "matched_evidence": list(self.matched_evidence),
            "missing_evidence": list(self.missing_evidence),
            "contradictory_evidence": list(self.contradictory_evidence),
            "hypotheses_considered": list(self.hypotheses_considered),
            "hypotheses_eliminated": self.hypotheses_eliminated,
            "repair_intent": self.repair_intent,
            "evidence_identity_sha256": self.evidence_identity_sha256,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "actuation": self.actuation,
        }


ARCHETYPES: tuple[DiagnosticArchetype, ...] = (
    DiagnosticArchetype(
        "scheduling_capacity",
        "infrastructure",
        frozenset({"workload_pending"}),
        frozenset(),
        ("capacity_exhausted", "quota_exhausted", "affinity_blocked", "taint_blocked", "volume_unbound"),
        "construct a bounded scheduling/capacity repair candidate",
    ),
    DiagnosticArchetype(
        "probe_restart_loop",
        "distributed_system",
        frozenset({"restarting"}),
        frozenset({"workload_pending"}),
        ("liveness_mismatch", "readiness_mismatch", "startup_timeout", "dependency_unready"),
        "construct a probe/lifecycle repair candidate",
    ),
    DiagnosticArchetype(
        "service_routing",
        "networking",
        frozenset({"no_endpoints"}),
        frozenset({"dns_failure"}),
        ("selector_mismatch", "target_port_mismatch", "backend_unready", "endpoint_stale"),
        "construct a service-routing repair candidate",
    ),
    DiagnosticArchetype(
        "dns_resolution",
        "networking",
        frozenset({"dns_failure"}),
        frozenset({"no_endpoints"}),
        ("resolver_config", "dns_policy", "record_missing", "upstream_dns_unreachable"),
        "construct a DNS-path repair candidate",
    ),
    DiagnosticArchetype(
        "authorization_policy",
        "security",
        frozenset({"authorization_denied"}),
        frozenset(),
        ("missing_binding", "wrong_subject", "wrong_scope", "expired_credential", "policy_denial"),
        "construct a least-authority policy/credential repair candidate",
    ),
    DiagnosticArchetype(
        "resource_exhaustion",
        "capacity",
        frozenset({"resource_exhausted"}),
        frozenset({"storage_io_failure"}),
        ("memory_limit", "cpu_saturation", "fd_exhaustion", "connection_table_exhaustion", "ip_exhaustion"),
        "construct a bounded resource/capacity repair candidate",
    ),
    DiagnosticArchetype(
        "storage_attachment_io",
        "storage",
        frozenset({"storage_io_failure"}),
        frozenset({"dns_failure"}),
        ("volume_unbound", "access_mode_conflict", "affinity_mismatch", "read_failure", "data_corruption"),
        "construct a storage-path repair candidate",
    ),
    DiagnosticArchetype(
        "configuration_drift",
        "configuration",
        frozenset({"configuration_drift"}),
        frozenset(),
        ("missing_env", "wrong_port", "wrong_image", "missing_config", "version_skew"),
        "construct a desired-vs-observed configuration repair candidate",
    ),
    DiagnosticArchetype(
        "dependency_failure",
        "dependencies",
        frozenset({"dependency_unreachable"}),
        frozenset(),
        ("dependency_down", "address_drift", "protocol_mismatch", "tls_mismatch", "timeout_budget"),
        "construct a dependency-path repair candidate",
    ),
    DiagnosticArchetype(
        "data_schema_validation",
        "data",
        frozenset({"schema_validation_failure"}),
        frozenset(),
        ("column_mismatch", "type_mismatch", "missing_field", "constraint_violation", "serialization_drift"),
        "construct a schema/data compatibility repair candidate",
    ),
    DiagnosticArchetype(
        "software_version_compatibility",
        "software",
        frozenset({"version_incompatible"}),
        frozenset(),
        ("api_break", "binary_mismatch", "dependency_version", "feature_flag_mismatch"),
        "construct a version/compatibility repair candidate",
    ),
    DiagnosticArchetype(
        "queue_backpressure",
        "messaging",
        frozenset({"queue_lag"}),
        frozenset(),
        ("consumer_slow", "poison_message", "retry_amplification", "partition_imbalance", "producer_flood"),
        "construct a queue/backpressure repair candidate",
    ),
    DiagnosticArchetype(
        "build_toolchain",
        "developer_tooling",
        frozenset({"build_failure"}),
        frozenset(),
        ("compiler_mismatch", "dependency_missing", "generated_drift", "test_contract", "environment_drift"),
        "construct a build/toolchain repair candidate",
    ),
    DiagnosticArchetype(
        "policy_governance",
        "governance",
        frozenset({"policy_violation"}),
        frozenset(),
        ("required_control_missing", "forbidden_state", "scope_mismatch", "evidence_missing"),
        "construct a policy-conformance repair candidate",
    ),
    DiagnosticArchetype(
        "business_process_stuck",
        "process",
        frozenset({"process_stuck"}),
        frozenset(),
        ("missing_transition", "approval_wait", "dependency_wait", "dead_letter", "state_drift"),
        "construct a bounded process-unblocking candidate",
    ),
    DiagnosticArchetype(
        "novel_causal_topology",
        "unknown",
        frozenset({"novel_or_metastable"}),
        frozenset(),
        ("unknown_causal_graph",),
        "delegate causal discovery to cognition; compile only after validation",
        compiled=False,
    ),
)


class CompiledIssueReasoner:
    """Route structured issue evidence through finite deterministic archetypes."""

    def __init__(self, archetypes: Iterable[DiagnosticArchetype] = ARCHETYPES) -> None:
        self._archetypes = tuple(archetypes)

    @property
    def archetypes(self) -> tuple[DiagnosticArchetype, ...]:
        return self._archetypes

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "domain": item.domain,
                "required": sorted(item.required),
                "contradictory": sorted(item.contradictory),
                "hypothesis_count": len(item.hypotheses),
                "compiled": item.compiled,
            }
            for item in self._archetypes
        ]

    def reason(self, evidence: Mapping[str, Any] | Iterable[str]) -> IssueReasoningResult:
        normalized = self._normalize(evidence)
        evidence_identity = sha256({"evidence": sorted(normalized)})
        ranked = sorted(
            self._archetypes,
            key=lambda item: (
                len(item.required & normalized),
                -len(item.required - normalized),
                -len(item.contradictory & normalized),
            ),
            reverse=True,
        )
        archetype = ranked[0]
        missing = archetype.required - normalized
        contradictions = archetype.contradictory & normalized
        matched = archetype.required & normalized

        if not archetype.compiled and not missing:
            route = IssueRoute.FALLBACK_NOVELTY
            repair_intent = archetype.repair_intent
            eliminated = 0
        elif missing or contradictions:
            route = IssueRoute.REFUSED_EVIDENCE
            repair_intent = None
            eliminated = max(0, len(archetype.hypotheses) - len(missing) - len(contradictions) - 1)
        else:
            route = IssueRoute.MATCHED
            repair_intent = archetype.repair_intent
            eliminated = max(0, len(archetype.hypotheses) - 1)

        candidate = {
            "route": route.value,
            "archetype": archetype.id,
            "domain": archetype.domain,
            "evidence_identity_sha256": evidence_identity,
            "repair_intent": repair_intent,
            "actuation": "REFUSED",
        }
        return IssueReasoningResult(
            route=route,
            archetype=archetype.id,
            domain=archetype.domain,
            matched_evidence=tuple(sorted(matched)),
            missing_evidence=tuple(sorted(missing)),
            contradictory_evidence=tuple(sorted(contradictions)),
            hypotheses_considered=archetype.hypotheses,
            hypotheses_eliminated=eliminated,
            repair_intent=repair_intent,
            evidence_identity_sha256=evidence_identity,
            candidate_identity_sha256=sha256(candidate),
        )

    @staticmethod
    def _normalize(evidence: Mapping[str, Any] | Iterable[str]) -> frozenset[str]:
        if isinstance(evidence, Mapping):
            return frozenset(str(key) for key, value in evidence.items() if bool(value))
        return frozenset(str(value) for value in evidence)
