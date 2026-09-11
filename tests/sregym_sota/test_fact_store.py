import json

from autofde_lab.sregym_sota.facts import FactStore
from autofde_lab.sregym_sota.powl_process import canonical_read_identity


def test_kubernetes_lists_use_semantic_object_identity_not_only_array_index() -> None:
    payload = {
        "items": [
            {
                "kind": "Service",
                "metadata": {"namespace": "shop", "name": "checkout"},
                "spec": {"ports": [{"port": 80, "targetPort": 8080}]},
            }
        ]
    }
    store = FactStore()
    facts = store.ingest("read:services", json.dumps(payload))
    paths = {fact.path for fact in facts}
    assert any("[kind=Service,ns=shop,name=checkout]" in path for path in paths)
    assert any(path.endswith(".spec.ports[0].targetPort") for path in paths)


def test_exact_read_identity_changes_when_arguments_change() -> None:
    capability = "mcp:kubectl:exec_kubectl_cmd_safely"
    one = canonical_read_identity(capability, {"cmd": "kubectl get pods -A"})
    two = canonical_read_identity(capability, {"cmd": "kubectl get services -A"})
    assert one != two
    assert one == canonical_read_identity(capability, {"cmd": "kubectl get pods -A"})


def test_fact_identity_is_bound_to_exact_read_source() -> None:
    store = FactStore()
    first = store.ingest("read:A", '{"value": 1}')
    second = store.ingest("read:B", '{"value": 1}')
    assert first[0].id != second[0].id
    assert first[0].source == "read:A"
    assert second[0].source == "read:B"
