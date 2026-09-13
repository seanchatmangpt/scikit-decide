"""Chicago-style tests for the generalized structural-anomaly scanner.

Real fixture k8s JSON in, real scanner.registry.scan() call, real Anomaly
objects asserted on final state. No mocks (see
.claude/rules/testing-chicago-style.md) -- zero-mock is verified separately
by a real grep over tests/scanner/ for unittest.mock / Mock( / MagicMock /
patch( / monkeypatch.
"""

from __future__ import annotations

from autofde_lab_planner.scanner import diff_engine, taxonomy
from autofde_lab_planner.scanner.models import Anomaly
from autofde_lab_planner.scanner.registry import scan


# ---------------------------------------------------------------------------
# One real fixture + assertion per relation-class (task requirement 5, part 1)
# ---------------------------------------------------------------------------


def test_declared_vs_observed_relation_class_deployment_replica_mismatch():
    state = {
        "deployments": [
            {
                "metadata": {"name": "billing-api", "namespace": "prod"},
                "spec": {
                    "replicas": 3,
                    "selector": {"matchLabels": {"app": "billing-api"}},
                    "template": {"spec": {"containers": [{"image": "billing-api:1.2.3"}]}},
                },
            }
        ],
        "pods": [
            {
                "metadata": {"name": "billing-api-1", "namespace": "prod", "labels": {"app": "billing-api"}},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }
        ],
    }
    anomalies = scan(state)
    replica_anomalies = [a for a in anomalies if a.field == "readyReplicas"]
    assert len(replica_anomalies) == 1
    a = replica_anomalies[0]
    assert a.kind == "Deployment"
    assert a.object_name == "billing-api"
    assert a.namespace == "prod"
    assert a.relation_class == "declared_vs_observed"
    assert a.expected == "3"
    assert a.observed == "1"


def test_dangling_reference_relation_class_pvc_claim_mismatch():
    state = {
        "persistentvolumeclaims": [{"metadata": {"name": "billing-data-real"}}],
        "pods": [
            {
                "metadata": {"name": "billing-api-1", "namespace": "prod"},
                "spec": {
                    "volumes": [
                        {"name": "data", "persistentVolumeClaim": {"claimName": "billing-data-typo"}},
                    ]
                },
            }
        ],
    }
    anomalies = scan(state)
    pvc_anomalies = [a for a in anomalies if a.kind == "PersistentVolumeClaim"]
    assert len(pvc_anomalies) == 1
    a = pvc_anomalies[0]
    assert a.relation_class == "dangling_reference"
    assert a.observed == "billing-data-typo"
    assert a.expected is None
    assert a.object_name == "billing-api-1"


def test_insufficient_capability_relation_class_rbac_gap():
    state = {
        "clusterroles": [
            {
                "metadata": {"name": "reader"},
                "rules": [{"resources": ["pods"], "verbs": ["get", "list"]}],
            }
        ],
        "clusterrolebindings": [
            {
                "roleRef": {"name": "reader"},
                "subjects": [{"kind": "ServiceAccount", "name": "billing-sa", "namespace": "prod"}],
            }
        ],
        "pods": [
            {
                "metadata": {
                    "name": "billing-api-1",
                    "namespace": "prod",
                    "annotations": {"required-rbac": "get:pods,delete:pods"},
                },
                "spec": {"serviceAccountName": "billing-sa"},
            }
        ],
    }
    anomalies = scan(state)
    rbac_anomalies = [a for a in anomalies if a.relation_class == "insufficient_capability"]
    assert len(rbac_anomalies) == 1
    a = rbac_anomalies[0]
    assert a.kind == "ServiceAccount"
    assert a.object_name == "billing-sa"
    assert "delete:pods" in a.expected
    assert "delete:pods" not in a.observed


def test_aggregate_threshold_relation_class_resourcequota_exhaustion():
    state = {
        "resourcequotas": [
            {
                "metadata": {"name": "prod-quota", "namespace": "prod"},
                "spec": {"hard": {"pods": "2"}},
            }
        ],
        "pods": [
            {"metadata": {"name": "p1", "namespace": "prod"}},
            {"metadata": {"name": "p2", "namespace": "prod"}},
            {"metadata": {"name": "p3", "namespace": "prod"}},
        ],
    }
    anomalies = scan(state)
    quota_anomalies = [a for a in anomalies if a.relation_class == "aggregate_threshold"]
    assert len(quota_anomalies) == 1
    a = quota_anomalies[0]
    assert a.kind == "ResourceQuota"
    assert a.observed == "3.0 pods"
    assert a.expected == "<= 2.0 pods"


# ---------------------------------------------------------------------------
# Uniformity-by-construction: every Anomaly is the exact same dataclass type,
# regardless of relation_class or kind (task requirement 1 verification).
# ---------------------------------------------------------------------------


def test_all_anomalies_share_one_uniform_dataclass_type():
    state = {
        "deployments": [
            {
                "metadata": {"name": "d1", "namespace": "ns"},
                "spec": {"replicas": 5, "selector": {"matchLabels": {"app": "d1"}}, "template": {"spec": {"containers": [{}]}}},
            }
        ],
        "persistentvolumeclaims": [],
        "pods": [
            {
                "metadata": {"name": "pd1", "namespace": "ns"},
                "spec": {"volumes": [{"persistentVolumeClaim": {"claimName": "missing-pvc"}}]},
            }
        ],
        "resourcequotas": [{"metadata": {"name": "q", "namespace": "ns"}, "spec": {"hard": {"pods": "0"}}}],
        "clusterroles": [{"metadata": {"name": "r"}, "rules": []}],
        "clusterrolebindings": [
            {"roleRef": {"name": "r"}, "subjects": [{"kind": "ServiceAccount", "name": "sa", "namespace": "ns"}]}
        ],
    }
    state["pods"].append(
        {
            "metadata": {"name": "pd2", "namespace": "ns", "annotations": {"required-rbac": "get:secrets"}},
            "spec": {"serviceAccountName": "sa"},
        }
    )
    anomalies = scan(state)
    relation_classes_seen = {a.relation_class for a in anomalies}
    assert len(relation_classes_seen) >= 3
    for a in anomalies:
        assert type(a) is Anomaly  # noqa: E721 -- exact type check: no subclassing exists


# ---------------------------------------------------------------------------
# Coverage-regression: every one of the 14 fault types the abandoned
# engine.py/models.py detectors were built for gets at least one matching
# fixture caught by the new scanner (task requirement 5, part 2). Honest gaps
# named where not covered -- never forced.
# ---------------------------------------------------------------------------


def test_coverage_missing_object_pvc():
    """Abandoned MissingObjectFault / PVCClaimMismatchFault (object_reconstruction.py, pvc_storage_faults.py)."""
    state = {
        "persistentvolumeclaims": [{"metadata": {"name": "real-pvc"}}],
        "pods": [
            {
                "metadata": {"name": "app-1", "namespace": "ns"},
                "spec": {"volumes": [{"persistentVolumeClaim": {"claimName": "nonexistent-pvc"}}]},
            }
        ],
    }
    anomalies = scan(state)
    assert any(a.kind == "PersistentVolumeClaim" and a.relation_class == "dangling_reference" for a in anomalies)


def test_coverage_missing_service_backend():
    """Abandoned IngressMisrouteFault (ingress_targetport.py)."""
    state = {
        "services": [{"metadata": {"name": "real-svc"}, "spec": {"ports": [{"port": 80}]}}],
        "ingresses": [
            {
                "metadata": {"name": "ing1", "namespace": "ns"},
                "spec": {
                    "rules": [
                        {"http": {"paths": [{"backend": {"service": {"name": "typo-svc", "port": {"number": 80}}}}]}}
                    ]
                },
            }
        ],
    }
    anomalies = scan(state)
    assert any(a.kind == "Ingress" and a.relation_class == "dangling_reference" for a in anomalies)


def test_coverage_target_port_mismatch():
    """Abandoned TargetPortFault (ingress_targetport.py)."""
    state = {
        "services": [{"metadata": {"name": "real-svc"}, "spec": {"ports": [{"port": 8080}]}}],
        "ingresses": [
            {
                "metadata": {"name": "ing1", "namespace": "ns"},
                "spec": {
                    "rules": [
                        {"http": {"paths": [{"backend": {"service": {"name": "real-svc", "port": {"number": 80}}}}]}}
                    ]
                },
            }
        ],
    }
    anomalies = scan(state)
    assert any(a.kind == "Ingress" and a.relation_class == "declared_vs_observed" for a in anomalies)


def test_coverage_cronjob_mutation():
    """Abandoned CronJobMutationFault (cronjob_mutation.py)."""
    state = {
        "cronjobs": [
            {
                "metadata": {"name": "nightly", "namespace": "ns", "annotations": {"baseline-schedule": "0 2 * * *"}},
                "spec": {"schedule": "* * * * *"},
            }
        ]
    }
    anomalies = scan(state)
    assert any(a.kind == "CronJob" and a.relation_class == "declared_vs_observed" for a in anomalies)


def test_coverage_coredns_fault_via_configmap_declared_vs_observed():
    """Abandoned CoreDNSFault (coredns_fault.py) -- CoreDNS config lives in a ConfigMap
    in kube-system; represented here as the general ConfigMap declared_vs_observed check."""
    # CoreDNS's own Corefile is not modeled as a distinct kind by this scanner (honest gap,
    # see report item 5) -- the closest structural analog it does catch is a ConfigMap whose
    # data drifted from a known-good baseline, exercised directly via diff_engine:
    anomaly = diff_engine.compare_declared_vs_observed(
        kind="ConfigMap",
        object_name="coredns",
        namespace="kube-system",
        field="data.Corefile",
        declared="forward . /etc/resolv.conf",
        observed="forward . 8.8.8.8 STALE",
    )
    assert anomaly is not None
    assert anomaly.relation_class == "declared_vs_observed"


def test_coverage_workload_misconfig_image_drift():
    """Abandoned WorkloadMisconfigFault (rolling_update_misconfig.py)."""
    state = {
        "deployments": [
            {
                "metadata": {"name": "app", "namespace": "ns"},
                "spec": {
                    "replicas": 1,
                    "selector": {"matchLabels": {"app": "app"}},
                    "template": {"spec": {"containers": [{"image": "app:v2"}]}},
                },
                "status": {"observedImage": "app:v1-rollback-stuck"},
            }
        ],
        "pods": [
            {
                "metadata": {"name": "app-1", "namespace": "ns", "labels": {"app": "app"}},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }
        ],
    }
    anomalies = scan(state)
    assert any(a.kind == "Deployment" and a.field == "image" for a in anomalies)


def test_coverage_dns_policy_override():
    """Abandoned DnsPolicyOverrideFault (dns_policy_override.py)."""
    state = {
        "pods": [
            {
                "metadata": {"name": "app-1", "namespace": "ns", "annotations": {"baseline-dns-policy": "ClusterFirst"}},
                "spec": {"dnsPolicy": "None"},
            }
        ]
    }
    anomalies = scan(state)
    assert any(a.kind == "Pod" and a.field == "spec.dnsPolicy" for a in anomalies)


def test_coverage_host_port_conflict():
    """Abandoned HostPortConflictFault (host_port_conflict.py)."""
    state = {
        "pods": [
            {
                "metadata": {"name": "app-1", "namespace": "ns"},
                "spec": {"containers": [{"ports": [{"hostPort": 9090}]}]},
            },
            {
                "metadata": {"name": "app-2", "namespace": "ns"},
                "spec": {"containers": [{"ports": [{"hostPort": 9090}]}]},
            },
        ]
    }
    anomalies = scan(state)
    assert any(a.kind == "Pod" and "hostPort" in a.field for a in anomalies)


def test_coverage_probe_fault():
    """Abandoned ProbeFault (probe_heuristics.py)."""
    state = {
        "pods": [
            {
                "metadata": {"name": "app-1", "namespace": "ns"},
                "spec": {
                    "containers": [
                        {
                            "name": "main",
                            "baselineFailureThreshold": 3,
                            "livenessProbe": {"failureThreshold": 1},
                        }
                    ]
                },
            }
        ]
    }
    anomalies = scan(state)
    assert any(a.kind == "Pod" and a.field == "probe.failureThreshold" for a in anomalies)


def test_coverage_rbac_misconfig():
    """Abandoned RBACMisconfigFault (rbac_misconfig.py) -- already exercised above."""
    state = {
        "clusterroles": [{"metadata": {"name": "r"}, "rules": [{"resources": ["pods"], "verbs": ["get"]}]}],
        "clusterrolebindings": [
            {"roleRef": {"name": "r"}, "subjects": [{"kind": "ServiceAccount", "name": "sa", "namespace": "ns"}]}
        ],
        "pods": [
            {
                "metadata": {"name": "p", "namespace": "ns", "annotations": {"required-rbac": "delete:pods"}},
                "spec": {"serviceAccountName": "sa"},
            }
        ],
    }
    anomalies = scan(state)
    assert any(a.relation_class == "insufficient_capability" for a in anomalies)


def test_coverage_pvc_multi_attach_via_aggregate_threshold():
    """Abandoned PVCMultiAttachFault (pvc_storage_faults.py) -- represented as an aggregate
    threshold on concurrent claims, exercised directly via diff_engine (no dedicated kind
    analyzer wired for this specific multi-attach aggregation in the registry -- honest gap,
    see report item 5)."""
    anomaly = diff_engine.find_aggregate_threshold_violation(
        kind="PersistentVolumeClaim",
        object_name="shared-data",
        namespace="ns",
        field="attachedPods",
        total_observed=2.0,
        limit=1.0,
        unit=" pods (ReadWriteOnce)",
    )
    assert anomaly is not None
    assert anomaly.relation_class == "aggregate_threshold"


def test_coverage_scheduling_deadlock_named_gap():
    """Abandoned SchedulingDeadlockFault (scheduling_deadlock.py, anti-affinity deadlock) --
    NOT covered by any registered ObjectKindAnalyzer in this scanner. No Node/scheduling
    kind analyzer exists here. Honest gap, named per absence-is-not-evidence.md: this test
    documents the gap rather than forcing a false-positive fixture to claim coverage."""
    assert "Node" not in __import__(
        "autofde_lab_planner.scanner.registry", fromlist=["ANALYZERS"]
    ).ANALYZERS


# ---------------------------------------------------------------------------
# Taxonomy: classify real anomalies against real SREGym inject_* method names,
# and honestly return UNCLASSIFIED for something that matches nothing.
# ---------------------------------------------------------------------------


def test_taxonomy_classifies_known_anomaly():
    a = Anomaly(
        kind="PersistentVolumeClaim",
        object_name="app-1",
        namespace="ns",
        relation_class="dangling_reference",
        field="spec.volumes[].persistentVolumeClaim.claimName",
        observed="missing-pvc",
        expected=None,
        detail="",
    )
    assert taxonomy.classify(a) == taxonomy.INJECT_PVC_CLAIM_MISMATCH


def test_taxonomy_returns_unclassified_honestly():
    a = Anomaly(
        kind="TotallyUnknownKind",
        object_name="x",
        namespace="ns",
        relation_class="aggregate_threshold",
        field="nonsense",
        observed="1",
        expected="0",
        detail="",
    )
    assert taxonomy.classify(a) == taxonomy.UNCLASSIFIED
