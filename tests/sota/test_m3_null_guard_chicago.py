"""Chicago-style zero-mock tests for M3 Null-Guards and Conditional Remediation.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch, NO monkeypatch.
Covering null metadata, null spec, null data, malformed payload items, and conditional patch generation.
"""

from __future__ import annotations

from autofde_lab_planner.detectors.coredns_fault import detect_coredns_faults
from autofde_lab_planner.detectors.cronjob_mutation import detect_cronjob_mutations
from autofde_lab_planner.detectors.ingress_targetport import detect_ingress_and_targetport_faults
from autofde_lab_planner.detectors.object_reconstruction import detect_missing_objects
from autofde_lab_planner.detectors.probe_heuristics import detect_probe_faults
from autofde_lab_planner.detectors.rolling_update_misconfig import detect_workload_and_rolling_update_misconfigs
from autofde_lab_planner.detectors.scheduling_deadlock import detect_scheduling_deadlocks
from autofde_lab_planner.models import WorkloadMisconfigFault
from autofde_lab_planner.remediators.rolling_update_misconfig import decide_workload_remediation_commands


def test_null_metadata_across_all_detectors():
    """Verify all detectors handle items with metadata: None without AttributeError."""
    dep_null_meta = {"items": [{"metadata": None, "spec": None}]}
    svc_null_meta = {"items": [{"metadata": None, "spec": None}]}
    ing_null_meta = {"items": [{"metadata": None, "spec": None}]}
    cm_null_meta = {"items": [{"metadata": None, "data": None}]}
    pod_null_meta = {"items": [{"metadata": None, "status": None}]}
    ev_null_meta = {"items": [{"metadata": None, "message": None, "involvedObject": None}]}

    res1 = detect_missing_objects(dep_null_meta, svc_null_meta, cm_null_meta, None, pod_null_meta)
    assert isinstance(res1, list)

    ing_res, tp_res = detect_ingress_and_targetport_faults(ing_null_meta, svc_null_meta, dep_null_meta)
    assert isinstance(ing_res, list) and isinstance(tp_res, list)

    res3 = detect_cronjob_mutations(cm_null_meta, dep_null_meta, cm_null_meta)
    assert isinstance(res3, list)

    res4 = detect_scheduling_deadlocks(dep_null_meta, pod_null_meta, ev_null_meta)
    assert isinstance(res4, list)

    res5 = detect_coredns_faults(cm_null_meta)
    assert isinstance(res5, list)

    res6 = detect_workload_and_rolling_update_misconfigs(dep_null_meta, pod_null_meta, ev_null_meta)
    assert isinstance(res6, list)

    res7 = detect_probe_faults(dep_null_meta, pod_null_meta, ev_null_meta)
    assert isinstance(res7, list)


def test_probe_heuristics_null_guards_and_crash_prevention():
    """Verify probe_heuristics detector handles null items, metadata, spec, pods, and pod metadata without crashing."""
    # Scenario 1: items list contains None
    res1 = detect_probe_faults({"items": [None]})
    assert isinstance(res1, list) and len(res1) == 0

    # Scenario 2: deployment metadata is None
    res2 = detect_probe_faults({"items": [{"metadata": None}]})
    assert isinstance(res2, list) and len(res2) == 0

    # Scenario 3: deployment spec is None
    res3 = detect_probe_faults({"items": [{"metadata": {"name": "test"}, "spec": None}]})
    assert isinstance(res3, list) and len(res3) == 0

    # Scenario 4: pods list contains None
    res4 = detect_probe_faults(
        deployments_json={"items": [{"metadata": {"name": "test"}, "spec": {}}]},
        pods_json={"items": [None]},
    )
    assert isinstance(res4, list) and len(res4) == 0

    # Scenario 5: pod metadata is None
    res5 = detect_probe_faults(
        deployments_json={"items": [{"metadata": {"name": "test"}, "spec": {}}]},
        pods_json={"items": [{"metadata": None}]},
    )
    assert isinstance(res5, list) and len(res5) == 0


def test_null_spec_data_status_subdicts():
    """Verify detectors handle null spec, null data, null status gracefully."""
    dep_null_subdicts = {
        "items": [
            {
                "metadata": {"name": "test-dep", "namespace": "default"},
                "spec": None,
                "status": None,
            }
        ]
    }
    cm_null_data = {
        "items": [
            {
                "metadata": {"name": "coredns", "namespace": "kube-system"},
                "data": None,
            }
        ]
    }

    res_recon = detect_missing_objects(dep_null_subdicts, namespace="default")
    assert isinstance(res_recon, list)

    res_dns = detect_coredns_faults(cm_null_data)
    assert isinstance(res_dns, list)

    res_wm = detect_workload_and_rolling_update_misconfigs(dep_null_subdicts)
    assert isinstance(res_wm, list)


def test_malformed_payload_items_primitives_and_nulls():
    """Verify _to_item_list filters out primitives, strings, numbers, and null list items."""
    malformed_items = [123, "not_a_dict", None, True, [], {"metadata": {"name": "valid-dep"}}]

    res_recon = detect_missing_objects(malformed_items, live_services_json=malformed_items)
    assert isinstance(res_recon, list)

    ing_res, tp_res = detect_ingress_and_targetport_faults(
        ingresses_json={"items": malformed_items},
        services_json={"items": malformed_items},
    )
    assert isinstance(ing_res, list) and isinstance(tp_res, list)

    res_cj = detect_cronjob_mutations(cronjobs_json=malformed_items)
    assert isinstance(res_cj, list)

    res_sd = detect_scheduling_deadlocks(deployments_json=malformed_items, events_json=malformed_items)
    assert isinstance(res_sd, list)


def test_conditional_init_container_patch_generation():
    """Verify rolling update remediator conditionally emits initContainers removal patch."""
    # Case A: Strategy misconfig WITHOUT hanging init container
    fault_no_init = WorkloadMisconfigFault(
        deployment_name="frontend",
        namespace="astronomy-shop",
        fault_kind="rolling_update_misconfigured",
        details="Rolling update strategy misconfiguration (maxUnavailable=100%, maxSurge=0%, hanging_init=False) on frontend",
    )
    cmds_no_init, _ = decide_workload_remediation_commands([fault_no_init], namespace="astronomy-shop")
    init_patches_no_init = [c for c in cmds_no_init if "initContainers" in c]
    strategy_patches_no_init = [c for c in cmds_no_init if "spec/strategy" in c]
    assert len(strategy_patches_no_init) == 1
    assert len(init_patches_no_init) == 0, "Do NOT issue initContainers removal patch when initContainers is absent"

    # Case B: Strategy misconfig WITH hanging init container
    fault_with_init = WorkloadMisconfigFault(
        deployment_name="frontend",
        namespace="astronomy-shop",
        fault_kind="rolling_update_misconfigured",
        details="Rolling update strategy misconfiguration (maxUnavailable=100%, maxSurge=0%, hanging_init=True) on frontend",
    )
    cmds_with_init, _ = decide_workload_remediation_commands([fault_with_init], namespace="astronomy-shop")
    init_patches_with_init = [c for c in cmds_with_init if "initContainers" in c]
    strategy_patches_with_init = [c for c in cmds_with_init if "spec/strategy" in c]
    assert len(strategy_patches_with_init) == 1
    assert len(init_patches_with_init) == 1, "Emit initContainers removal patch when hanging init container is detected"
