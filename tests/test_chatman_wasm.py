from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

import pytest

from autofde_lab.wasm import (
    ABI_VERSION,
    ArtifactIntegrityError,
    ChatmanEcosystem,
    ComponentRegistry,
    DirectoryArtifactStore,
    MfwInteropError,
    MfwWasm4pmBridge,
    NodeBackend,
    validate_mfw_envelope,
)
from autofde_lab.wasm._artifacts import ARTIFACTS
from autofde_lab.wasm.build import materialize, verify


def node_backend() -> NodeBackend:
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node.js is required for exact Wasm execution in this verifier")
    return NodeBackend(executable)


class BlockedBackend:
    name = "blocked-negative-fixture"

    def invoke(self, artifact: Any, request: bytes) -> bytes:
        decoded = json.loads(request)
        return json.dumps(
            {
                "schema": "chatman.ecosystem.response.v1",
                "status": "BLOCKED",
                "output": {"reason": "EXTERNAL_DEPENDENCY"},
                "receipt": {
                    "schema": "chatman.ecosystem.receipt.v1",
                    "scope": "negative-fixture",
                    "subject": {
                        "component": decoded["component"],
                        "source_revision": decoded["source_revision"],
                    },
                    "standing": "BLOCKED",
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


def test_registry_is_complete_exact_and_artifact_bound() -> None:
    registry = ComponentRegistry.default()
    assert len(registry) == 16
    assert set(ARTIFACTS) == {component.name for component in registry}
    assert ABI_VERSION == "1.1.0"
    for component in registry:
        artifact = ARTIFACTS[component.name]
        data = artifact.bytes()
        assert component.revision and len(component.revision) == 40
        assert component.artifact_sha256 == hashlib.sha256(data).hexdigest()
        assert component.artifact_size == len(data)
        assert data.startswith(b"\x00asm\x01\x00\x00\x00")


def test_aliases_resolve_mu_and_powl() -> None:
    ecosystem = ChatmanEcosystem(backend=node_backend())
    assert ecosystem.mcpp.descriptor.name == "mu-mcpp"
    assert ecosystem.truex.descriptor.name == "mu-truex"
    assert ecosystem.POWL.descriptor.name == "powl"


def test_all_embedded_components_execute_self_test_alive() -> None:
    ecosystem = ChatmanEcosystem(backend=node_backend())
    results = ecosystem.self_test_all()
    assert len(results) == 16
    assert {result.status for result in results} == {"ALIVE"}
    assert ecosystem.missing_artifacts() == ()
    for result in results:
        assert result.receipt["scope"] == "federation-adapter"
        assert (
            result.receipt["artifact"]["sha256"]
            == result.component.artifact_sha256
        )
        assert result.receipt["host"]["backend"] == "node-webassembly"
        assert result.output["semantic_execution"] is False


def test_describe_and_admit_are_receipt_bound() -> None:
    ecosystem = ChatmanEcosystem(backend=node_backend())
    described = ecosystem.ggen.describe()
    admitted = ecosystem.ggen.admit({"graph": "urn:test"})
    assert described.status == "ALIVE"
    assert admitted.status == "ALIVE"
    assert admitted.receipt["subject"] == {
        "component": "ggen",
        "source_revision": ecosystem.ggen.descriptor.revision,
    }


def test_unadmitted_operation_is_typed_refusal() -> None:
    result = ChatmanEcosystem(backend=node_backend()).ggen.invoke("render")
    assert result.status == "REFUSED:OPERATION_NOT_ADMITTED"
    assert result.output["reason"] == "OPERATION_NOT_ADMITTED"
    assert result.receipt["standing"] == "REFUSED:OPERATION_NOT_ADMITTED"
    assert result.receipt["guest_standing"] == "REFUSED"


def test_blocked_guest_standing_is_preserved() -> None:
    result = ChatmanEcosystem(backend=BlockedBackend()).ggen.invoke("self_test")
    assert result.status == "BLOCKED"
    assert result.receipt["standing"] == "BLOCKED"


def test_materialized_inventory_is_deterministic_and_executable(
    tmp_path: Path,
) -> None:
    first = materialize(tmp_path)
    manifest_bytes = (tmp_path / "chatman-ecosystem.json").read_bytes()
    second = materialize(tmp_path)
    assert (tmp_path / "chatman-ecosystem.json").read_bytes() == manifest_bytes
    assert first == second
    report = verify(tmp_path)
    assert report["status"] == "ALIVE"
    assert report["component_count"] == 16
    assert {receipt["status"] for receipt in report["receipts"]} == {"ALIVE"}


def test_directory_store_refuses_artifact_drift(tmp_path: Path) -> None:
    materialize(tmp_path)
    descriptor = ComponentRegistry.default().by_name("ggen")
    (tmp_path / descriptor.artifact).write_bytes(b"not-wasm")
    store = DirectoryArtifactStore(tmp_path)
    with pytest.raises(ArtifactIntegrityError, match="digest mismatch"):
        store.load(descriptor)


def test_registry_manifest_has_no_unverified_runtime_state() -> None:
    manifest = ComponentRegistry.default().as_manifest()
    encoded = json.dumps(manifest, sort_keys=True)
    assert "BLOCKED" not in encoded
    assert "PARTIAL_ALIVE" not in encoded
    assert manifest["component_count"] == 16


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _interop_envelope(
    request: Mapping[str, Any],
    *,
    mfw_revision: str,
    wasm4pm_revision: str,
) -> dict[str, Any]:
    result = {
        "ok": True,
        "oracle": "mfw-python-v1",
        "result": {"planning_type": "classical", "plan": ["move-a-b"]},
    }
    source = {
        "mfw_repository": "seanchatmangpt/mfw",
        "mfw_revision": mfw_revision,
        "wasm4pm_repository": "seanchatmangpt/wasm4pm",
        "wasm4pm_revision": wasm4pm_revision,
    }
    authority = {"class": "candidate", "actuation": "none"}
    request_sha256 = _digest(request)
    result_sha256 = _digest(result)
    receipt_core = {
        "schema": "chatman.mfw-wasm4pm.receipt.v1",
        "subject": {
            **source,
            "request_sha256": request_sha256,
            "result_sha256": result_sha256,
        },
        "authority": authority,
        "standing": "ALIVE",
        "replay": {
            "operation": "admit_mfw_candidate",
            "request_sha256": request_sha256,
            "result_sha256": result_sha256,
        },
    }
    return {
        "schema": "chatman.mfw-wasm4pm.planning.v1",
        "status": "ALIVE",
        "source": source,
        "authority": authority,
        "request": dict(request),
        "request_sha256": request_sha256,
        "result": result,
        "result_sha256": result_sha256,
        "receipt": {
            **receipt_core,
            "receipt_sha256": _digest(receipt_core),
        },
    }


@dataclass
class _Descriptor:
    revision: str


@dataclass
class _AdapterResult:
    status: str
    receipt: dict[str, Any]


class _Binding:
    def __init__(self, revision: str, name: str) -> None:
        self.descriptor = _Descriptor(revision)
        self.name = name
        self.calls: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []

    def admit(
        self,
        payload: Mapping[str, Any],
        *,
        authority: Mapping[str, Any],
    ) -> _AdapterResult:
        self.calls.append((payload, authority))
        return _AdapterResult(
            "ALIVE",
            {"component": self.name, "authority": dict(authority)},
        )


class _Ecosystem:
    def __init__(self, mfw_revision: str, wasm4pm_revision: str) -> None:
        self.mfw = _Binding(mfw_revision, "mfw")
        self.wasm4pm = _Binding(wasm4pm_revision, "wasm4pm")


class _Transport:
    def solve(
        self,
        request: Mapping[str, Any],
        *,
        mfw_revision: str,
        wasm4pm_revision: str,
    ) -> Mapping[str, Any]:
        return _interop_envelope(
            request,
            mfw_revision=mfw_revision,
            wasm4pm_revision=wasm4pm_revision,
        )


def _interop_subject() -> tuple[str, str, dict[str, Any]]:
    registry = ComponentRegistry.default()
    return (
        registry.by_name("mfw").revision,
        registry.by_name("wasm4pm").revision,
        {
            "schema": "mfw.universal-planning.v1",
            "planning_type": "classical",
            "problem": {"id": "tiny"},
        },
    )


def test_mfw_bridge_admits_exact_candidate_through_both_adapters() -> None:
    mfw_revision, wasm4pm_revision, request = _interop_subject()
    ecosystem = _Ecosystem(mfw_revision, wasm4pm_revision)
    result = MfwWasm4pmBridge(ecosystem, _Transport()).solve(request)
    assert result.standing == "ALIVE"
    assert result.candidate["result"]["plan"] == ["move-a-b"]
    assert len(ecosystem.mfw.calls) == 1
    assert len(ecosystem.wasm4pm.calls) == 1
    assert ecosystem.mfw.calls[0][1] == {
        "class": "candidate",
        "actuation": "none",
    }


def test_mfw_candidate_drift_is_refused_before_adapter_execution() -> None:
    mfw_revision, wasm4pm_revision, request = _interop_subject()
    envelope = _interop_envelope(
        request,
        mfw_revision=mfw_revision,
        wasm4pm_revision=wasm4pm_revision,
    )
    envelope["result"]["result"]["plan"].append("tampered")
    with pytest.raises(MfwInteropError, match="RESULT_DIGEST_MISMATCH"):
        validate_mfw_envelope(
            envelope,
            request=request,
            mfw_revision=mfw_revision,
            wasm4pm_revision=wasm4pm_revision,
        )


def test_mfw_non_object_receipt_subject_is_typed_refusal() -> None:
    mfw_revision, wasm4pm_revision, request = _interop_subject()
    envelope = _interop_envelope(
        request,
        mfw_revision=mfw_revision,
        wasm4pm_revision=wasm4pm_revision,
    )
    envelope["receipt"]["subject"] = ["not", "an", "object"]
    with pytest.raises(MfwInteropError, match="RECEIPT_SUBJECT_MISSING"):
        validate_mfw_envelope(
            envelope,
            request=request,
            mfw_revision=mfw_revision,
            wasm4pm_revision=wasm4pm_revision,
        )
