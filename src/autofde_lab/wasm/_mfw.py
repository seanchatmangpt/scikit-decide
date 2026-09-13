"""MFW planning bridge admitted by wasm4pm and exposed to scikit-decide.

The bridge separates construction from actuation. MFW manufactures a candidate
plan envelope; this host validates it; the embedded MFW and wasm4pm adapters
execute the receipt-bound ``admit`` operation; no action is executed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import shutil
import subprocess
from typing import Any, Mapping, Protocol

INTEROP_SCHEMA = "chatman.mfw-wasm4pm.planning.v1"
RECEIPT_SCHEMA = "chatman.mfw-wasm4pm.receipt.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BASE_STANDINGS = frozenset(
    {
        "UNKNOWN",
        "PARTIAL_ALIVE",
        "ALIVE",
        "BLOCKED",
        "BUILD_BROKEN",
        "UNSUPPORTED",
    }
)


class MfwInteropError(RuntimeError):
    """Typed admission failure for the MFW/wasm4pm boundary."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"REFUSED:{reason}: {detail}")


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


def _valid_standing(value: object) -> bool:
    return isinstance(value, str) and (
        value in _BASE_STANDINGS
        or (value.startswith("REFUSED:") and len(value) > len("REFUSED:"))
    )


def validate_mfw_envelope(
    envelope: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    mfw_revision: str,
    wasm4pm_revision: str,
) -> dict[str, Any]:
    value = dict(envelope)
    if value.get("schema") != INTEROP_SCHEMA:
        raise MfwInteropError("SCHEMA_MISMATCH", f"expected {INTEROP_SCHEMA}")
    if not _valid_standing(value.get("status")):
        raise MfwInteropError("STANDING_INVALID", "unrecognized standing")
    source = value.get("source")
    if not isinstance(source, Mapping):
        raise MfwInteropError("SOURCE_IDENTITY_MISSING", "source object is required")
    expected_source = {
        "mfw_repository": "seanchatmangpt/mfw",
        "mfw_revision": mfw_revision,
        "wasm4pm_repository": "seanchatmangpt/wasm4pm",
        "wasm4pm_revision": wasm4pm_revision,
    }
    if dict(source) != expected_source:
        raise MfwInteropError(
            "SOURCE_IDENTITY_MISMATCH",
            "source pins do not match the registry",
        )
    if not _SHA_RE.fullmatch(mfw_revision) or not _SHA_RE.fullmatch(
        wasm4pm_revision
    ):
        raise MfwInteropError(
            "SOURCE_IDENTITY_INVALID",
            "registry revisions must be exact SHAs",
        )
    if value.get("authority") != {"class": "candidate", "actuation": "none"}:
        raise MfwInteropError(
            "AUTHORITY_ESCALATION",
            "planning interoperability is candidate-only",
        )
    candidate_request = value.get("request")
    candidate_result = value.get("result")
    if not isinstance(candidate_request, Mapping) or not isinstance(
        candidate_result, Mapping
    ):
        raise MfwInteropError(
            "PAYLOAD_INVALID",
            "request and result must be objects",
        )
    if _canonical(candidate_request) != _canonical(request):
        raise MfwInteropError(
            "REQUEST_SUBJECT_MISMATCH",
            "candidate was produced for another request",
        )
    request_digest = _digest(candidate_request)
    result_digest = _digest(candidate_result)
    if value.get("request_sha256") != request_digest:
        raise MfwInteropError(
            "REQUEST_DIGEST_MISMATCH",
            "request digest does not recompute",
        )
    if value.get("result_sha256") != result_digest:
        raise MfwInteropError(
            "RESULT_DIGEST_MISMATCH",
            "result digest does not recompute",
        )
    receipt = value.get("receipt")
    if not isinstance(receipt, Mapping) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise MfwInteropError("RECEIPT_MISSING", "versioned receipt is required")
    if (
        receipt.get("standing") != value.get("status")
        or receipt.get("authority") != value.get("authority")
    ):
        raise MfwInteropError(
            "RECEIPT_MISMATCH",
            "receipt consequence does not match envelope",
        )
    subject = receipt.get("subject")
    if not isinstance(subject, Mapping):
        raise MfwInteropError(
            "RECEIPT_SUBJECT_MISSING",
            "receipt subject must be an object",
        )
    if dict(subject) != {
        **expected_source,
        "request_sha256": request_digest,
        "result_sha256": result_digest,
    }:
        raise MfwInteropError(
            "RECEIPT_SUBJECT_MISMATCH",
            "receipt does not bind exact identities",
        )
    core = {
        key: receipt.get(key)
        for key in ("schema", "subject", "authority", "standing", "replay")
    }
    if receipt.get("receipt_sha256") != _digest(core):
        raise MfwInteropError(
            "RECEIPT_DIGEST_MISMATCH",
            "receipt digest does not recompute",
        )
    replay = receipt.get("replay")
    if (
        not isinstance(replay, Mapping)
        or replay.get("operation") != "admit_mfw_candidate"
        or replay.get("request_sha256") != request_digest
        or replay.get("result_sha256") != result_digest
    ):
        raise MfwInteropError(
            "REPLAY_INVALID",
            "replay must re-enter receipt-bound admission",
        )
    return value


class MfwTransport(Protocol):
    def solve(
        self,
        request: Mapping[str, Any],
        *,
        mfw_revision: str,
        wasm4pm_revision: str,
    ) -> Mapping[str, Any]: ...


class SubprocessMfwTransport:
    """Invoke the bounded MFW oracle CLI without a shell or ambient writes."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.executable = executable or shutil.which("mfw-planner-oracle") or ""
        self.timeout = timeout
        if not self.executable:
            raise MfwInteropError(
                "TRANSPORT_UNAVAILABLE",
                "mfw-planner-oracle is not installed",
            )
        if timeout <= 0:
            raise ValueError("timeout must be positive")

    def solve(
        self,
        request: Mapping[str, Any],
        *,
        mfw_revision: str,
        wasm4pm_revision: str,
    ) -> Mapping[str, Any]:
        command = [
            self.executable,
            "interop",
            "-",
            "--mfw-revision",
            mfw_revision,
            "--wasm4pm-revision",
            wasm4pm_revision,
        ]
        try:
            completed = subprocess.run(
                command,
                input=_canonical(request),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MfwInteropError(
                "TRANSPORT_FAILED",
                "MFW oracle process failed",
            ) from exc
        if completed.returncode not in (0, 2):
            raise MfwInteropError(
                "TRANSPORT_FAILED",
                completed.stderr.decode("utf-8", "replace").strip()
                or "MFW oracle rejected invocation",
            )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise MfwInteropError(
                "TRANSPORT_PROTOCOL_INVALID",
                "MFW oracle returned invalid JSON",
            ) from exc
        if not isinstance(value, dict):
            raise MfwInteropError(
                "TRANSPORT_PROTOCOL_INVALID",
                "MFW oracle result must be an object",
            )
        return value


@dataclass(frozen=True, slots=True)
class MfwPlanResult:
    standing: str
    candidate: Mapping[str, Any]
    receipt: Mapping[str, Any]
    mfw_adapter_receipt: Mapping[str, Any]
    wasm4pm_adapter_receipt: Mapping[str, Any]


class MfwWasm4pmBridge:
    """Construct and admit an MFW plan through both exact WASM identities."""

    def __init__(self, ecosystem: Any, transport: MfwTransport) -> None:
        self.ecosystem = ecosystem
        self.transport = transport

    def solve(self, request: Mapping[str, Any]) -> MfwPlanResult:
        mfw = self.ecosystem.mfw
        wasm4pm = self.ecosystem.wasm4pm
        envelope = self.transport.solve(
            request,
            mfw_revision=mfw.descriptor.revision,
            wasm4pm_revision=wasm4pm.descriptor.revision,
        )
        admitted = validate_mfw_envelope(
            envelope,
            request=request,
            mfw_revision=mfw.descriptor.revision,
            wasm4pm_revision=wasm4pm.descriptor.revision,
        )
        authority = {"class": "candidate", "actuation": "none"}
        mfw_result = mfw.admit({"interop": admitted}, authority=authority)
        wasm_result = wasm4pm.admit({"interop": admitted}, authority=authority)
        if mfw_result.status != "ALIVE":
            raise MfwInteropError(
                "MFW_ADAPTER_NOT_ALIVE",
                f"observed {mfw_result.status}",
            )
        if wasm_result.status != "ALIVE":
            raise MfwInteropError(
                "WASM4PM_ADAPTER_NOT_ALIVE",
                f"observed {wasm_result.status}",
            )
        return MfwPlanResult(
            standing=str(admitted["status"]),
            candidate=admitted["result"],
            receipt=admitted["receipt"],
            mfw_adapter_receipt=mfw_result.receipt,
            wasm4pm_adapter_receipt=wasm_result.receipt,
        )
