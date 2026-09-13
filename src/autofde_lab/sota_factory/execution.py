from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from .models import ExperimentPlan, FailureKind, TrialOutcome, TrialResult

_GGEN_SCHEMA = "urn:autofde:execution-profile:v1"
_GGEN_GENERATOR = "ggen:autofde-execution-profile-pack"
_GGEN_AUTHORITY_MODE = "external-only"
_GGEN_TOP_KEYS = {"schema", "generated_by", "authority_mode", "profiles"}
_GGEN_PROFILE_KEYS = {
    "profile_id",
    "source_ref",
    "derived_from",
    "provider",
    "benchmark_revision",
    "scenario",
    "config_json",
    "capability_ref",
    "capability_binding",
    "payload_json",
    "expected_json",
    "input_schema_json",
    "authority_ref",
    "action_ref",
}


@dataclass(frozen=True, slots=True)
class GymActExecutionProfile:
    """Pure-data lowering of one ExperimentPlan into a GymAct consequence request.

    The profile contains no execution grant and cannot authorize DO. Authority remains
    an external input consumed by GymAct/BRCE.
    """

    provider: str
    scenario: str | None = None
    config: Mapping[str, Any] = field(default_factory=dict)
    capability_ref: str | None = None
    capability_binding: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    expected: Mapping[str, Any] = field(default_factory=dict)
    authority_ref: str | None = None
    subject_revision: str | None = None
    action_ref: str | None = None
    input_schema: Mapping[str, Any] = field(default_factory=lambda: {"type": "object"})

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("execution profile provider must be non-empty")
        selected = int(self.capability_ref is not None) + int(
            self.capability_binding is not None
        )
        if selected != 1:
            raise ValueError(
                "execution profile requires exactly one capability selector"
            )
        if not self.expected:
            raise ValueError(
                "execution profile requires a non-empty verification oracle"
            )


@runtime_checkable
class ExecutionProfileResolver(Protocol):
    """CONSTRUCT-only adapter from an experiment identity to executable request data."""

    def resolve(self, plan: ExperimentPlan) -> GymActExecutionProfile: ...


@runtime_checkable
class ExperimentExecutionPort(Protocol):
    """External consequence boundary consumed by the SELECT/LEARN SOTA factory."""

    async def execute(self, plan: ExperimentPlan) -> TrialResult: ...


class ExecutionProfileRefused(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExecutionProfileRefused(
                f"REFUSED:DUPLICATE_EXECUTION_PROFILE_KEY:{key}"
            )
        result[key] = value
    return result


def _required_string(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExecutionProfileRefused(f"REFUSED:EXECUTION_PROFILE_FIELD_REQUIRED:{key}")
    return value


def _nullable_string(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExecutionProfileRefused(f"REFUSED:EXECUTION_PROFILE_FIELD_TYPE:{key}")
    return value or None


def _json_object(
    row: dict[str, Any], key: str, *, nonempty: bool = False
) -> dict[str, Any]:
    lexical = row.get(key)
    if not isinstance(lexical, str):
        raise ExecutionProfileRefused(f"REFUSED:EXECUTION_PROFILE_JSON_REQUIRED:{key}")
    try:
        value = json.loads(lexical, object_pairs_hook=_without_duplicate_keys)
    except ExecutionProfileRefused:
        raise
    except json.JSONDecodeError as exc:
        raise ExecutionProfileRefused(
            f"REFUSED:EXECUTION_PROFILE_JSON_INVALID:{key}"
        ) from exc
    if not isinstance(value, dict) or (nonempty and not value):
        raise ExecutionProfileRefused(
            f"REFUSED:EXECUTION_PROFILE_OBJECT_REQUIRED:{key}"
        )
    return value


class GgenExecutionProfileBundleResolver:
    """Resolve ExperimentPlans only from exact, digest-bound ggen profile output.

    The resolver is deliberately non-actuating. ggen safely manufactures lexical JSON
    data; this boundary performs the strict parse, proves the experiment-plan identity,
    and rejects benchmark revision drift before a request can reach GymAct.
    """

    def __init__(self, raw: bytes, *, expected_sha256: str) -> None:
        observed = _sha256(raw)
        if observed != expected_sha256.lower():
            raise ExecutionProfileRefused(
                "REFUSED:EXECUTION_PROFILE_BUNDLE_DIGEST_DRIFT"
            )
        try:
            document = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_without_duplicate_keys
            )
        except ExecutionProfileRefused:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExecutionProfileRefused(
                "REFUSED:EXECUTION_PROFILE_BUNDLE_JSON"
            ) from exc
        if not isinstance(document, dict) or set(document) != _GGEN_TOP_KEYS:
            raise ExecutionProfileRefused("REFUSED:EXECUTION_PROFILE_BUNDLE_SHAPE")
        if document.get("schema") != _GGEN_SCHEMA:
            raise ExecutionProfileRefused("REFUSED:EXECUTION_PROFILE_SCHEMA")
        if document.get("generated_by") != _GGEN_GENERATOR:
            raise ExecutionProfileRefused("REFUSED:EXECUTION_PROFILE_GENERATOR")
        if document.get("authority_mode") != _GGEN_AUTHORITY_MODE:
            raise ExecutionProfileRefused("REFUSED:EXECUTION_PROFILE_AUTHORITY_MODE")
        rows = document.get("profiles")
        if not isinstance(rows, list) or not rows:
            raise ExecutionProfileRefused("REFUSED:EXECUTION_PROFILE_ROWS_REQUIRED")

        index: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != _GGEN_PROFILE_KEYS:
                raise ExecutionProfileRefused("REFUSED:EXECUTION_PROFILE_ROW_SHAPE")
            profile_id = _required_string(row, "profile_id")
            if profile_id in index:
                raise ExecutionProfileRefused(
                    f"REFUSED:DUPLICATE_EXECUTION_PROFILE:{profile_id}"
                )
            index[profile_id] = row
        self._sha256 = observed
        self._index = index

    @property
    def sha256(self) -> str:
        return self._sha256

    def resolve(self, plan: ExperimentPlan) -> GymActExecutionProfile:
        row = self._index.get(plan.plan_id)
        if row is None:
            raise ExecutionProfileRefused(
                f"REFUSED:EXECUTION_PROFILE_MISSING:{plan.plan_id}"
            )
        revision = _required_string(row, "benchmark_revision")
        if revision != plan.benchmark_revision:
            raise ExecutionProfileRefused(
                f"REFUSED:EXECUTION_PROFILE_REVISION_DRIFT:{plan.plan_id}"
            )
        capability_ref = _nullable_string(row, "capability_ref")
        capability_binding = _nullable_string(row, "capability_binding")
        if (capability_ref is None) == (capability_binding is None):
            raise ExecutionProfileRefused(
                f"REFUSED:EXECUTION_PROFILE_SELECTOR:{plan.plan_id}"
            )
        _required_string(row, "source_ref")
        _required_string(row, "derived_from")
        return GymActExecutionProfile(
            provider=_required_string(row, "provider"),
            scenario=_nullable_string(row, "scenario"),
            config=_json_object(row, "config_json"),
            capability_ref=capability_ref,
            capability_binding=capability_binding,
            payload=_json_object(row, "payload_json"),
            expected=_json_object(row, "expected_json", nonempty=True),
            authority_ref=_nullable_string(row, "authority_ref"),
            subject_revision=revision,
            action_ref=_nullable_string(row, "action_ref"),
            input_schema=_json_object(row, "input_schema_json", nonempty=True),
        )


_FAILURE_MAP = {
    "NONE": FailureKind.NONE,
    "CONFIGURATION": FailureKind.TOOL_POLICY,
    "AUTHORITY": FailureKind.AUTHORITY,
    "DEPENDENCY": FailureKind.DEPENDENCY,
    "CAPABILITY": FailureKind.TOOL_POLICY,
    "EXECUTION": FailureKind.EXECUTION,
    "VERIFICATION": FailureKind.VERIFICATION,
    "UNCERTAIN": FailureKind.EXECUTION,
}


def _map_outcome(standing: str, verified: bool) -> TrialOutcome:
    if standing == "ALIVE" and verified:
        return TrialOutcome.PASS
    if standing in {"BLOCKED", "STALE", "BUILD_BROKEN", "REQUIRES_CONFIGURATION"}:
        return TrialOutcome.BLOCKED
    if standing == "UNSUPPORTED":
        return TrialOutcome.UNSUPPORTED
    if standing == "REFUSED":
        return TrialOutcome.REFUSED
    return TrialOutcome.FAIL


class GymActExecutionPort:
    """Governed adapter from Lab ExperimentPlan to GymAct's autonomic BRCE plane.

    ``controller`` is injected by the caller and is expected to be a configured
    ``gymact.autonomic.AutonomicController``. The adapter deliberately does not create
    a runtime, authority resolver, GrantIssuer, or ExecutionGrant. This keeps Lab on
    SELECT/CONSTRUCT/LEARN while GymAct owns DO.
    """

    def __init__(self, controller: object, resolver: ExecutionProfileResolver) -> None:
        if not isinstance(resolver, ExecutionProfileResolver):
            raise TypeError("resolver does not satisfy ExecutionProfileResolver")
        self._controller = controller
        self._resolver = resolver

    async def execute(self, plan: ExperimentPlan) -> TrialResult:
        try:
            from gymact.autonomic import ConsequenceRequest
        except ImportError as exc:
            raise RuntimeError("GYMACT_AUTONOMIC_EXECUTION_REQUIRED") from exc

        run = getattr(self._controller, "run", None)
        if run is None:
            raise TypeError("controller must expose async run(ConsequenceRequest)")

        profile = self._resolver.resolve(plan)
        request = ConsequenceRequest(
            request_id=plan.plan_id,
            provider=profile.provider,
            scenario=profile.scenario,
            config=dict(profile.config),
            capability_ref=profile.capability_ref,
            capability_binding=profile.capability_binding,
            payload=dict(profile.payload),
            expected=dict(profile.expected),
            authority_ref=profile.authority_ref,
            subject_revision=profile.subject_revision or plan.benchmark_revision,
            action_ref=profile.action_ref,
            input_schema=dict(profile.input_schema),
            idempotency_key=plan.plan_id,
            require_verification=True,
        )
        result = await run(request)
        standing = str(result.standing)
        failure_name = str(result.knowledge.failure_class)
        outcome = _map_outcome(standing, bool(result.verified))
        failure_kind = (
            FailureKind.NONE
            if outcome is TrialOutcome.PASS
            else _FAILURE_MAP.get(failure_name, FailureKind.UNKNOWN)
        )
        return TrialResult(
            plan_id=plan.plan_id,
            benchmark_id=plan.benchmark_id,
            benchmark_revision=plan.benchmark_revision,
            task_id=plan.task_id,
            architecture_digest=plan.architecture_digest,
            outcome=outcome,
            primary_score=1.0 if outcome is TrialOutcome.PASS else 0.0,
            failure_kind=failure_kind,
            blocker="" if outcome is TrialOutcome.PASS else str(result.reason),
            evidence_refs=tuple(str(item) for item in result.receipt_ids),
        )
