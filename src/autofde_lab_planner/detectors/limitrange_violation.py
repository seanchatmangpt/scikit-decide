"""Detector for LimitRange Violation faults.

Ground truth: a namespace-scoped `LimitRange` object (`kubectl get
limitrange -o json`) carries, per `type: Container` item, `min`/`max` bounds
and an optional `default`/`defaultRequest` per resource name. A container
whose own `resources.requests`/`resources.limits` fall outside those
`min`/`max` bounds is admission-rejected by the API server; a container that
omits requests/limits entirely when the LimitRange has no `default` for that
resource is likewise represented here as `missing_default`, since the pod
then silently inherits no bound at all (a distinct silent-drift risk from an
explicit out-of-range value). This is a namespace-policy-object fault,
independent of `resource_request_too_large` (`WorkloadMisconfigFault`, which
flags a single deployment's own resources being outsized against no
namespace policy) and of `resourcequota_exhaustion` (namespace-wide
aggregate ceiling vs. this file's per-container min/max bound). sregym's
closest related mechanism is V.8 `inject_resource_request`
(`vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py:323`), which
mutates a deployment's resources directly and has no LimitRange-object
awareness at all -- this detector covers the genuinely distinct
policy-conformance mechanism that file does not.
"""

from __future__ import annotations

from typing import Any

from autofde_lab_planner.models import LimitRangeViolationFault

_RESOURCE_KEYS = ("cpu", "memory")


def detect_limitrange_violations(
    limitranges_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[LimitRangeViolationFault]:
    """Detects containers whose resources.requests/limits fall outside a namespace LimitRange."""
    lr_items = _to_item_list(limitranges_json)
    dep_items = _to_item_list(deployments_json)

    faults: list[LimitRangeViolationFault] = []

    for lr in lr_items:
        lr_meta = lr.get("metadata") or {}
        lr_name = lr_meta.get("name", "")
        lr_ns = lr_meta.get("namespace") or namespace

        limits_spec = (lr.get("spec") or {}).get("limits") or []
        container_limit = next(
            (item for item in limits_spec if isinstance(item, dict) and item.get("type") == "Container"),
            None,
        )
        if not container_limit:
            continue

        bounds_min = container_limit.get("min") or {}
        bounds_max = container_limit.get("max") or {}
        defaults = container_limit.get("default") or {}
        default_requests = container_limit.get("defaultRequest") or {}

        for dep in dep_items:
            dep_meta = dep.get("metadata") or {}
            dep_name = dep_meta.get("name", "")
            dep_ns = dep_meta.get("namespace") or namespace
            if dep_ns != lr_ns:
                continue

            containers = (
                ((dep.get("spec") or {}).get("template") or {}).get("spec") or {}
            ).get("containers") or []

            for container in containers:
                if not isinstance(container, dict):
                    continue
                c_name = container.get("name", "")
                resources = container.get("resources") or {}
                requests = resources.get("requests") or {}
                limits = resources.get("limits") or {}

                for resource_name in _RESOURCE_KEYS:
                    min_bound = bounds_min.get(resource_name)
                    max_bound = bounds_max.get(resource_name)

                    observed = requests.get(resource_name) or limits.get(resource_name)

                    if observed is None:
                        has_default = resource_name in defaults or resource_name in default_requests
                        if not has_default and (min_bound is not None or max_bound is not None):
                            faults.append(
                                LimitRangeViolationFault(
                                    limitrange_name=lr_name,
                                    namespace=lr_ns,
                                    deployment_name=dep_name,
                                    container_name=c_name,
                                    resource_name=resource_name,
                                    fault_kind="missing_default",
                                    observed_value=None,
                                    bound_value=None,
                                )
                            )
                        continue

                    observed_num = _parse_quantity(observed)
                    if observed_num is None:
                        continue

                    if min_bound is not None:
                        min_num = _parse_quantity(min_bound)
                        if min_num is not None and observed_num < min_num:
                            faults.append(
                                LimitRangeViolationFault(
                                    limitrange_name=lr_name,
                                    namespace=lr_ns,
                                    deployment_name=dep_name,
                                    container_name=c_name,
                                    resource_name=resource_name,
                                    fault_kind="below_min",
                                    observed_value=str(observed),
                                    bound_value=str(min_bound),
                                )
                            )

                    if max_bound is not None:
                        max_num = _parse_quantity(max_bound)
                        if max_num is not None and observed_num > max_num:
                            faults.append(
                                LimitRangeViolationFault(
                                    limitrange_name=lr_name,
                                    namespace=lr_ns,
                                    deployment_name=dep_name,
                                    container_name=c_name,
                                    resource_name=resource_name,
                                    fault_kind="above_max",
                                    observed_value=str(observed),
                                    bound_value=str(max_bound),
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
