"""Capability gate for gymact-backed diagnosing pipelines.

The manifest is an admitted projection of the real gymact capability surface. Runtime
checks are fail-closed in both directions: a listed capability absent upstream is stale,
and a real upstream capability absent from the projection is missing. This closes the
historical failure mode where a five-entry consumer manifest remained technically valid
while the real SREGym world grew to fourteen capabilities.

The gate does not grant execution authority. It only proves that a requested binding is
inside the admitted projection and that the projection can be checked for exact identity
against the real target environment.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "CapabilityGate",
    "CapabilityManifestEntry",
    "CapabilityProjectionDrift",
    "CapabilityRefused",
    "DEFAULT_MANIFEST_PATH",
]

DEFAULT_MANIFEST_PATH = Path(__file__).with_name("gymact_capabilities.toml")


class CapabilityRefused(PermissionError):
    """A requested gymact binding is outside the admitted projection."""

    def __init__(self, binding: str, *, allowed: frozenset[str], environment: str) -> None:
        self.binding = binding
        self.allowed = allowed
        self.environment = environment
        super().__init__(
            f"REFUSED:CAPABILITY_NOT_IN_MANIFEST binding={binding!r} "
            f"environment={environment!r} allowed={sorted(allowed)!r}"
        )


class CapabilityProjectionDrift(RuntimeError):
    """The generated/admitted consumer projection differs from the real world surface."""

    def __init__(
        self,
        *,
        environment: str,
        missing: frozenset[str],
        stale: frozenset[str],
    ) -> None:
        self.environment = environment
        self.missing = missing
        self.stale = stale
        super().__init__(
            "REFUSED:CAPABILITY_PROJECTION_DRIFT "
            f"environment={environment!r} missing={sorted(missing)!r} "
            f"stale={sorted(stale)!r}"
        )


@dataclass(frozen=True)
class CapabilityManifestEntry:
    """One capability admitted by the local projection."""

    name: str
    consequence: str
    reason: str


class CapabilityGate:
    """Load and enforce a real TOML capability projection."""

    def __init__(
        self,
        entries: tuple[CapabilityManifestEntry, ...],
        *,
        environment: str,
        source_pack: str = "",
        source_graph: str = "",
    ) -> None:
        self._entries = entries
        self._by_name: dict[str, CapabilityManifestEntry] = {entry.name: entry for entry in entries}
        if len(self._by_name) != len(entries):
            raise ValueError("REFUSED:DUPLICATE_CAPABILITY_IN_PROJECTION")
        self.environment = environment
        self.source_pack = source_pack
        self.source_graph = source_graph

    @classmethod
    def from_toml(cls, path: Path | str = DEFAULT_MANIFEST_PATH) -> "CapabilityGate":
        """Parse a real TOML projection; missing/empty manifests fail closed."""
        manifest_path = Path(path)
        with manifest_path.open("rb") as handle:
            data: dict[str, Any] = tomllib.load(handle)

        gymact = data.get("gymact", {})
        environment = gymact.get("environment", "")
        source_pack = gymact.get("source_pack", "")
        source_graph = gymact.get("source_graph", "")
        raw_entries = data.get("capability", [])
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValueError(
                f"REFUSED:EMPTY_CAPABILITY_MANIFEST path={manifest_path} -- "
                "zero entries are never treated as implicit authority"
            )

        entries = tuple(
            CapabilityManifestEntry(
                name=entry["name"],
                consequence=entry.get("consequence", ""),
                reason=entry.get("reason", ""),
            )
            for entry in raw_entries
        )
        return cls(
            entries,
            environment=environment,
            source_pack=source_pack,
            source_graph=source_graph,
        )

    @property
    def allowed_names(self) -> frozenset[str]:
        """Exact set admitted by the local projection."""
        return frozenset(self._by_name)

    def entry(self, binding: str) -> CapabilityManifestEntry:
        """Return one admitted entry or raise a typed boundary refusal."""
        try:
            return self._by_name[binding]
        except KeyError:
            raise CapabilityRefused(
                binding,
                allowed=self.allowed_names,
                environment=self.environment,
            ) from None

    def check(self, binding: str) -> None:
        """Refuse a binding outside the admitted projection."""
        self.entry(binding)

    def stale_entries(self, real_names: frozenset[str] | set[str]) -> frozenset[str]:
        """Projected names no longer present in the real upstream world."""
        return self.allowed_names - frozenset(real_names)

    def missing_entries(self, real_names: frozenset[str] | set[str]) -> frozenset[str]:
        """Real upstream names omitted by the local projection.

        This is the inverse of :meth:`stale_entries` and closes the exact drift mode
        where an old subset remains syntactically valid while the world expands.
        """
        return frozenset(real_names) - self.allowed_names

    def assert_exact_world_surface(self, real_names: frozenset[str] | set[str]) -> None:
        """Require set equality with the observed upstream capability surface.

        Raises :class:`CapabilityProjectionDrift` for either omission or stale entry.
        The caller must supply the real observed names; this method never infers them.
        """
        missing = self.missing_entries(real_names)
        stale = self.stale_entries(real_names)
        if missing or stale:
            raise CapabilityProjectionDrift(
                environment=self.environment,
                missing=missing,
                stale=stale,
            )

    def guard_capability(self, capability: Any) -> Any:
        """Check a real Capability-shaped object's ``binding`` and return it unchanged."""
        binding = getattr(capability, "binding", None)
        if binding is None:
            raise CapabilityRefused(
                repr(capability),
                allowed=self.allowed_names,
                environment=self.environment,
            )
        self.check(binding)
        return capability
