"""Detector for ResourceQuota Exhaustion faults.

Ground truth: a namespace-scoped `ResourceQuota` object (`kubectl get
resourcequota -o json`) carries `status.hard` (the configured ceiling) and
`status.used` (current consumption) per resource name (e.g. `pods`,
`requests.cpu`, `requests.memory`, `limits.cpu`, `count/deployments.apps`).
When `used` approaches or reaches `hard`, subsequent pod/deployment scale-up
requests are admission-rejected by the API server with a `FailedCreate`
event whose message contains `exceeded quota`, even though the Deployment
spec itself is well-formed -- distinct from `resource_request_too_large`
(`WorkloadMisconfigFault`), which flags a single container's own
requests/limits being oversized, and from `scheduling_deadlock`, which flags
node-level placement constraints. This is a namespace-policy-object fault:
sregym's closest related mechanism is V.8 `inject_resource_request`
(`vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py:323`), which
mutates a single deployment's own resource requests rather than a
namespace-wide ResourceQuota ceiling -- this detector covers the genuinely
distinct namespace-quota-exhaustion mechanism that file does not.
"""

from __future__ import annotations

from typing import Any

from autofde_lab_planner.models import ResourceQuotaExhaustionFault

_EXHAUSTION_RATIO_THRESHOLD = 0.9


def detect_resourcequota_exhaustion(
    resourcequotas_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    events_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
    ratio_threshold: float = _EXHAUSTION_RATIO_THRESHOLD,
) -> list[ResourceQuotaExhaustionFault]:
    """Detects ResourceQuota objects near or at exhaustion (used/hard >= threshold)."""
    quota_items = _to_item_list(resourcequotas_json)
    event_items = _to_item_list(events_json)

    # Map quota_name -> deployment name blocked by "exceeded quota" FailedCreate events.
    blocked_by_quota: dict[str, str] = {}
    for ev in event_items:
        reason = ev.get("reason", "")
        msg = ev.get("message") or ""
        if reason == "FailedCreate" and "exceeded quota" in msg:
            involved = (ev.get("involvedObject") or {}).get("name", "")
            for quota in quota_items:
                q_name = (quota.get("metadata") or {}).get("name", "")
                if q_name and q_name in msg:
                    blocked_by_quota[q_name] = involved

    faults: list[ResourceQuotaExhaustionFault] = []

    for quota in quota_items:
        meta = quota.get("metadata") or {}
        q_name = meta.get("name", "")
        q_ns = meta.get("namespace") or namespace

        status = quota.get("status") or {}
        hard = status.get("hard") or {}
        used = status.get("used") or {}

        for resource_name, hard_val in hard.items():
            used_val = used.get(resource_name)
            if used_val is None:
                continue

            hard_num = _parse_quantity(hard_val)
            used_num = _parse_quantity(used_val)
            if hard_num is None or used_num is None or hard_num <= 0:
                continue

            ratio = used_num / hard_num
            if ratio >= ratio_threshold:
                fault_kind = "exceeded" if ratio >= 1.0 else "near_exhaustion"
                faults.append(
                    ResourceQuotaExhaustionFault(
                        quota_name=q_name,
                        namespace=q_ns,
                        resource_name=resource_name,
                        used=str(used_val),
                        hard=str(hard_val),
                        used_ratio=round(ratio, 4),
                        blocked_deployment=blocked_by_quota.get(q_name),
                        fault_kind=fault_kind,
                    )
                )

    return faults


def _parse_quantity(value: Any) -> float | None:
    """Parses a Kubernetes resource quantity string (e.g. '500m', '2Gi', '10') into a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None

    suffixes = {
        "m": 1e-3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
        "P": 1e15,
        "E": 1e18,
        "Ki": 2**10,
        "Mi": 2**20,
        "Gi": 2**30,
        "Ti": 2**40,
        "Pi": 2**50,
        "Ei": 2**60,
    }
    for suffix in sorted(suffixes, key=len, reverse=True):
        if text.endswith(suffix):
            numeric = text[: -len(suffix)]
            try:
                return float(numeric) * suffixes[suffix]
            except ValueError:
                return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_item_list(data: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    if isinstance(data, dict):
        raw_items = data.get("items")
        if isinstance(raw_items, list):
            items = raw_items
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return []
    return [i for i in items if isinstance(i, dict)]
