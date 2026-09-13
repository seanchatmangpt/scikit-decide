"""Detector for CoreDNS & Service Discovery Faults (e.g. NXDOMAIN template rewrite in Corefile)."""

from __future__ import annotations

import re
from typing import Any
from autofde_lab_planner.models import CoreDNSFault

# Pattern matching the injected NXDOMAIN template block in Corefile
NXDOMAIN_TEMPLATE_PATTERN = re.compile(
    r"\s*template\s+ANY\s+ANY\s+svc\.cluster\.local\s*\{[^}]*rcode\s+NXDOMAIN[^}]*\}\s*",
    re.MULTILINE | re.DOTALL,
)


def detect_coredns_faults(
    configmaps_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "kube-system",
) -> list[CoreDNSFault]:
    """Detects Corefile corruption and NXDOMAIN rewrite rules in CoreDNS ConfigMap."""
    cm_items = _to_item_list(configmaps_json)
    faults: list[CoreDNSFault] = []

    for cm in cm_items:
        cm_meta = cm.get("metadata") or {}
        cm_name = cm_meta.get("name", "")
        cm_ns = cm_meta.get("namespace") or namespace

        cm_data = cm.get("data") or {}
        if cm_name != "coredns" and "Corefile" not in cm_data:
            continue

        corefile = cm_data.get("Corefile") or ""
        if not corefile:
            continue

        if "template ANY ANY svc.cluster.local" in corefile or "rcode NXDOMAIN" in corefile:
            # Strip out the injected template block
            repaired_corefile = NXDOMAIN_TEMPLATE_PATTERN.sub("\n", corefile)
            # If regex didn't catch it due to subtle formatting, do fallback string cleaning
            if "template ANY ANY svc.cluster.local" in repaired_corefile:
                lines = corefile.splitlines()
                cleaned_lines = []
                skipping = False
                for line in lines:
                    if "template ANY ANY svc.cluster.local" in line:
                        skipping = True
                        continue
                    if skipping:
                        if "}" in line:
                            skipping = False
                        continue
                    cleaned_lines.append(line)
                repaired_corefile = "\n".join(cleaned_lines)

            faults.append(
                CoreDNSFault(
                    configmap_name=cm_name,
                    namespace=cm_ns,
                    fault_kind="nxdomain_template",
                    repaired_corefile=repaired_corefile,
                )
            )

    return faults


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

