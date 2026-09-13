"""Materialize, rebuild, and execute the Chatman ecosystem Wasm federation."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from ._abi import BUILD_REPORT_SCHEMA, WIT
from ._artifacts import artifact_for
from ._model import canonical_json_bytes
from ._registry import ComponentRegistry
from ._runtime import ChatmanEcosystem

_C_TEMPLATE = r'''
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
static u8 arena[65536];
static u8 response[4096];
static u32 arena_offset = 0;
static u32 response_len = 0;
static const char COMPONENT[] = "__COMPONENT__";
static const char REVISION[] = "__REVISION__";
static const char CAPABILITY[] = "__CAPABILITY__";
static u32 slen(const char *s) { u32 n = 0; while (s[n]) n++; return n; }
static void putc1(char c) { if (response_len < (u32)sizeof(response)) response[response_len++] = (u8)c; }
static void puts1(const char *s) { for (u32 i = 0; s[i]; i++) putc1(s[i]); }
static void putn(u32 value) { char digits[10]; u32 n = 0; if (value == 0) { putc1('0'); return; } while (value && n < 10) { digits[n++] = (char)('0' + value % 10); value /= 10; } while (n) putc1(digits[--n]); }
static void puthex(u32 value) { static const char hex[] = "0123456789abcdef"; for (int shift = 28; shift >= 0; shift -= 4) putc1(hex[(value >> shift) & 15]); }
static int same(const char *a, const char *b) { u32 i = 0; while (a[i] && b[i] && a[i] == b[i]) i++; return a[i] == 0 && b[i] == 0; }
static u32 fnv1a(const u8 *data, u32 len) { u32 h = 2166136261u; for (u32 i = 0; i < len; i++) { h ^= data[i]; h *= 16777619u; } return h; }
static int extract_operation(const u8 *data, u32 len, char *out, u32 cap) {
  static const char key[] = "\"operation\":\""; u32 key_len = slen(key);
  for (u32 i = 0; i + key_len < len; i++) { u32 j = 0; while (j < key_len && data[i+j] == (u8)key[j]) j++; if (j != key_len) continue; u32 p = i + key_len, n = 0; int escaped = 0; while (p < len) { char c = (char)data[p++]; if (!escaped && c == '"') { if (n < cap) out[n] = 0; return 1; } if (n + 1 < cap) out[n++] = c; if (!escaped && c == '\\') escaped = 1; else escaped = 0; } }
  if (cap) out[0] = 0; return 0;
}
__attribute__((visibility("default"))) u32 chatman_alloc(u32 len) { u32 aligned = (arena_offset + 7u) & ~7u; if (len > (u32)sizeof(arena) || aligned + len > (u32)sizeof(arena)) return 0; arena_offset = aligned + len; return (u32)(u64)(arena + aligned); }
__attribute__((visibility("default"))) void chatman_dealloc(u32 ptr, u32 len) { (void)ptr; (void)len; }
__attribute__((visibility("default"))) u64 chatman_invoke(u32 ptr, u32 len) {
  const u8 *request = (const u8 *)(u64)ptr; char operation[96]; int found = extract_operation(request, len, operation, sizeof(operation)); int admitted = found && (same(operation, "self_test") || same(operation, "describe") || same(operation, "admit")); response_len = 0;
  puts1("{\"schema\":\"chatman.ecosystem.response.v1\",\"status\":\""); puts1(admitted ? "ALIVE" : "REFUSED"); puts1("\",\"output\":{\"adapter\":\""); puts1(COMPONENT); puts1("\",\"capability_class\":\""); puts1(CAPABILITY); puts1("\",\"operation\":\""); puts1(found ? operation : ""); puts1("\",\"request_fingerprint\":\""); puthex(fnv1a(request, len)); puts1("\",\"semantic_execution\":false"); if (!admitted) puts1(",\"reason\":\"OPERATION_NOT_ADMITTED\"");
  puts1("},\"receipt\":{\"schema\":\"chatman.ecosystem.receipt.v1\",\"scope\":\"federation-adapter\",\"subject\":{\"component\":\""); puts1(COMPONENT); puts1("\",\"source_revision\":\""); puts1(REVISION); puts1("\"},\"execution\":{\"runtime\":\"wasm32-core\",\"operation\":\""); puts1(found ? operation : ""); puts1("\",\"request_len\":"); putn(len); puts1("},\"standing\":\""); puts1(admitted ? "ALIVE" : "REFUSED"); puts1("\"}}");
  return (((u64)(u32)(u64)response) << 32) | (u64)response_len;
}
'''


def emit_contract(output: Path, registry: ComponentRegistry) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    wit_path = output / "chatman-ecosystem.wit"
    manifest_path = output / "chatman-ecosystem.json"
    wit_path.write_text(WIT, encoding="utf-8")
    manifest_path.write_bytes(canonical_json_bytes(registry.as_manifest()) + b"\n")
    return wit_path, manifest_path


def materialize(output: Path, registry: ComponentRegistry | None = None) -> dict[str, Any]:
    registry = registry or ComponentRegistry.default()
    wit, manifest = emit_contract(output, registry)
    artifacts = []
    for component in registry:
        data = artifact_for(component.name).bytes()
        path = output / component.artifact
        path.write_bytes(data)
        artifacts.append(
            {
                "component": component.name,
                "path": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "status": "ALIVE",
            }
        )
    return {
        "schema": BUILD_REPORT_SCHEMA,
        "manifest": str(manifest),
        "wit": str(wit),
        "artifacts": artifacts,
    }


def verify(output: Path | None = None) -> dict[str, Any]:
    ecosystem = ChatmanEcosystem(output) if output is not None else ChatmanEcosystem()
    results = ecosystem.self_test_all()
    return {
        "schema": BUILD_REPORT_SCHEMA,
        "component_count": len(results),
        "status": "ALIVE",
        "receipts": [
            {
                "component": result.component.name,
                "status": result.status,
                "receipt": dict(result.receipt),
            }
            for result in results
        ],
    }


def rebuild_verify(output: Path, compiler: str | None = None) -> dict[str, Any]:
    compiler = compiler or shutil.which("clang") or ""
    if not compiler:
        raise RuntimeError("clang is required to rebuild the embedded Wasm adapters")
    output.mkdir(parents=True, exist_ok=True)
    registry = ComponentRegistry.default()
    results = []
    with tempfile.TemporaryDirectory(prefix="chatman-wasm-") as temporary:
        work = Path(temporary)
        for component in registry:
            source = (
                _C_TEMPLATE.replace("__COMPONENT__", component.name)
                .replace("__REVISION__", component.revision)
                .replace("__CAPABILITY__", component.capability_class)
            )
            source_path = work / f"{component.name}.c"
            artifact_path = output / component.artifact
            source_path.write_text(source, encoding="utf-8")
            command = [
                compiler,
                "--target=wasm32",
                "-O2",
                "-nostdlib",
                "-Wl,--no-entry",
                "-Wl,--export-memory",
                "-Wl,--export=chatman_alloc",
                "-Wl,--export=chatman_dealloc",
                "-Wl,--export=chatman_invoke",
                "-Wl,--initial-memory=196608",
                "-Wl,--max-memory=196608",
                "-Wl,--strip-all",
                str(source_path),
                "-o",
                str(artifact_path),
            ]
            completed = subprocess.run(
                command,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            data = artifact_path.read_bytes() if artifact_path.is_file() else b""
            observed = hashlib.sha256(data).hexdigest() if data else None
            status = (
                "ALIVE"
                if completed.returncode == 0
                and observed == component.artifact_sha256
                and len(data) == component.artifact_size
                else "BUILD_BROKEN"
            )
            results.append(
                {
                    "component": component.name,
                    "status": status,
                    "exit_code": completed.returncode,
                    "expected_sha256": component.artifact_sha256,
                    "observed_sha256": observed,
                    "expected_size": component.artifact_size,
                    "observed_size": len(data),
                    "output": completed.stdout,
                }
            )
    standing = "ALIVE" if all(item["status"] == "ALIVE" for item in results) else "BUILD_BROKEN"
    report = {
        "schema": "chatman.ecosystem.rebuild-report.v1",
        "status": standing,
        "component_count": len(results),
        "results": results,
    }
    (output / "rebuild-report.json").write_bytes(canonical_json_bytes(report) + b"\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/chatman-wasm"))
    parser.add_argument("--emit-contract", action="store_true")
    parser.add_argument("--verify-embedded", action="store_true")
    parser.add_argument("--rebuild-verify", action="store_true")
    args = parser.parse_args(argv)
    registry = ComponentRegistry.default()
    if args.emit_contract:
        emit_contract(args.output, registry)
        return 0
    if args.rebuild_verify:
        report = rebuild_verify(args.output)
    elif args.verify_embedded:
        report = verify()
    else:
        report = materialize(args.output, registry)
        report["execution"] = verify(args.output)
        report["status"] = "ALIVE"
    report_path = args.output / "build-report.json"
    args.output.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(canonical_json_bytes(report) + b"\n")
    print(f"status {report['status']}")
    print(f"components {len(registry)}")
    print(f"report {report_path}")
    return 0 if report["status"] == "ALIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
