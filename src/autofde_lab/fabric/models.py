# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typed contracts for the scikit-decide agentic fabric."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility
    from enum import Enum

    class StrEnum(str, Enum):
        """Minimal stdlib-compatible StrEnum fallback."""


class DecisionStanding(StrEnum):
    """Standing of a bounded planning run."""

    SOLVED = "SOLVED"
    BOUNDED = "BOUNDED"
    REFUSED = "REFUSED"


class CacheStatus(StrEnum):
    """Cache disposition for an observed operation."""

    HIT = "HIT"
    MISS = "MISS"
    BYPASS = "BYPASS"


class RefusalCode(StrEnum):
    """Stable refusal identifiers for protocol-independent clients."""

    DEPENDENCY_UNAVAILABLE = "SKD-FABRIC-001"
    DOMAIN_UNKNOWN = "SKD-FABRIC-002"
    SOLVER_UNKNOWN = "SKD-FABRIC-003"
    INVALID_ARGUMENTS = "SKD-FABRIC-004"
    SOLVER_INCOMPATIBLE = "SKD-FABRIC-005"
    DOMAIN_CONSTRUCTION_FAILED = "SKD-FABRIC-006"
    SOLVER_CONSTRUCTION_FAILED = "SKD-FABRIC-007"
    SOLVE_FAILED = "SKD-FABRIC-008"
    SERIALIZATION_FAILED = "SKD-FABRIC-009"
    NATURAL_LANGUAGE_COMPILER_UNAVAILABLE = "SKD-FABRIC-010"
    NATURAL_LANGUAGE_COMPILATION_FAILED = "SKD-FABRIC-011"
    CANCELLATION_UNSUPPORTED = "SKD-FABRIC-012"


class DecisionRefusal(ValueError):
    """A fail-closed, machine-readable refusal."""

    def __init__(
        self,
        code: RefusalCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cache_status: CacheStatus = CacheStatus.BYPASS,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.cache_status = cache_status
        super().__init__(f"{code.value}: {message}")

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible refusal payload."""
        return {
            "standing": DecisionStanding.REFUSED.value,
            "code": self.code.value,
            "message": str(self),
            "details": self.details,
            "cache_status": self.cache_status.value,
        }

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        cache_status: CacheStatus = CacheStatus.HIT,
    ) -> DecisionRefusal:
        """Rehydrate a cached deterministic refusal."""
        message = str(payload.get("message", "cached refusal"))
        prefix = f"{payload.get('code')}: "
        if message.startswith(prefix):
            message = message[len(prefix) :]
        return cls(
            RefusalCode(str(payload["code"])),
            message,
            details=dict(payload.get("details", {})),
            cache_status=cache_status,
        )


@dataclass(frozen=True)
class DecisionRequest:
    """Material identities required to solve and safely reuse a decision."""

    domain: str
    solver: str | None = None
    domain_arguments: dict[str, Any] = field(default_factory=dict)
    solver_arguments: dict[str, Any] = field(default_factory=dict)
    max_steps: int = 100
    subject_digest: str = "UNBOUND_SUBJECT"
    policy_digest: str = "UNBOUND_POLICY"
    environment_digest: str = "UNBOUND_ENVIRONMENT"
    randomness_digest: str = "UNBOUND_RANDOMNESS"
    use_cache: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        return asdict(self)

    def semantic_dict(self) -> dict[str, Any]:
        """Return decision semantics without the local cache-control flag."""
        payload = self.as_dict()
        payload.pop("use_cache")
        return payload

    def has_exact_reuse_identity(self) -> bool:
        """Return whether all authority and nondeterminism identities are bound."""
        values = (
            self.subject_digest,
            self.policy_digest,
            self.environment_digest,
            self.randomness_digest,
        )
        return all(value and not value.startswith("UNBOUND_") for value in values)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DecisionRequest:
        """Create a request from a strict JSON object."""
        allowed = {
            "domain",
            "solver",
            "domain_arguments",
            "solver_arguments",
            "max_steps",
            "subject_digest",
            "policy_digest",
            "environment_digest",
            "randomness_digest",
            "use_cache",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise DecisionRefusal(
                RefusalCode.INVALID_ARGUMENTS,
                "unknown decision request fields",
                details={"unknown": unknown},
            )
        if not isinstance(payload.get("domain"), str) or not payload["domain"]:
            raise DecisionRefusal(
                RefusalCode.INVALID_ARGUMENTS,
                "domain is required and must be a non-empty string",
            )
        domain_arguments = payload.get("domain_arguments", {})
        solver_arguments = payload.get("solver_arguments", {})
        if not isinstance(domain_arguments, dict) or not isinstance(
            solver_arguments, dict
        ):
            raise DecisionRefusal(
                RefusalCode.INVALID_ARGUMENTS,
                "domain_arguments and solver_arguments must be JSON objects",
            )
        return cls(
            domain=payload["domain"],
            solver=payload.get("solver"),
            domain_arguments=dict(domain_arguments),
            solver_arguments=dict(solver_arguments),
            max_steps=int(payload.get("max_steps", 100)),
            subject_digest=str(payload.get("subject_digest", "UNBOUND_SUBJECT")),
            policy_digest=str(payload.get("policy_digest", "UNBOUND_POLICY")),
            environment_digest=str(
                payload.get("environment_digest", "UNBOUND_ENVIRONMENT")
            ),
            randomness_digest=str(
                payload.get("randomness_digest", "UNBOUND_RANDOMNESS")
            ),
            use_cache=bool(payload.get("use_cache", True)),
        )


@dataclass(frozen=True)
class DecisionCatalog:
    """Registered domain and solver names."""

    domains: tuple[str, ...]
    solvers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionMatch:
    """Compatible solvers for an instantiated domain."""

    domain: str
    domain_arguments: dict[str, Any]
    compatible_solvers: tuple[str, ...]
    cache_status: CacheStatus
    identity_sha256: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cache_status"] = self.cache_status.value
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        cache_status: CacheStatus,
    ) -> DecisionMatch:
        return cls(
            domain=str(payload["domain"]),
            domain_arguments=dict(payload.get("domain_arguments", {})),
            compatible_solvers=tuple(payload.get("compatible_solvers", ())),
            cache_status=cache_status,
            identity_sha256=str(payload["identity_sha256"]),
        )


@dataclass(frozen=True)
class DecisionStep:
    """One transition in a bounded rollout."""

    index: int
    observation: Any
    action: Any
    next_observation: Any
    value: Any
    termination: bool
    info: Any

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionResult:
    """Receipt-bearing solve and bounded rollout result."""

    schema: str
    standing: DecisionStanding
    request: DecisionRequest
    solver: str
    initial_observation: Any
    steps: tuple[DecisionStep, ...]
    terminal: bool
    cache_status: CacheStatus
    input_sha256: str
    trajectory_sha256: str
    receipt_sha256: str
    claim_ceiling: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["standing"] = self.standing.value
        payload["cache_status"] = self.cache_status.value
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        cache_status: CacheStatus,
    ) -> DecisionResult:
        return cls(
            schema=str(payload["schema"]),
            standing=DecisionStanding(str(payload["standing"])),
            request=DecisionRequest.from_dict(dict(payload["request"])),
            solver=str(payload["solver"]),
            initial_observation=payload.get("initial_observation"),
            steps=tuple(DecisionStep(**step) for step in payload.get("steps", ())),
            terminal=bool(payload.get("terminal", False)),
            cache_status=cache_status,
            input_sha256=str(payload["input_sha256"]),
            trajectory_sha256=str(payload["trajectory_sha256"]),
            receipt_sha256=str(payload["receipt_sha256"]),
            claim_ceiling=str(payload["claim_ceiling"]),
        )
