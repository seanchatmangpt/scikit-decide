"""Adapter boundary primitives.

scikit-decide is self-contained. Sibling repositories (``~/mfw``, ``~/bcinr``,
Ferroplan, ``~/mfact``, ``~/ggen``, OpenClaw, ``~/wasm4pm-compat``) are OPTIONAL
adapters, never prerequisites. A missing adapter must never lower the standing of
the core: a clean checkout with none of those repositories present imports
``autofde_lab.adapters`` fine and reports every adapter ``UNAVAILABLE``.

Adapters describe what EXISTS. They carry no actuation, admission, broker, or
receipt semantics. This repository computes candidate plans; it does not actuate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

__all__ = [
    "AdapterStatus",
    "AdapterProbe",
    "Adapter",
    "resolve_home",
    "probe_directory",
]


class AdapterStatus(StrEnum):
    """Outcome of a probe.

    The AVAILABLE/COMPATIBLE split is the reason this enum exists.

    - ``AVAILABLE`` — the backend was FOUND. A directory exists, a binary is on
      ``PATH``. That is all it means.
    - ``COMPATIBLE`` — the backend was found AND its interface matches what we
      expect (an expected entrypoint, a parseable version).

    Finding a binary is not the same as it being usable. Conflating "it is there"
    with "it works with us" is the error this enum exists to prevent: a probe that
    reports COMPATIBLE on the strength of a directory listing has manufactured an
    interface claim out of a filesystem fact.

    - ``INCOMPATIBLE`` — found, and positively determined not to match.
    - ``PARTIAL`` — found, and only some of the expected surface is present.
    - ``UNAVAILABLE`` — not found within the recorded search boundary.
    """

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class AdapterProbe:
    """The result of one probe, including the boundary it searched.

    ``searched`` is REQUIRED and load-bearing. An absence claim must carry the
    search boundary that produced it: "not found" is meaningless without "looked
    here." A probe returning ``UNAVAILABLE`` without recording where it looked is
    a bug, not a terse success — this repository has made that exact mistake three
    times, reporting a ``command -v`` result as a fact about the whole filesystem.
    A negative result is a statement about the recorded paths in ``searched`` and
    about nothing else; readers must be able to see the boundary to know how far
    the claim reaches.

    Attributes:
        status: See :class:`AdapterStatus`.
        detail: Human-readable reason, including *why* a status was chosen.
        located_at: Where the backend was found, or ``None``.
        version: Version string if one could be read WITHOUT importing or
            executing the sibling, else ``None``.
        searched: Every path / ``PATH`` lookup consulted. Must be non-empty.
    """

    status: AdapterStatus
    detail: str
    located_at: str | None = None
    version: str | None = None
    searched: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.searched:
            raise ValueError(
                "AdapterProbe.searched must be non-empty: an absence claim must "
                "carry the search boundary that produced it."
            )

    @property
    def found(self) -> bool:
        """True when the backend was located, whatever its compatibility."""
        return self.status is not AdapterStatus.UNAVAILABLE


@runtime_checkable
class Adapter(Protocol):
    """A declared, probeable optional backend. Zero implementation."""

    name: str

    def probe(self) -> AdapterProbe:
        """Inspect the filesystem/PATH only. MUST NOT raise, ever."""
        ...


def resolve_home(env_var: str, default: str) -> str:
    """Resolve an adapter root, honouring an env override such as ``MFW_HOME``."""
    return os.path.expanduser(os.environ.get(env_var) or default)


def probe_directory(
    *,
    root: str,
    entrypoint: str | None = None,
    absent_detail: str,
    present_detail: str,
) -> AdapterProbe:
    """Shared filesystem-only probe: does ``root`` exist, and its entrypoint?

    Never raises: any OS error is folded into an ``UNAVAILABLE`` result whose
    ``detail`` names the error, since a probe that throws when the backend is
    absent defeats the purpose of probing.
    """
    searched: list[str] = [root]
    entry_path = os.path.join(root, entrypoint) if entrypoint else None
    if entry_path is not None:
        searched.append(entry_path)
    boundary = tuple(searched)
    try:
        if not os.path.isdir(root):
            return AdapterProbe(
                status=AdapterStatus.UNAVAILABLE,
                detail=f"{absent_detail} (no directory at {root})",
                searched=boundary,
            )
        if entry_path is None:
            return AdapterProbe(
                status=AdapterStatus.AVAILABLE,
                detail=f"{present_detail} Found the repository root only; no "
                "entrypoint check was performed, so compatibility is UNKNOWN.",
                located_at=root,
                searched=boundary,
            )
        if os.path.exists(entry_path):
            return AdapterProbe(
                status=AdapterStatus.AVAILABLE,
                detail=f"{present_detail} Entrypoint present at {entry_path}. "
                "AVAILABLE, not COMPATIBLE: the file was found but its interface "
                "was not exercised.",
                located_at=entry_path,
                searched=boundary,
            )
        return AdapterProbe(
            status=AdapterStatus.PARTIAL,
            detail=f"{present_detail} Repository root exists but the expected "
            f"entrypoint {entry_path} is missing (unbuilt or moved).",
            located_at=root,
            searched=boundary,
        )
    except OSError as exc:  # pragma: no cover - defensive; probes never raise
        return AdapterProbe(
            status=AdapterStatus.UNAVAILABLE,
            detail=f"{absent_detail} (probe error: {exc!r})",
            searched=boundary,
        )
