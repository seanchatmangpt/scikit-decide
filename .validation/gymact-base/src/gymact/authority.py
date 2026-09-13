"""Authority resolution contracts.

GymAct never treats an authority reference as permission. A consequential
operation is admitted only when an injected resolver returns an explicit
positive decision. The default resolver is fail-closed.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol, runtime_checkable

from gymact.models import AuthorityDecision, AuthorityRequest


@runtime_checkable
class AuthorityResolver(Protocol):
    """External policy/authority decision point for consequential operations."""

    async def authorize(self, request: AuthorityRequest) -> AuthorityDecision: ...


class DenyAuthorityResolver:
    """Fail-closed resolver used when no authority system is configured."""

    async def authorize(self, request: AuthorityRequest) -> AuthorityDecision:
        if request.authority_ref is None:
            return AuthorityDecision(admitted=False, reason="LIVE_AUTHORITY_REQUIRED")
        return AuthorityDecision(admitted=False, reason="AUTHORITY_NOT_ADMITTED")


class AllowListAuthorityResolver:
    """Deterministic bounded resolver for tests, demos, and isolated local gyms.

    This is not a substitute for BRCE or a production policy decision point. It
    admits only exact preconfigured references and emits a distinct evidence IRI.
    """

    def __init__(self, allowed: Collection[str]) -> None:
        self._allowed = frozenset(allowed)

    async def authorize(self, request: AuthorityRequest) -> AuthorityDecision:
        ref = request.authority_ref
        if ref is None:
            return AuthorityDecision(admitted=False, reason="LIVE_AUTHORITY_REQUIRED")
        if ref not in self._allowed:
            return AuthorityDecision(admitted=False, reason="AUTHORITY_NOT_ADMITTED")
        return AuthorityDecision(
            admitted=True,
            reason="AUTHORITY_ADMITTED",
            evidence_ref=f"urn:gymact:authority-decision:{ref}",
        )
