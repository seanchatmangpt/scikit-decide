"""Evidence-bounded 80/20 ERRC closure court for the AutoFDE Lab Crown.

Static source paths establish eligibility, not standing. A requirement is only
promoted by this projection when an exact-subject execution receipt names it,
exits successfully, and covers the expected evidence paths. External/runtime
blockers remain blocked and cannot be self-promoted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable

from .crown import CrownReport, RequirementStatus, crown_report


class ErrcAction(str, Enum):
    ELIMINATE = "ELIMINATE"
    REDUCE = "REDUCE"
    RAISE = "RAISE"
    CREATE = "CREATE"


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    """Observed validation bound to one exact source subject."""

    subject_sha: str
    command: str
    exit_code: int
    requirement_ids: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    replay_key: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", self.subject_sha):
            raise ValueError("subject_sha must be a full 40-character Git SHA")
        if not self.command.strip():
            raise ValueError("command must be non-empty")
        if not self.replay_key.strip():
            raise ValueError("replay_key must be non-empty")
        if not self.requirement_ids:
            raise ValueError("requirement_ids must be non-empty")
        if not self.evidence_paths:
            raise ValueError("evidence_paths must be non-empty")

    @property
    def successful(self) -> bool:
        return self.exit_code == 0


ELIGIBLE_EVIDENCE: dict[str, tuple[str, ...]] = {
    "R-002": ("src/autofde_lab/fabric/selection.py", "tests/fabric/test_selection.py"),
    "R-004": (
        "src/autofde_lab/fabric/differential_verification.py",
        "tests/fabric/test_differential_verification.py",
    ),
    "R-005": (
        "src/autofde_lab/fabric/guardrails.py",
        "tests/fabric/test_guardrails.py",
    ),
    "R-007": ("src/autofde_lab/fabric/crown.py", "tests/fabric/test_crown.py"),
    "R-100": (
        "src/autofde_lab/fabric/public_ontology.py",
        "tests/fabric/test_public_ontology.py",
    ),
    "R-101": (
        "src/autofde_lab/fabric/public_ontology.py",
        "tests/fabric/test_public_ontology.py",
    ),
    "R-102": (
        "src/autofde_lab/fabric/public_ontology.py",
        "tests/fabric/test_public_ontology.py",
    ),
    "R-104": (
        "src/autofde_lab/fabric/public_ontology.py",
        "tests/fabric/test_public_ontology.py",
    ),
    "R-200": (
        "src/autofde_lab/fabric/coverage_bridge.py",
        "tests/fabric/test_coverage_bridge.py",
    ),
    "R-201": ("src/autofde_lab/fabric/selection.py", "tests/fabric/test_selection.py"),
    "R-202": ("src/autofde_lab/fabric/selection.py", "tests/fabric/test_selection.py"),
    "R-300": (
        "src/autofde_lab/fabric/selection_store.py",
        "tests/fabric/test_selection_store.py",
    ),
    "R-301": ("src/autofde_lab/fabric/selection.py", "tests/fabric/test_selection.py"),
    "R-302": (
        "src/autofde_lab/fabric/query_plane.py",
        "tests/fabric/test_query_plane.py",
    ),
    "R-303": (
        "src/autofde_lab/fabric/selection_store.py",
        "tests/fabric/test_selection_store.py",
    ),
    "R-304": ("src/autofde_lab/fabric/selection.py", "tests/fabric/test_selection.py"),
    "R-400": ("src/autofde_lab/fabric/hot_path.py", "tests/fabric/test_hot_path.py"),
    "R-401": ("src/autofde_lab/fabric/selection.py", "tests/fabric/test_selection.py"),
    "R-402": ("src/autofde_lab/fabric/self_play.py", "tests/fabric/test_self_play.py"),
    "R-500": ("src/autofde_lab/fabric/hot_path.py", "tests/fabric/test_hot_path.py"),
    "R-501": (
        "src/autofde_lab/fabric/cognition_debt.py",
        "tests/fabric/test_cognition_debt.py",
    ),
    "R-503": ("src/autofde_lab/fabric/hot_path.py", "tests/fabric/test_hot_path.py"),
    "R-602": ("src/autofde_lab/fabric/handoff.py", "tests/fabric/test_handoff.py"),
    "R-603": (
        "src/autofde_lab/fabric/guardrails.py",
        "tests/fabric/test_guardrails.py",
    ),
    "R-1000": (
        "src/autofde_lab/fabric/competitive_benchmark.py",
        "tests/fabric/test_competitive_benchmark.py",
    ),
    "R-1003": (
        "src/autofde_lab/fabric/differential_verification.py",
        "tests/fabric/test_differential_verification.py",
    ),
    "R-1103": ("src/autofde_lab/fabric/metrics.py", "tests/fabric/test_metrics.py"),
    "R-1200": ("src/autofde_lab/fabric/metrics.py", "tests/fabric/test_metrics.py"),
    "R-1201": (
        "src/autofde_lab/fabric/causal_placement.py",
        "tests/fabric/test_causal_placement.py",
    ),
    "R-1202": (
        "src/autofde_lab/fabric/causal_placement.py",
        "tests/fabric/test_causal_placement.py",
    ),
    "R-1300": (
        "src/autofde_lab/fabric/query_plane.py",
        "tests/fabric/test_query_plane.py",
    ),
    "R-1302": (
        "src/autofde_lab/fabric/query_plane.py",
        "tests/fabric/test_query_plane.py",
    ),
    "R-1400": ("src/autofde_lab/fabric/self_play.py", "tests/fabric/test_self_play.py"),
    "R-1401": (
        "src/autofde_lab/fabric/coverage_bridge.py",
        "tests/fabric/test_coverage_bridge.py",
    ),
    "R-1402": (
        "src/autofde_lab/fabric/differential_verification.py",
        "tests/fabric/test_differential_verification.py",
    ),
    "R-1403": (
        "src/autofde_lab/fabric/guardrails.py",
        "tests/fabric/test_guardrails.py",
    ),
    "R-1502": ("src/autofde_lab/fabric/metrics.py", "tests/fabric/test_metrics.py"),
}


GATE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "P1": ("R-100", "R-101", "R-102", "R-104"),
    "D1": ("R-200", "R-201", "R-202", "R-304", "R-1401"),
    "D2": ("R-300", "R-301", "R-302", "R-303", "R-400", "R-401"),
    "D3": ("R-004", "R-1003", "R-1402"),
    "D4": ("R-100", "R-104"),
    "D6": ("R-1200", "R-1201", "R-1202"),
    "D8": ("R-400", "R-402", "R-500", "R-503"),
}


ERRC: dict[str, ErrcAction] = {
    "repeated_frontier_reasoning_on_hot_signatures": ErrcAction.ELIMINATE,
    "duplicate_candidate_selection_work": ErrcAction.ELIMINATE,
    "full_graph_runtime_traversal": ErrcAction.REDUCE,
    "model_tokens_on_warm_paths": ErrcAction.REDUCE,
    "independent_postcondition_verification": ErrcAction.RAISE,
    "content_bound_candidate_replay": ErrcAction.RAISE,
    "adversarial_self_play_and_differential_oracles": ErrcAction.RAISE,
    "indexed_hot_path_and_cognition_compilation": ErrcAction.CREATE,
    "execution_receipt_derived_gate_court": ErrcAction.CREATE,
}


def _admitted_requirement_ids(receipts: Iterable[ExecutionReceipt]) -> set[str]:
    admitted: set[str] = set()
    for receipt in receipts:
        if not receipt.successful:
            continue
        observed_paths = set(receipt.evidence_paths)
        for requirement_id in receipt.requirement_ids:
            expected_paths = ELIGIBLE_EVIDENCE.get(requirement_id)
            if expected_paths and set(expected_paths) <= observed_paths:
                admitted.add(requirement_id)
    return admitted


def errc_crown_report(
    base: CrownReport | None = None,
    *,
    receipts: Iterable[ExecutionReceipt] = (),
) -> CrownReport:
    """Project Crown standing from explicit exact-subject execution receipts."""
    source = base or crown_report()
    admitted_ids = _admitted_requirement_ids(receipts)
    upgraded = []
    for requirement in source.requirements:
        if (
            requirement.requirement_id in admitted_ids
            and requirement.external_dependency is None
        ):
            upgraded.append(
                replace(
                    requirement,
                    status=RequirementStatus.SATISFIED,
                    evidence=ELIGIBLE_EVIDENCE[requirement.requirement_id],
                )
            )
        else:
            upgraded.append(requirement)

    by_id = {requirement.requirement_id: requirement for requirement in upgraded}
    for gate, dependencies in GATE_REQUIREMENTS.items():
        if gate not in by_id or any(
            dependency not in by_id for dependency in dependencies
        ):
            continue
        if not admitted_ids.intersection(dependencies):
            continue
        gate_requirement = by_id[gate]
        if gate_requirement.external_dependency is not None:
            continue
        if all(
            by_id[dependency].status is RequirementStatus.SATISFIED
            for dependency in dependencies
        ):
            evidence = tuple(
                dict.fromkeys(
                    path
                    for dependency in dependencies
                    for path in by_id[dependency].evidence
                )
            )
            by_id[gate] = replace(
                gate_requirement,
                status=RequirementStatus.SATISFIED,
                evidence=evidence,
            )

    report = CrownReport(tuple(by_id[r.requirement_id] for r in source.requirements))
    problems = report.validate()
    if problems:
        raise ValueError("invalid ERRC Crown projection: " + "; ".join(problems))
    return report


def closure_delta(
    base: CrownReport | None = None,
    *,
    receipts: Iterable[ExecutionReceipt] = (),
) -> dict[str, int]:
    """Return before/after counts without manufacturing execution evidence."""
    source = base or crown_report()
    projected = errc_crown_report(source, receipts=receipts)
    return {
        "before_satisfied": len(source.by_status(RequirementStatus.SATISFIED)),
        "after_satisfied": len(projected.by_status(RequirementStatus.SATISFIED)),
        "blocked_preserved": len(projected.by_status(RequirementStatus.BLOCKED)),
        "remaining_partial": len(projected.by_status(RequirementStatus.PARTIAL)),
    }
