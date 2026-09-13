"""Category-B9 Detector: flagd Config Drift."""

from __future__ import annotations

import json
from typing import Any

from autofde_lab_planner.models import FlagdDriftResult, FlagDriftItem

FLAG_TO_DEPLOYMENTS: dict[str, tuple[str, ...]] = {
    "adFailure": ("ad",),
    "adHighCpu": ("ad",),
    "adManualGc": ("ad",),
    "cartFailure": ("cart",),
    "paymentFailure": ("payment",),
    "paymentUnreachable": ("checkout",),
    "productCatalogFailure": ("product-catalog",),
    "kafkaQueueProblems": ("kafka",),
    "imageSlowLoad": ("frontend",),
    "loadGeneratorFloodHomepage": ("load-generator",),
    "failedReadinessProbe": ("cart",),
    "recommendationCacheFailure": ("recommendation",),
    "emailMemoryLeak": ("email",),
    "llmInaccurateResponse": ("llm",),
    "llmRateLimitError": ("llm",),
}


def detect_flagd_config_drift(
    configmap_json_input: str | dict[str, Any],
    namespace: str = "astronomy-shop",
    configmap_name: str = "flagd-config",
) -> FlagdDriftResult:
    """Parses flagd-config ConfigMap and detects feature flag defaultVariant drift away from 'off'."""
    cm_dict: dict[str, Any] = {}
    if isinstance(configmap_json_input, str):
        raw_str = configmap_json_input.strip()
        if not raw_str:
            return FlagdDriftResult(has_drift=False, configmap_name=configmap_name, namespace=namespace)
        try:
            cm_dict = json.loads(raw_str)
        except json.JSONDecodeError:
            return FlagdDriftResult(has_drift=False, configmap_name=configmap_name, namespace=namespace)
    elif isinstance(configmap_json_input, dict):
        cm_dict = configmap_json_input

    data = cm_dict.get("data", {})
    if not isinstance(data, dict):
        return FlagdDriftResult(has_drift=False, configmap_name=configmap_name, namespace=namespace)

    flagd_json_str = data.get("demo.flagd.json") or data.get("flags.json") or data.get("config.json")
    if not flagd_json_str:
        return FlagdDriftResult(has_drift=False, configmap_name=configmap_name, namespace=namespace)

    try:
        flagd_dict = json.loads(flagd_json_str)
    except json.JSONDecodeError:
        return FlagdDriftResult(has_drift=False, configmap_name=configmap_name, namespace=namespace)

    flags = flagd_dict.get("flags", {})
    if not isinstance(flags, dict):
        return FlagdDriftResult(has_drift=False, configmap_name=configmap_name, namespace=namespace)

    drifted_items: list[FlagDriftItem] = []
    repaired_flagd_dict = json.loads(json.dumps(flagd_dict))  # deep copy

    for flag_name, flag_data in flags.items():
        if not isinstance(flag_data, dict):
            continue
        curr_variant = str(flag_data.get("defaultVariant", "off"))
        if curr_variant != "off":
            target_deps = FLAG_TO_DEPLOYMENTS.get(flag_name, (flag_name,))
            drifted_items.append(
                FlagDriftItem(
                    flag_name=flag_name,
                    current_variant=curr_variant,
                    canonical_variant="off",
                    target_deployments=target_deps,
                )
            )
            repaired_flagd_dict["flags"][flag_name]["defaultVariant"] = "off"

    if not drifted_items:
        return FlagdDriftResult(has_drift=False, configmap_name=configmap_name, namespace=namespace)

    repaired_json_str = json.dumps(repaired_flagd_dict, indent=2)
    return FlagdDriftResult(
        has_drift=True,
        configmap_name=configmap_name,
        namespace=namespace,
        drifted_flags=tuple(drifted_items),
        repaired_flagd_json=repaired_json_str,
    )
