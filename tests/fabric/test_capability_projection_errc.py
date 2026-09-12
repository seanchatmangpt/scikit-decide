"""ERRC courts for generated/drift-guarded gymact capability projections."""

from __future__ import annotations

import pytest

from autofde_lab.fabric.gymact_capability_gate import (
    DEFAULT_MANIFEST_PATH,
    CapabilityGate,
    CapabilityProjectionDrift,
)


gymact = pytest.importorskip(
    "gymact",
    reason="real external gymact package unavailable; named skip, never mocked success",
)
from gymact.gyms.sregym import SREGYM_CAPABILITIES  # noqa: E402


def real_names() -> frozenset[str]:
    return frozenset(capability.binding for capability in SREGYM_CAPABILITIES)


def test_shipped_projection_equals_real_sregym_surface() -> None:
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    observed = real_names()
    assert len(observed) == 14
    assert gate.missing_entries(observed) == frozenset()
    assert gate.stale_entries(observed) == frozenset()
    gate.assert_exact_world_surface(observed)


def test_omitted_real_capability_is_a_named_refusal(tmp_path) -> None:
    observed = real_names()
    omitted = sorted(observed)[-1]
    manifest = tmp_path / "omitted.toml"
    lines = ['[gymact]', 'environment = "sregym"', '']
    for name in sorted(observed - {omitted}):
        lines.extend(
            [
                "[[capability]]",
                f'name = "{name}"',
                'consequence = "DO"',
                'reason = "test projection"',
                "",
            ]
        )
    manifest.write_text("\n".join(lines), encoding="utf-8")
    gate = CapabilityGate.from_toml(manifest)

    assert gate.missing_entries(observed) == frozenset({omitted})
    with pytest.raises(CapabilityProjectionDrift) as excinfo:
        gate.assert_exact_world_surface(observed)
    assert excinfo.value.missing == frozenset({omitted})
    assert excinfo.value.stale == frozenset()
    assert "REFUSED:CAPABILITY_PROJECTION_DRIFT" in str(excinfo.value)


def test_projection_with_stale_entry_and_omission_reports_both(tmp_path) -> None:
    observed = real_names()
    omitted = sorted(observed)[0]
    stale = "not_a_real_sregym_binding"
    manifest = tmp_path / "two_way_drift.toml"
    lines = ['[gymact]', 'environment = "sregym"', '']
    for name in sorted((observed - {omitted}) | {stale}):
        lines.extend(
            [
                "[[capability]]",
                f'name = "{name}"',
                'consequence = "DO"',
                'reason = "test projection"',
                "",
            ]
        )
    manifest.write_text("\n".join(lines), encoding="utf-8")
    gate = CapabilityGate.from_toml(manifest)

    with pytest.raises(CapabilityProjectionDrift) as excinfo:
        gate.assert_exact_world_surface(observed)
    assert excinfo.value.missing == frozenset({omitted})
    assert excinfo.value.stale == frozenset({stale})


def test_duplicate_projection_identity_refuses_at_load(tmp_path) -> None:
    manifest = tmp_path / "duplicate.toml"
    manifest.write_text(
        """
[gymact]
environment = "sregym"

[[capability]]
name = "run_kubectl"
consequence = "DO"
reason = "first"

[[capability]]
name = "run_kubectl"
consequence = "DO"
reason = "duplicate"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="DUPLICATE_CAPABILITY_IN_PROJECTION"):
        CapabilityGate.from_toml(manifest)
