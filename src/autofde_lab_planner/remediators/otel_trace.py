"""Category-B6 Remediator: OTel Trace Diffing Root Cause Rollback."""

from __future__ import annotations

from autofde_lab_planner.models import TraceAnomalyResult


def decide_otel_remediation_commands(
    result: TraceAnomalyResult,
    namespace: str,
) -> tuple[list[str], list[str]]:
    """Generates remediation rollout commands for OTel trace root cause isolation."""
    if not result.has_anomaly or not result.root_cause_service:
        return [], []

    svc = result.root_cause_service
    # Rollback deployment to prior revision, or rollout restart
    commands = [
        f"kubectl rollout undo deployment/{svc} -n {namespace}",
    ]
    return commands, [svc]
