"""Python bindings for the embedded Chatman ecosystem WebAssembly adapters."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Protocol

from ._abi import ALLOC_EXPORT, DEALLOC_EXPORT, INVOKE_EXPORT, MEMORY_EXPORT
from ._artifacts import artifact_for
from ._model import ComponentDescriptor, Invocation, InvocationResult
from ._registry import ComponentRegistry


class WasmBindingError(RuntimeError):
    pass


class ArtifactIntegrityError(WasmBindingError):
    pass


class RuntimeDependencyUnavailable(WasmBindingError):
    pass


class AbiViolation(WasmBindingError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactImage:
    filename: str
    sha256: str
    data: bytes

    @classmethod
    def from_descriptor(cls, descriptor: ComponentDescriptor, data: bytes) -> "ArtifactImage":
        digest = hashlib.sha256(data).hexdigest()
        if digest != descriptor.artifact_sha256:
            raise ArtifactIntegrityError(
                f"{descriptor.name} artifact digest mismatch: expected {descriptor.artifact_sha256}, observed {digest}"
            )
        if len(data) != descriptor.artifact_size:
            raise ArtifactIntegrityError(
                f"{descriptor.name} artifact size mismatch: expected {descriptor.artifact_size}, observed {len(data)}"
            )
        if not data.startswith(b"\x00asm\x01\x00\x00\x00"):
            raise ArtifactIntegrityError(f"{descriptor.name} is not a WebAssembly v1 module")
        return cls(filename=descriptor.artifact, sha256=digest, data=data)


class ArtifactStore(Protocol):
    def load(self, descriptor: ComponentDescriptor) -> ArtifactImage:
        ...


class EmbeddedArtifactStore:
    def load(self, descriptor: ComponentDescriptor) -> ArtifactImage:
        return ArtifactImage.from_descriptor(descriptor, artifact_for(descriptor.name).bytes())


class DirectoryArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def load(self, descriptor: ComponentDescriptor) -> ArtifactImage:
        path = self.root / descriptor.artifact
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError(f"exact artifact missing: {path}") from exc
        return ArtifactImage.from_descriptor(descriptor, data)


class Backend(Protocol):
    name: str

    def invoke(self, artifact: ArtifactImage, request: bytes) -> bytes:
        ...


_NODE_RUNNER = r"""
const fs = require('fs');
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const bytes = Buffer.from(input.wasm, 'base64');
  const module = await WebAssembly.compile(bytes);
  const imports = WebAssembly.Module.imports(module);
  if (imports.length) throw new Error('ambient imports are not admitted');
  const instance = await WebAssembly.instantiate(module, {});
  const ex = instance.exports;
  for (const name of ['memory', 'chatman_alloc', 'chatman_invoke']) {
    if (!(name in ex)) throw new Error(`missing ABI export: ${name}`);
  }
  const request = Buffer.from(input.request, 'base64');
  const ptr = ex.chatman_alloc(request.length);
  if (!ptr) throw new Error('guest allocation failed');
  new Uint8Array(ex.memory.buffer, ptr, request.length).set(request);
  const packed = ex.chatman_invoke(ptr, request.length);
  const responsePtr = Number((packed >> 32n) & 0xffffffffn);
  const responseLen = Number(packed & 0xffffffffn);
  if (!responseLen || responseLen > 1048576) throw new Error('invalid response length');
  const response = Buffer.from(new Uint8Array(ex.memory.buffer, responsePtr, responseLen));
  if (ex.chatman_dealloc) {
    ex.chatman_dealloc(ptr, request.length);
    ex.chatman_dealloc(responsePtr, responseLen);
  }
  process.stdout.write(response.toString('base64'));
})().catch(err => { console.error(err.stack || String(err)); process.exit(1); });
"""


class NodeBackend:
    name = "node-webassembly"

    def __init__(self, executable: str | None = None, *, timeout: float = 5.0) -> None:
        self.executable = executable or shutil.which("node") or ""
        self.timeout = timeout
        if not self.executable:
            raise RuntimeDependencyUnavailable("Node.js is not available")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

    def invoke(self, artifact: ArtifactImage, request: bytes) -> bytes:
        envelope = json.dumps(
            {
                "wasm": base64.b64encode(artifact.data).decode("ascii"),
                "request": base64.b64encode(request).decode("ascii"),
            },
            separators=(",", ":"),
        )
        try:
            result = subprocess.run(
                [self.executable, "--no-warnings", "-e", _NODE_RUNNER],
                input=envelope,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeDependencyUnavailable("Node.js WebAssembly execution failed") from exc
        if result.returncode != 0:
            raise AbiViolation(result.stderr.strip() or "Node.js rejected the Wasm adapter")
        try:
            return base64.b64decode(result.stdout, validate=True)
        except ValueError as exc:
            raise AbiViolation("Node.js returned invalid base64") from exc


class WasmtimeBackend:
    name = "wasmtime-python"

    def __init__(self, *, fuel: int = 10_000_000) -> None:
        if fuel <= 0:
            raise ValueError("fuel must be positive")
        self._fuel = fuel

    def invoke(self, artifact: ArtifactImage, request: bytes) -> bytes:
        try:
            import wasmtime
        except ImportError as exc:
            raise RuntimeDependencyUnavailable("wasmtime is not installed") from exc
        config = wasmtime.Config()
        config.consume_fuel = True
        engine = wasmtime.Engine(config)
        store = wasmtime.Store(engine)
        store.set_fuel(self._fuel)
        store.set_limits(memory_size=3 * 65536, instances=1, memories=1)
        module = wasmtime.Module(engine, artifact.data)
        if tuple(module.imports):
            raise AbiViolation("ambient imports are not admitted")
        try:
            instance = wasmtime.Instance(store, module, [])
            exports = instance.exports(store)
            memory = exports[MEMORY_EXPORT]
            allocate = exports[ALLOC_EXPORT]
            invoke = exports[INVOKE_EXPORT]
            try:
                deallocate = exports[DEALLOC_EXPORT]
            except KeyError:
                deallocate = None
        except (KeyError, TypeError) as exc:
            raise AbiViolation("component is missing a required Chatman ABI export") from exc
        request_ptr = int(allocate(store, len(request)))
        memory.write(store, request, request_ptr)
        packed = int(invoke(store, request_ptr, len(request)))
        response_ptr = (packed >> 32) & 0xFFFFFFFF
        response_len = packed & 0xFFFFFFFF
        if response_len == 0 or response_len > 1024 * 1024:
            raise AbiViolation("component returned an invalid response length")
        response = bytes(memory.read(store, response_ptr, response_ptr + response_len))
        if deallocate is not None:
            deallocate(store, request_ptr, len(request))
            deallocate(store, response_ptr, response_len)
        return response


class AutoBackend:
    def __init__(self) -> None:
        if importlib.util.find_spec("wasmtime") is not None:
            self._backend: Backend = WasmtimeBackend()
        elif shutil.which("node"):
            self._backend = NodeBackend()
        else:
            raise RuntimeDependencyUnavailable("install wasmtime or provide Node.js")
        self.name = self._backend.name

    def invoke(self, artifact: ArtifactImage, request: bytes) -> bytes:
        return self._backend.invoke(artifact, request)


class ComponentBinding:
    def __init__(self, descriptor: ComponentDescriptor, store: ArtifactStore, backend: Backend) -> None:
        self.descriptor = descriptor
        self.store = store
        self.backend = backend

    @property
    def artifact(self) -> ArtifactImage:
        return self.store.load(self.descriptor)

    @property
    def available(self) -> bool:
        try:
            self.artifact
        except ArtifactIntegrityError:
            return False
        return True

    def invoke(
        self,
        operation: str,
        payload: Mapping[str, Any] | None = None,
        *,
        authority: Mapping[str, Any] | None = None,
    ) -> InvocationResult:
        artifact = self.artifact
        invocation = Invocation(
            component=self.descriptor,
            operation=operation,
            payload=payload or {},
            authority=authority or {},
        )
        try:
            raw = self.backend.invoke(artifact, invocation.to_bytes())
            guest = InvocationResult.from_bytes(self.descriptor, operation, raw)
        except WasmBindingError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise AbiViolation(f"{self.descriptor.name} failed the receipt-bound ABI") from exc
        receipt = dict(guest.receipt)
        receipt["artifact"] = {
            "filename": artifact.filename,
            "sha256": artifact.sha256,
            "size": len(artifact.data),
        }
        receipt["host"] = {"backend": self.backend.name}
        return InvocationResult(
            component=guest.component,
            operation=guest.operation,
            status=guest.status,
            output=guest.output,
            receipt=receipt,
        )

    def self_test(self) -> InvocationResult:
        return self.invoke("self_test", authority={"actuation": "none"})

    def describe(self) -> InvocationResult:
        return self.invoke("describe", authority={"actuation": "none"})

    def admit(self, payload: Mapping[str, Any], *, authority: Mapping[str, Any] | None = None) -> InvocationResult:
        return self.invoke("admit", payload, authority=authority or {"actuation": "none"})


class ChatmanEcosystem:
    def __init__(
        self,
        artifact_root: str | Path | None = None,
        *,
        registry: ComponentRegistry | None = None,
        backend: Backend | None = None,
        store: ArtifactStore | None = None,
    ) -> None:
        if artifact_root is not None and store is not None:
            raise ValueError("provide artifact_root or store, not both")
        self.registry = registry or ComponentRegistry.default()
        self.store = store or (DirectoryArtifactStore(artifact_root) if artifact_root is not None else EmbeddedArtifactStore())
        self.backend = backend or AutoBackend()
        self._bindings: dict[str, ComponentBinding] = {}

    def __iter__(self):
        for component in self.registry:
            yield self.bind(component.name)

    def __getattr__(self, name: str) -> ComponentBinding:
        descriptor = self.registry.by_python_name(name)
        return self.bind(descriptor.name)

    def bind(self, name: str) -> ComponentBinding:
        descriptor = self.registry.by_name(name)
        binding = self._bindings.get(descriptor.name)
        if binding is None:
            binding = ComponentBinding(descriptor, self.store, self.backend)
            self._bindings[descriptor.name] = binding
        return binding

    def inventory(self) -> tuple[dict[str, object], ...]:
        rows = []
        for component in self.registry:
            binding = self.bind(component.name)
            rows.append({**component.as_dict(), "available": binding.available})
        return tuple(rows)

    def missing_artifacts(self) -> tuple[str, ...]:
        return tuple(item["name"] for item in self.inventory() if not item["available"])

    def self_test_all(self) -> tuple[InvocationResult, ...]:
        results = tuple(binding.self_test() for binding in self)
        failures = [result.component.name for result in results if result.status != "ALIVE"]
        if failures:
            raise AbiViolation(f"component self-test did not reach ALIVE: {', '.join(failures)}")
        return results
