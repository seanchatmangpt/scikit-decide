"""Chicago-style tests for the Azure adapter subpackage.

Scope warning, stated up front so these results are not over-read: the Azure CLI
is not installed on the machine these tests were written on, no Azure SDK is
present, and no subscription exists. Every probe here therefore reports
UNAVAILABLE, and that is the CORRECT outcome, not a failure.

What these tests establish: the typed contracts exist, probes are total, refusals
name their missing prerequisite, and no operation returns a boolean permission.

What they do NOT establish, at any evidence level: that any Azure integration
works. Nothing here was ever exercised against Azure and, in this environment,
cannot be.

The load-bearing property: a missing adapter must never lower the standing of the
self-contained core.
"""

from __future__ import annotations

import dataclasses
import inspect
import pathlib
import subprocess
import sys

import pytest

from autofde_lab import adapters
from autofde_lab.adapters import azure as azure_pkg
from autofde_lab.adapters.azure import (
    AZURE_SURFACE_ADAPTERS,
    AzureEvidenceSink,
    AzureIdentity,
    AzureIncidentIngress,
    AzureLogicApps,
    AzureNotificationCapture,
    AzureProbe,
    AzureProbeStatus,
    AzureSentinel,
    Refusal,
    RefusalCode,
    probe_azure_surfaces,
)
from autofde_lab.adapters.base import AdapterStatus

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# (surface adapter, operation name, kwargs) — every operation in the brief.
OPERATIONS = (
    (AzureIncidentIngress(), "inject_synthetic_incident", {"correlation_id": "c1"}),
    (AzureSentinel(), "read_incident_observation", {"correlation_id": "c1"}),
    (AzureLogicApps(), "submit_candidate_action", {"correlation_id": "c1", "action_name": "isolate_host"}),
    (AzureIdentity(), "request_authority", {"correlation_id": "c1", "scope": "Incident.Write"}),
    (AzureNotificationCapture(), "capture_notification_draft", {"correlation_id": "c1", "channel": "teams", "subject": "s"}),
    (AzureEvidenceSink(), "record_execution_evidence", {"correlation_id": "c1", "described_by": "mfw"}),
    (AzureSentinel(), "read_postcondition", {"correlation_id": "c1", "predicate": "host_isolated"}),
)


def _empty_environment(tmp_path, monkeypatch) -> None:
    empty = tmp_path / "empty-home"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(empty))
    monkeypatch.setenv("USERPROFILE", str(empty))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    for var in ("AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)


# --------------------------------------------------------------------------
# The existing control must keep holding.
# --------------------------------------------------------------------------


def test_existing_azure_adapter_behaviour_is_preserved_by_the_package_move():
    """The module became a package; the registered adapter is unchanged."""
    probe = adapters.AzureIncidentAdapter().probe()
    assert probe.status is AdapterStatus.UNAVAILABLE
    assert "deployment-time" in probe.detail
    assert probe.searched


def test_surface_adapters_are_not_registered_in_the_core_adapter_tuple():
    """Additive only: the new surfaces cannot move probe_all()/available()."""
    registered = {a.name for a in adapters.ADAPTERS}
    assert registered & {a.name for a in AZURE_SURFACE_ADAPTERS} == set()
    assert "azure" in registered


# --------------------------------------------------------------------------
# Probes: total, boundary-carrying, UNAVAILABLE under an empty environment.
# --------------------------------------------------------------------------


def test_every_azure_surface_probe_records_a_non_empty_boundary():
    for name, probe in probe_azure_surfaces().items():
        assert isinstance(probe, AzureProbe), name
        assert probe.searched, name
        assert probe.surfaces_searched, name
        assert probe.methods_used, name
        assert probe.evidence, name
        assert probe.revision, name
        assert probe.detail.strip(), name


def test_probe_states_a_method_not_merely_a_path():
    """A path existing is not compatibility: say what was actually checked."""
    for name, probe in probe_azure_surfaces().items():
        joined = " ".join(probe.methods_used).lower()
        assert "path" in joined or "environ" in joined, (name, probe.methods_used)


def test_empty_home_and_path_yields_unavailable_and_raises_nothing(tmp_path, monkeypatch):
    _empty_environment(tmp_path, monkeypatch)
    results = probe_azure_surfaces()  # must not raise
    assert set(results) == {a.name for a in AZURE_SURFACE_ADAPTERS}
    for name, probe in results.items():
        assert probe.azure_status is AzureProbeStatus.UNAVAILABLE, (name, probe.detail)
        assert probe.status is AdapterStatus.UNAVAILABLE, name
        assert probe.located_at is None, name
        assert probe.searched and probe.environment, name


def test_registered_azure_adapter_is_unavailable_under_empty_environment(tmp_path, monkeypatch):
    _empty_environment(tmp_path, monkeypatch)
    probe = adapters.AzureIncidentAdapter().probe()
    assert probe.status is AdapterStatus.UNAVAILABLE
    assert adapters.available() == frozenset()


def test_azure_probe_cannot_be_constructed_without_a_search_boundary():
    with pytest.raises(ValueError):
        AzureProbe(status=AdapterStatus.UNAVAILABLE, detail="nope")


def test_azure_probe_requires_every_boundary_field():
    """Each boundary field, blanked in turn, must be rejected. Failures accumulated."""
    cases = {
        "no-surfaces": {"surfaces_searched": ()},
        "no-methods": {"methods_used": ()},
        "no-evidence": {"evidence": ()},
    }
    full = {
        "searched": ("x",),
        "surfaces_searched": ("s",),
        "methods_used": ("m",),
        "evidence": ("e",),
    }
    accepted: list[str] = []
    for label, blank in cases.items():
        try:
            AzureProbe(status=AdapterStatus.UNAVAILABLE, detail="nope", **{**full, **blank})
        except ValueError:
            continue
        accepted.append(label)
    assert not accepted, f"AzureProbe accepted an empty boundary field: {accepted}"


def test_unknown_maps_down_to_unavailable_never_up():
    assert azure_pkg.to_adapter_status(AzureProbeStatus.UNKNOWN) is AdapterStatus.UNAVAILABLE


# --------------------------------------------------------------------------
# Operations: typed refusals, never booleans, never credentials.
# --------------------------------------------------------------------------


def test_every_operation_returns_a_typed_refusal_naming_its_prerequisite():
    """One property over every operation in OPERATIONS; failures accumulated.

    Collapsed from a 7-way parametrize per property: each param redrew the same
    falsifier, so one red item naming every offending operation carries strictly
    more information than seven red items each naming one.
    """
    # anti-vacuity: the operation table must not silently shrink.
    assert len(OPERATIONS) == 7, OPERATIONS
    offenders: list[str] = []
    for adapter, op, kwargs in OPERATIONS:
        result = getattr(adapter, op)(**kwargs)
        if not isinstance(result, Refusal):
            offenders.append(f"{op}: returned {type(result).__name__}, not Refusal")
            continue
        if not isinstance(result.code, RefusalCode):
            offenders.append(f"{op}: code is {result.code!r}, not a RefusalCode")
        if result.operation != op:
            offenders.append(f"{op}: result.operation == {result.operation!r}")
        if not result.missing_prerequisite.strip():
            offenders.append(f"{op}: empty missing_prerequisite")
        if not (result.surfaces_searched and result.methods_used):
            offenders.append(f"{op}: empty search boundary")
    assert not offenders, "typed-refusal contract violated:\n" + "\n".join(offenders)


def test_no_operation_returns_a_boolean_permission():
    offenders: list[str] = []
    for adapter, op, kwargs in OPERATIONS:
        result = getattr(adapter, op)(**kwargs)
        if isinstance(result, bool):
            offenders.append(f"{op}: returned a bare bool")
            continue
        # `granted` is None, never False: False would be a denial verdict, and
        # this repository issues no authorization verdict of any polarity.
        if result.granted is not None:
            offenders.append(f"{op}: granted == {result.granted!r}, must be None")
        for f in dataclasses.fields(result):
            if isinstance(getattr(result, f.name), bool):
                offenders.append(f"{op}: field {f.name} is a bool")
    assert not offenders, "boolean permission surfaced:\n" + "\n".join(offenders)


def test_operations_do_not_raise_under_an_empty_environment(tmp_path, monkeypatch):
    _empty_environment(tmp_path, monkeypatch)
    offenders: list[str] = []
    for adapter, op, kwargs in OPERATIONS:
        try:
            result = getattr(adapter, op)(**kwargs)
        except Exception as exc:  # noqa: BLE001 - the property under test
            offenders.append(f"{op}: raised {type(exc).__name__}: {exc}")
            continue
        if not isinstance(result, Refusal):
            offenders.append(f"{op}: returned {type(result).__name__}, not Refusal")
    assert not offenders, "empty-environment behaviour:\n" + "\n".join(offenders)


def test_request_authority_requests_and_cannot_grant():
    result = AzureIdentity().request_authority(correlation_id="c1", scope="Incident.Write")
    assert result.granted is None
    assert result.code is RefusalCode.NO_IDENTITY_PROVIDER
    assert "never" in result.detail.lower()
    assert not hasattr(result, "token")


def test_refusal_requires_a_named_missing_prerequisite():
    with pytest.raises(ValueError):
        Refusal(
            code=RefusalCode.NO_SUBSCRIPTION,
            operation="op",
            missing_prerequisite="",
            detail="d",
            surfaces_searched=("s",),
            methods_used=("m",),
        )
    with pytest.raises(ValueError):
        Refusal(
            code=RefusalCode.NO_SUBSCRIPTION,
            operation="op",
            missing_prerequisite="p",
            detail="d",
            surfaces_searched=(),
            methods_used=("m",),
        )


def test_no_result_or_detail_carries_a_bearer_credential():
    """No secret material may appear in any result or detail string."""
    banned = ("secret", "password", "bearer ", "client_secret", "sas=", "access_token")
    blobs = [p.detail + " ".join(p.evidence) + " ".join(p.environment) for p in probe_azure_surfaces().values()]
    blobs += [getattr(a, op)(**kw).detail for a, op, kw in OPERATIONS]
    for blob in blobs:
        low = blob.lower()
        for word in banned:
            assert word not in low, (word, blob)


def test_surface_adapters_expose_no_actuation_surface():
    """Describe and refuse. No admission, broker, receipt, or actuation verbs."""
    forbidden = ("actuate", "admit", "broker", "receipt")
    for adapter in AZURE_SURFACE_ADAPTERS:
        attrs = {a for a in dir(adapter) if not a.startswith("_")}
        assert "probe" in attrs
        for word in forbidden:
            assert not any(word in a.lower() for a in attrs), (adapter.name, word)


# --------------------------------------------------------------------------
# The optionality proof must survive the subpackage.
# --------------------------------------------------------------------------


def test_no_azure_sdk_is_imported_at_module_level_or_lazily(tmp_path):
    """Not just an AST check: prove the SDK is absent from sys.modules after use."""
    empty = tmp_path / "clean-home"
    empty.mkdir()
    env = {
        "HOME": str(empty),
        "USERPROFILE": str(empty),
        "PATH": str(tmp_path / "no-bin"),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    code = (
        "import sys, autofde_lab.adapters as a;"
        "from autofde_lab.adapters.azure import probe_azure_surfaces, AzureIdentity;"
        "r = probe_azure_surfaces();"
        "assert r, 'no azure surfaces';"
        "assert all(p.searched and p.methods_used for p in r.values());"
        "AzureIdentity().request_authority(correlation_id='c', scope='s');"
        "leaked = [m for m in sys.modules if m.split('.')[0] in ('azure', 'msal')];"
        "assert not leaked, leaked;"
        "core = a.probe_all();"
        "assert all(p.status is a.AdapterStatus.UNAVAILABLE for p in core.values()), core;"
        "assert a.available() == frozenset();"
        "print('OK', len(r), len(core))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=str(tmp_path)
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.stdout.startswith("OK")


def test_probe_signatures_take_no_arguments_so_they_cannot_be_pointed_at_a_tenant():
    for adapter in AZURE_SURFACE_ADAPTERS:
        params = inspect.signature(adapter.probe).parameters
        assert not params, (adapter.name, list(params))
