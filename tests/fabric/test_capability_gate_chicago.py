"""Chicago-style tests for `autofde_lab.fabric.gymact_capability_gate`.

Real collaborators throughout: a real TOML manifest file on disk (both the
shipped `gymact_capabilities.toml` and, for the malformed/refusal cases, a
real temp file written by the test itself), real `tomllib` parsing, and --
where the real external `gymact` package is importable in this environment
-- real `gymact.gyms.sregym.SREGYM_CAPABILITIES` `Capability` objects
checked against the gate. No `unittest.mock` / `Mock` / `patch` /
`monkeypatch` anywhere in this module.

`gymact` (the real external `~/gymact` package, imported via `import
gymact`) is verified importable in this dev environment as of this session;
the gymact-object tests below run unconditionally rather than being
skipped. The gate's own TOML-parsing and refusal logic (`test_gate_from_...`
and the malformed-manifest cases) is exercised independently of whether
gymact is importable, per this repo's Chicago-style testing rule -- the
gate's enforcement logic does not require gymact itself.
"""

from __future__ import annotations

import pytest

from autofde_lab.fabric.gymact_capability_gate import (
    DEFAULT_MANIFEST_PATH,
    CapabilityGate,
    CapabilityRefused,
)


def test_default_manifest_exists_and_parses() -> None:
    """The shipped manifest is a real file that really parses."""
    assert DEFAULT_MANIFEST_PATH.exists()
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    assert gate.environment == "sregym"
    assert gate.allowed_names == frozenset(
        {
            "observe_cluster_state",
            "run_kubectl",
            "get_benchmark_status",
            "submit_diagnosis",
            "submit_mitigation",
            "jaeger_get_services",
            "jaeger_get_operations",
            "jaeger_get_traces",
            "jaeger_get_dependency_graph",
            "loki_get_logs",
            "loki_get_labels",
            "loki_get_label_values",
            "prometheus_get_metrics",
            "prometheus_get_alerts",
        }
    )


def test_listed_capability_is_permitted() -> None:
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    # No exception raised; entry() returns the real manifest entry.
    entry = gate.entry("run_kubectl")
    assert entry.name == "run_kubectl"
    assert entry.consequence == "DO"
    assert "diagnostic" in entry.reason.lower()
    gate.check("observe_cluster_state")  # no exception


def test_unlisted_capability_is_refused_with_named_error() -> None:
    """A capability name that is not in the manifest -- representing a
    hypothetical ground-truth/scoring-adjacent capability, e.g.
    `get_injected_fault` or `score_submission` -- must be refused with the
    real, named `CapabilityRefused` error, never silently ignored."""
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)

    with pytest.raises(CapabilityRefused) as excinfo:
        gate.check("get_injected_fault")

    err = excinfo.value
    assert err.binding == "get_injected_fault"
    assert err.environment == "sregym"
    assert "get_injected_fault" not in err.allowed
    assert "run_kubectl" in err.allowed
    assert "REFUSED:CAPABILITY_NOT_IN_MANIFEST" in str(err)


def test_unlisted_capability_entry_also_refuses() -> None:
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    with pytest.raises(CapabilityRefused):
        gate.entry("score_submission")


def test_real_toml_file_written_to_disk_round_trips(tmp_path) -> None:
    """Real file on disk, written and re-read by this test -- not a fixture
    baked into the repo -- to exercise `from_toml` against an
    independently-authored manifest shape."""
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        """
        [gymact]
        environment = "sregym"

        [[capability]]
        name = "observe_cluster_state"
        consequence = "READ"
        reason = "test fixture"
        """,
        encoding="utf-8",
    )
    gate = CapabilityGate.from_toml(manifest)
    assert gate.allowed_names == frozenset({"observe_cluster_state"})
    gate.check("observe_cluster_state")
    with pytest.raises(CapabilityRefused):
        gate.check("run_kubectl")


def test_empty_manifest_refuses_at_load_time(tmp_path) -> None:
    """A manifest declaring zero capabilities is a configuration defect, not
    silently treated as 'allow everything'."""
    manifest = tmp_path / "empty.toml"
    manifest.write_text('[gymact]\nenvironment = "sregym"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="EMPTY_CAPABILITY_MANIFEST"):
        CapabilityGate.from_toml(manifest)


def test_missing_manifest_file_raises_file_not_found(tmp_path) -> None:
    missing = tmp_path / "does_not_exist.toml"
    with pytest.raises(FileNotFoundError):
        CapabilityGate.from_toml(missing)


# ---------------------------------------------------------------------------
# Real gymact.gyms.sregym.Capability objects, checked against the gate.
# ---------------------------------------------------------------------------

gymact = pytest.importorskip(
    "gymact",
    reason="real external ~/gymact package not importable in this environment",
)
from gymact.gyms.sregym import SREGYM_CAPABILITIES  # noqa: E402


def test_real_sregym_capabilities_are_all_permitted() -> None:
    """Every real `SREGYM_CAPABILITIES` entry (re-verified 2026-08-12: 14,
    directly from `~/gymact/src/gymact/gyms/sregym.py` -- the original 5 plus
    9 observability-read additions upstream in gymact, see
    `gymact_capabilities.toml`'s header) is permitted by the shipped manifest
    -- the diagnosing pipeline's tool surface is not accidentally narrower
    than what sregym actually offers."""
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    assert len(SREGYM_CAPABILITIES) == 14
    for capability in SREGYM_CAPABILITIES:
        permitted = gate.guard_capability(capability)
        assert permitted is capability


def test_real_gymact_capability_object_with_unlisted_binding_is_refused() -> None:
    """Construct a real `gymact.models.Capability` object (the real class,
    not a fake) whose binding is not in the manifest -- standing in for a
    hypothetical future ground-truth-exposing sregym capability -- and
    confirm the gate refuses it by real identity of its `.binding` field,
    not by object identity with anything in `SREGYM_CAPABILITIES`."""
    from gymact.models import Capability, Consequence

    hypothetical_ground_truth_capability = Capability(
        iri="urn:gymact:sregym:capability:get_injected_fault",
        title="Read the injected fault spec (ground truth, grading-only)",
        consequence=Consequence.READ,
        binding="get_injected_fault",
    )
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    with pytest.raises(CapabilityRefused) as excinfo:
        gate.guard_capability(hypothetical_ground_truth_capability)
    assert excinfo.value.binding == "get_injected_fault"


def test_stale_entries_is_empty_against_real_sregym_capabilities() -> None:
    """Cross-check the shipped manifest's allowlist against the real,
    imported `gymact.gyms.sregym.SREGYM_CAPABILITIES` binding names. Zero
    stale entries today proves the manifest is not silently carrying a
    typo'd or dropped-upstream capability name that `from_toml` alone has no
    way to detect (a manifest is self-consistent TOML regardless of whether
    its names mean anything to the real environment)."""
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    real_names = frozenset(c.binding for c in SREGYM_CAPABILITIES)
    assert gate.stale_entries(real_names) == frozenset()


def test_stale_entries_detects_an_injected_fake_entry() -> None:
    """A manifest entry naming a capability gymact does not actually have
    (a stale/typo'd binding) must be detected by `stale_entries`, not
    silently accepted -- prove this against a real TOML file on disk, not
    the shipped manifest, so the shipped manifest itself is never mutated
    to make this test pass."""
    import tempfile
    from pathlib import Path

    real_names = frozenset(c.binding for c in SREGYM_CAPABILITIES)
    assert "get_injected_fault_TYPO_DOES_NOT_EXIST" not in real_names

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = Path(tmpdir) / "manifest_with_stale_entry.toml"
        manifest.write_text(
            """
            [gymact]
            environment = "sregym"

            [[capability]]
            name = "run_kubectl"
            consequence = "DO"
            reason = "real capability"

            [[capability]]
            name = "get_injected_fault_TYPO_DOES_NOT_EXIST"
            consequence = "READ"
            reason = "stale/typo'd entry that does not exist in real gymact"
            """,
            encoding="utf-8",
        )
        gate = CapabilityGate.from_toml(manifest)
        stale = gate.stale_entries(real_names)
        assert stale == frozenset({"get_injected_fault_TYPO_DOES_NOT_EXIST"})


# ---------------------------------------------------------------------------
# Corrupt/malformed TOML on disk -- gymact importability is irrelevant here,
# this exercises tomllib's own fail-closed behavior against a real file.
# ---------------------------------------------------------------------------


def test_syntactically_corrupt_toml_file_raises_uncaught(tmp_path) -> None:
    """A present-but-syntactically-invalid TOML file must raise
    `tomllib.TOMLDecodeError` uncaught -- `from_toml` does no try/except
    around `tomllib.load`, so a corrupt manifest fails closed exactly like a
    missing one, rather than being papered over into an implicit
    allow-everything or allow-nothing default. Real malformed file on disk,
    not assumed from reading the source."""
    import tomllib

    corrupt = tmp_path / "corrupt.toml"
    corrupt.write_text(
        """
        [gymact
        environment = "sregym"

        [[capability]]
        name = "run_kubectl"
        consequence = "DO"
        reason = "unterminated table header above breaks TOML syntax"
        """,
        encoding="utf-8",
    )
    with pytest.raises(tomllib.TOMLDecodeError):
        CapabilityGate.from_toml(corrupt)
