"""One real diff implementation per relation-class, shared across every kind.

Each function here is called by many `ObjectKindAnalyzer`s in registry.py but
implemented exactly once. This is the shared logic the per-kind analyzers
compose instead of reimplementing.
"""

from __future__ import annotations

from autofde_lab_planner.scanner.models import Anomaly


def compare_declared_vs_observed(
    *,
    kind: str,
    object_name: str,
    namespace: str,
    field: str,
    declared: str | int | float | bool | None,
    observed: str | int | float | bool | None,
    detail: str = "",
) -> Anomaly | None:
    """Relation-class 1: declared spec field vs. observed/status value.

    Returns None (no anomaly) when declared == observed. `declared` may be a
    baseline/canonical value rather than a literal spec field -- the caller
    decides what "declared" means for its kind (e.g. dnsPolicy default).
    """
    if declared == observed:
        return None
    return Anomaly(
        kind=kind,
        object_name=object_name,
        namespace=namespace,
        relation_class="declared_vs_observed",
        field=field,
        observed=str(observed),
        expected=str(declared) if declared is not None else None,
        detail=detail or f"{field} declared={declared!r} observed={observed!r}",
    )


def find_dangling_reference(
    *,
    kind: str,
    object_name: str,
    namespace: str,
    field: str,
    referenced_name: str,
    available_names: set[str],
    detail: str = "",
) -> Anomaly | None:
    """Relation-class 2: a reference to an object that does not exist.

    `available_names` is the real set of names/keys observed for the
    referenced kind (e.g. real PVC names, real ConfigMap keys, real Pod
    labels-matched names).
    """
    if referenced_name in available_names:
        return None
    return Anomaly(
        kind=kind,
        object_name=object_name,
        namespace=namespace,
        relation_class="dangling_reference",
        field=field,
        observed=referenced_name,
        expected=None,
        detail=detail or f"{field} references {referenced_name!r}, not found among {sorted(available_names)}",
    )


def find_insufficient_capability(
    *,
    kind: str,
    object_name: str,
    namespace: str,
    field: str,
    required: set[str],
    granted: set[str],
    detail: str = "",
) -> Anomaly | None:
    """Relation-class 3: a reference exists but lacks required capability.

    `required` is the real set of verb/resource strings the workload needs;
    `granted` is the real set the bound role actually confers. Returns an
    Anomaly listing exactly the missing subset, or None if fully covered.
    """
    missing = required - granted
    if not missing:
        return None
    return Anomaly(
        kind=kind,
        object_name=object_name,
        namespace=namespace,
        relation_class="insufficient_capability",
        field=field,
        observed=",".join(sorted(granted)) or "<none>",
        expected=",".join(sorted(required)),
        detail=detail or f"missing capabilities: {sorted(missing)}",
    )


def find_aggregate_threshold_violation(
    *,
    kind: str,
    object_name: str,
    namespace: str,
    field: str,
    total_observed: float,
    limit: float,
    unit: str = "",
    detail: str = "",
) -> Anomaly | None:
    """Relation-class 4: an aggregate across many objects exceeds a threshold.

    `total_observed` is the real summed usage/count across the namespace's
    objects (computed by the caller from real per-object data); `limit` is
    the real declared quota/limit value.
    """
    if total_observed <= limit:
        return None
    return Anomaly(
        kind=kind,
        object_name=object_name,
        namespace=namespace,
        relation_class="aggregate_threshold",
        field=field,
        observed=f"{total_observed}{unit}",
        expected=f"<= {limit}{unit}",
        detail=detail or f"{field} total {total_observed}{unit} exceeds limit {limit}{unit}",
    )
