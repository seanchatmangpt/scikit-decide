"""Detector for CronJob / Scheduled Mutations (e.g. vpa-updater squeezing deployment limits)."""

from __future__ import annotations

import json
from typing import Any
from autofde_lab_planner.models import CronJobMutationFault


def detect_cronjob_mutations(
    cronjobs_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    configmaps_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[CronJobMutationFault]:
    """Detects recurring mutator CronJobs (such as vpa-updater) targeting victim deployments."""
    cj_items = _to_item_list(cronjobs_json)
    dep_items = _to_item_list(deployments_json)
    cm_items = _to_item_list(configmaps_json)

    faults: list[CronJobMutationFault] = []

    # Map configmap data by name
    cm_data_by_name: dict[str, dict[str, str]] = {
        (cm.get("metadata") or {}).get("name", ""): cm.get("data") or {}
        for cm in cm_items
        if (cm.get("metadata") or {}).get("name")
    }

    # Find victim deployment with squeezed memory limits (e.g. <= 16Mi)
    squeezed_victims: dict[str, tuple[str, str, int]] = {}  # dep_name -> (mem_limit, container_name, container_index)
    for dep in dep_items:
        d_name = (dep.get("metadata") or {}).get("name", "")
        containers = (((dep.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
        for c_idx, c in enumerate(containers):
            if not isinstance(c, dict):
                continue
            c_name = c.get("name", "")
            limits = (c.get("resources") or {}).get("limits") or {}
            mem_limit = limits.get("memory", "")
            if mem_limit and (_parse_memory_to_mb(mem_limit) <= 16 or mem_limit == "4Mi"):
                squeezed_victims[d_name] = (mem_limit, c_name, c_idx)

    for cj in cj_items:
        cj_meta = cj.get("metadata") or {}
        cj_name = cj_meta.get("name", "")
        cj_ns = cj_meta.get("namespace") or namespace

        is_mutator = False
        target_dep = ""
        injected_limit = "4Mi"

        # Check name
        if cj_name == "vpa-updater" or "mutat" in cj_name or "updater" in cj_name:
            is_mutator = True

        # Check containers / command / envFrom
        pod_spec = (
            ((((cj.get("spec") or {})
              .get("jobTemplate") or {})
              .get("spec") or {})
              .get("template") or {})
              .get("spec") or {}
        )
        containers = pod_spec.get("containers") or []

        for c in containers:
            if not isinstance(c, dict):
                continue
            cmd_str = " ".join((c.get("command") or []) + (c.get("args") or []))
            if "patch" in cmd_str and "deployment" in cmd_str:
                is_mutator = True

            # Check envFrom configmap refs
            env_from = c.get("envFrom") or []
            for ef in env_from:
                if not isinstance(ef, dict):
                    continue
                cm_ref = (ef.get("configMapRef") or {}).get("name", "")
                if cm_ref in cm_data_by_name:
                    data = cm_data_by_name[cm_ref]
                    if "TARGET" in data:
                        target_dep = data["TARGET"]
                    if "PATCH" in data and "memory" in data["PATCH"]:
                        is_mutator = True
                        if "4Mi" in data["PATCH"]:
                            injected_limit = "4Mi"

        if is_mutator:
            # If target_dep wasn't explicitly found in policy configmap, match against squeezed victim
            if not target_dep and squeezed_victims:
                target_dep = next(iter(squeezed_victims.keys()))
            elif not target_dep:
                target_dep = "recommendation"

            vic_info = squeezed_victims.get(target_dep)
            vic_limit = vic_info[0] if vic_info else injected_limit
            vic_cname = vic_info[1] if vic_info else None
            vic_cidx = vic_info[2] if vic_info else 0

            faults.append(
                CronJobMutationFault(
                    cronjob_name=cj_name,
                    cronjob_namespace=cj_ns,
                    victim_deployment=target_dep,
                    victim_namespace=namespace,
                    injected_memory_limit=vic_limit,
                    container_name=vic_cname,
                    container_index=vic_cidx,
                )
            )

    return faults


def _parse_memory_to_mb(mem_str: str) -> float:
    """Parses k8s memory strings like '4Mi', '16Mi', '512Mi', '1Gi' to float MB."""
    s = mem_str.strip()
    if s.endswith("Mi"):
        try:
            return float(s[:-2])
        except ValueError:
            return 0.0
    elif s.endswith("Gi"):
        try:
            return float(s[:-2]) * 1024.0
        except ValueError:
            return 0.0
    elif s.endswith("Ki"):
        try:
            return float(s[:-2]) / 1024.0
        except ValueError:
            return 0.0
    try:
        return float(s) / (1024.0 * 1024.0)
    except ValueError:
        return 0.0


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

