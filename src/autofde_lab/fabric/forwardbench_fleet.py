"""Fleet-level audit and exact materialization for ForwardBench vendors.

The semantic lock, superproject gitlinks, and materialized vendor worktrees are
three independent identity carriers. Fleet standing is exact only when all
three agree for every selected subject.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from autofde_lab.fabric.vendor_materialization import (
    VendorAudit,
    VendorMaterializationState,
    audit_vendor,
    parse_gym_lock,
)
from autofde_lab.fabric.vendor_materializer import materialize_vendor


@dataclass(frozen=True, slots=True)
class ForwardBenchFleetReport:
    audits: tuple[VendorAudit, ...]

    @property
    def total(self) -> int:
        return len(self.audits)

    @property
    def materialized_exact(self) -> int:
        return sum(a.materialized for a in self.audits)

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.materialized_exact == self.total

    @property
    def refused(self) -> tuple[VendorAudit, ...]:
        return tuple(a for a in self.audits if a.state.value.startswith("REFUSED:"))

    @property
    def unmaterialized(self) -> tuple[VendorAudit, ...]:
        return tuple(
            a
            for a in self.audits
            if a.state is VendorMaterializationState.PINNED_UNMATERIALIZED
        )


def _selected_pins(lock_text: str, slugs: Iterable[str] | None) -> dict[str, str]:
    pins = dict(parse_gym_lock(lock_text))
    if slugs is None:
        return pins
    selected = tuple(sorted(set(slugs)))
    missing = tuple(slug for slug in selected if slug not in pins)
    if missing:
        raise KeyError(f"ForwardBench lock has no pin for: {', '.join(missing)}")
    return {slug: pins[slug] for slug in selected}


def audit_forwardbench_fleet(
    superproject: str | Path,
    lock_text: str,
    *,
    slugs: Iterable[str] | None = None,
) -> ForwardBenchFleetReport:
    root = Path(superproject).resolve()
    pins = _selected_pins(lock_text, slugs)
    audits = tuple(
        audit_vendor(
            root,
            f"vendor/gyms/{slug}",
            pinned_revision=revision,
        )
        for slug, revision in sorted(pins.items())
    )
    return ForwardBenchFleetReport(audits)


def materialize_forwardbench_fleet(
    superproject: str | Path,
    lock_text: str,
    *,
    slugs: Iterable[str] | None = None,
    allow_file_protocol: bool = False,
) -> ForwardBenchFleetReport:
    """Materialize selected pinned vendors, refusing drift instead of repairing it.

    Only ``PINNED_UNMATERIALIZED`` subjects are initialized. Any existing
    populated wrong identity, semantic-pin mismatch, or wrong revision remains
    a refusal and is not overwritten.
    """

    root = Path(superproject).resolve()
    pins = _selected_pins(lock_text, slugs)
    audits = tuple(
        materialize_vendor(
            root,
            f"vendor/gyms/{slug}",
            pinned_revision=revision,
            allow_file_protocol=allow_file_protocol,
        )
        for slug, revision in sorted(pins.items())
    )
    return ForwardBenchFleetReport(audits)
