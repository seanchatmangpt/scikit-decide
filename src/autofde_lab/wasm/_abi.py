"""Canonical receipt-bound ABI for the Chatman ecosystem Wasm adapters."""

from __future__ import annotations

ABI_NAME = "chatman:ecosystem/library"
ABI_VERSION = "1.1.0"
REQUEST_SCHEMA = "chatman.ecosystem.invoke.v1"
RESPONSE_SCHEMA = "chatman.ecosystem.response.v1"
RECEIPT_SCHEMA = "chatman.ecosystem.receipt.v1"
REGISTRY_SCHEMA = "chatman.ecosystem.registry.v2"
BUILD_REPORT_SCHEMA = "chatman.ecosystem.build-report.v2"

MEMORY_EXPORT = "memory"
ALLOC_EXPORT = "chatman_alloc"
DEALLOC_EXPORT = "chatman_dealloc"
INVOKE_EXPORT = "chatman_invoke"
ADAPTER_OPERATIONS = ("admit", "describe", "self_test")

WIT = f"""package chatman:ecosystem@{ABI_VERSION};

interface library {{
  record invocation {{
    operation: string,
    payload-json: list<u8>,
    authority-json: list<u8>,
  }}

  record receipt-bound-result {{
    status: string,
    output-json: list<u8>,
    receipt-json: list<u8>,
  }}

  invoke: func(request: invocation) -> result<receipt-bound-result, string>;
}}

world chatman-library {{
  export library;
}}
"""

CORE_ABI = {
    "memory": MEMORY_EXPORT,
    "alloc": ALLOC_EXPORT,
    "dealloc": DEALLOC_EXPORT,
    "invoke": INVOKE_EXPORT,
    "invoke_signature": "(request_ptr: i32, request_len: i32) -> packed_ptr_len: i64",
    "packed_result": "high_u32=response_ptr, low_u32=response_len",
    "imports": [],
    "memory_max_pages": 3,
}
