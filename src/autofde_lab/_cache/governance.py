# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Policy-as-code admission for enterprise cache use."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "CacheGovernanceError",
    "DataClassification",
    "EnterpriseContext",
    "GovernanceDecision",
    "GovernancePolicy",
    "NamespaceRule",
    "PolicyEngine",
]

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class CacheGovernanceError(PermissionError):
    """Raised when an enterprise policy refuses a cache operation."""


class DataClassification(str, Enum):
    """Data handling level carried by an enterprise cache request."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class EnterpriseContext:
    """Identity and provenance that bind a request to a deployment."""

    tenant: str
    application: str
    environment: str
    release_id: str
    model_fingerprint: str
    data_fingerprint: str
    classification: DataClassification = DataClassification.INTERNAL
    actor: str = "service"
    change_ticket: str | None = None
    estimated_bytes: int = 0
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "tenant",
            "application",
            "environment",
            "release_id",
            "model_fingerprint",
            "data_fingerprint",
            "actor",
        ):
            value = getattr(self, name)
            if not value or not _IDENTIFIER.fullmatch(value):
                raise ValueError(
                    f"{name} must match {_IDENTIFIER.pattern!r}: {value!r}"
                )
        if self.estimated_bytes < 0:
            raise ValueError("estimated_bytes cannot be negative")
        clean_attributes: dict[str, str] = {}
        for key, value in self.attributes.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("enterprise attributes must map strings to strings")
            if not _IDENTIFIER.fullmatch(key):
                raise ValueError(f"invalid enterprise attribute name: {key!r}")
            clean_attributes[key] = value
        object.__setattr__(
            self,
            "attributes",
            MappingProxyType(clean_attributes),
        )

    @property
    def subject_id(self) -> str:
        return "/".join((self.tenant, self.application, self.environment, self.actor))


@dataclass(frozen=True)
class NamespaceRule:
    """Allow or deny one namespace and method pattern."""

    namespace_pattern: str
    method_pattern: str = "*"
    allow: bool = True
    classifications: frozenset[DataClassification] = frozenset(DataClassification)
    max_ttl_seconds: float | None = None
    allow_stale_if_error: bool = True
    allow_persistence: bool = True
    required_attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.namespace_pattern:
            raise ValueError("namespace_pattern must be non-empty")
        if not self.method_pattern:
            raise ValueError("method_pattern must be non-empty")
        if self.max_ttl_seconds is not None and self.max_ttl_seconds <= 0:
            raise ValueError("max_ttl_seconds must be positive or None")
        object.__setattr__(
            self,
            "classifications",
            frozenset(self.classifications),
        )
        object.__setattr__(
            self,
            "required_attributes",
            MappingProxyType(dict(self.required_attributes)),
        )

    def matches(
        self,
        *,
        context: EnterpriseContext,
        namespace: str,
        method: str,
    ) -> bool:
        return (
            fnmatch.fnmatchcase(namespace, self.namespace_pattern)
            and fnmatch.fnmatchcase(method, self.method_pattern)
            and context.classification in self.classifications
            and all(
                context.attributes.get(key) == value
                for key, value in self.required_attributes.items()
            )
        )


_DEFAULT_TTL = MappingProxyType(
    {
        DataClassification.PUBLIC: 7 * 24 * 60 * 60.0,
        DataClassification.INTERNAL: 24 * 60 * 60.0,
        DataClassification.CONFIDENTIAL: 60 * 60.0,
        DataClassification.RESTRICTED: 5 * 60.0,
    }
)


@dataclass(frozen=True)
class GovernancePolicy:
    """Fail-closed enterprise policy evaluated before cache access."""

    rules: tuple[NamespaceRule, ...] = ()
    allowed_environments: frozenset[str] = frozenset({"dev", "test", "staging", "prod"})
    default_allow: bool = False
    require_namespace_binding: bool = True
    require_change_ticket_for_prod_invalidation: bool = True
    allow_restricted_persistence: bool = False
    max_ttl_by_classification: Mapping[DataClassification, float] = field(
        default_factory=lambda: _DEFAULT_TTL
    )
    policy_version: str = "1"

    def __post_init__(self) -> None:
        if not self.policy_version:
            raise ValueError("policy_version must be non-empty")
        object.__setattr__(self, "rules", tuple(self.rules))
        object.__setattr__(
            self,
            "allowed_environments",
            frozenset(self.allowed_environments),
        )
        ttl_map = dict(self.max_ttl_by_classification)
        missing = set(DataClassification) - set(ttl_map)
        if missing:
            names = sorted(member.value for member in missing)
            raise ValueError(f"missing TTL limits for: {names}")
        if any(value <= 0 for value in ttl_map.values()):
            raise ValueError("classification TTL limits must be positive")
        object.__setattr__(
            self,
            "max_ttl_by_classification",
            MappingProxyType(ttl_map),
        )

    @classmethod
    def company_default(cls) -> "GovernancePolicy":
        """Return a strict baseline suitable for a shared company platform."""

        return cls(
            rules=(
                NamespaceRule(
                    namespace_pattern="*/shared/reference/*",
                    classifications=frozenset(
                        {
                            DataClassification.PUBLIC,
                            DataClassification.INTERNAL,
                        }
                    ),
                    max_ttl_seconds=7 * 24 * 60 * 60.0,
                ),
                NamespaceRule(
                    namespace_pattern="*",
                    classifications=frozenset(
                        {
                            DataClassification.PUBLIC,
                            DataClassification.INTERNAL,
                            DataClassification.CONFIDENTIAL,
                        }
                    ),
                ),
                NamespaceRule(
                    namespace_pattern="*",
                    classifications=frozenset({DataClassification.RESTRICTED}),
                    allow=True,
                    allow_persistence=False,
                    allow_stale_if_error=False,
                ),
            )
        )

    def digest(self) -> str:
        payload = {
            "policy_version": self.policy_version,
            "allowed_environments": sorted(self.allowed_environments),
            "default_allow": self.default_allow,
            "require_namespace_binding": self.require_namespace_binding,
            "require_change_ticket_for_prod_invalidation": (
                self.require_change_ticket_for_prod_invalidation
            ),
            "allow_restricted_persistence": self.allow_restricted_persistence,
            "max_ttl_by_classification": {
                key.value: value
                for key, value in sorted(
                    self.max_ttl_by_classification.items(),
                    key=lambda item: item[0].value,
                )
            },
            "rules": [
                {
                    "namespace_pattern": rule.namespace_pattern,
                    "method_pattern": rule.method_pattern,
                    "allow": rule.allow,
                    "classifications": sorted(
                        value.value for value in rule.classifications
                    ),
                    "max_ttl_seconds": rule.max_ttl_seconds,
                    "allow_stale_if_error": rule.allow_stale_if_error,
                    "allow_persistence": rule.allow_persistence,
                    "required_attributes": dict(rule.required_attributes),
                }
                for rule in self.rules
            ],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class GovernanceDecision:
    """Evidence-backed admission result for one cache operation."""

    admitted: bool
    reasons: tuple[str, ...]
    max_ttl_seconds: float
    allow_stale_if_error: bool
    allow_persistence: bool
    required_tags: tuple[str, ...]
    policy_digest: str

    def require(self) -> "GovernanceDecision":
        if not self.admitted:
            raise CacheGovernanceError("; ".join(self.reasons))
        return self


class PolicyEngine:
    """Evaluate immutable policy without executing user code."""

    def __init__(self, policy: GovernancePolicy) -> None:
        self.policy = policy
        self.policy_digest = policy.digest()

    def evaluate(
        self,
        *,
        context: EnterpriseContext,
        namespace: str,
        method: str,
        persistent_enabled: bool,
    ) -> GovernanceDecision:
        reasons: list[str] = []
        if context.environment not in self.policy.allowed_environments:
            reasons.append(f"environment is not admitted: {context.environment!r}")
        if not namespace or namespace.startswith("_"):
            reasons.append("namespace must be non-empty and public")
        if not method or method.startswith("_") or method.startswith("sample"):
            reasons.append(f"method is not cacheable: {method!r}")

        expected_prefix = "/".join(
            (context.tenant, context.application, context.environment)
        )
        if self.policy.require_namespace_binding and not (
            namespace == expected_prefix or namespace.startswith(expected_prefix + "/")
        ):
            reasons.append(
                "namespace is not bound to tenant/application/environment: "
                f"expected prefix {expected_prefix!r}"
            )

        rule = next(
            (
                candidate
                for candidate in self.policy.rules
                if candidate.matches(
                    context=context,
                    namespace=namespace,
                    method=method,
                )
            ),
            None,
        )
        admitted = self.policy.default_allow if rule is None else rule.allow
        if not admitted:
            reasons.append("no allow rule admitted the operation")

        classification_ttl = self.policy.max_ttl_by_classification[
            context.classification
        ]
        rule_ttl = rule.max_ttl_seconds if rule is not None else None
        max_ttl = min(
            classification_ttl,
            rule_ttl if rule_ttl is not None else classification_ttl,
        )
        allow_stale = rule.allow_stale_if_error if rule is not None else False
        allow_persistence = rule.allow_persistence if rule is not None else False
        if context.classification is DataClassification.RESTRICTED:
            allow_stale = False
            allow_persistence = (
                allow_persistence and self.policy.allow_restricted_persistence
            )
        if persistent_enabled and not allow_persistence:
            reasons.append(
                "persistent caching is not admitted for this data classification"
            )

        tags = (
            f"tenant:{context.tenant}",
            f"application:{context.application}",
            f"environment:{context.environment}",
            f"release:{context.release_id}",
            f"model:{context.model_fingerprint}",
            f"data:{context.data_fingerprint}",
            f"classification:{context.classification.value}",
            f"policy:{self.policy_digest}",
        )
        return GovernanceDecision(
            admitted=not reasons,
            reasons=tuple(reasons) or ("admitted",),
            max_ttl_seconds=max_ttl,
            allow_stale_if_error=allow_stale,
            allow_persistence=allow_persistence,
            required_tags=tags,
            policy_digest=self.policy_digest,
        )

    def authorize_invalidation(
        self,
        *,
        context: EnterpriseContext,
        reason: str,
    ) -> None:
        if not reason.strip():
            raise CacheGovernanceError("invalidation reason must be non-empty")
        if (
            context.environment == "prod"
            and self.policy.require_change_ticket_for_prod_invalidation
            and not context.change_ticket
        ):
            raise CacheGovernanceError(
                "production invalidation requires a change ticket"
            )
