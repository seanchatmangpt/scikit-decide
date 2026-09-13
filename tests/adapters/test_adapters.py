"""Chicago-style tests for the optional adapter boundary.

The load-bearing property under test: a missing adapter must never lower the
standing of the self-contained core.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from autofde_lab import adapters
from autofde_lab.adapters import ADAPTERS, AdapterProbe, AdapterStatus, available, probe_all

ADAPTER_DIR = pathlib.Path(adapters.__file__).parent
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

SIBLING_PACKAGES = frozenset(
    {
        "mfw",
        "bcinr",
        "ferroplan",
        "mfact",
        "ggen",
        "openclaw",
        "wasm4pm",
        "wasm4pm_compat",
        "azure",
        "msal",
    }
)

ENV_OVERRIDES = (
    "MFW_HOME",
    "BCINR_HOME",
    "FERROPLAN_HOME",
    "MFACT_HOME",
    "GGEN_HOME",
    "OPENCLAW_HOME",
    "WASM4PM_COMPAT_HOME",
)


def test_probe_all_covers_every_registered_adapter():
    results = probe_all()
    assert set(results) == {a.name for a in ADAPTERS}
    assert len(results) == len(ADAPTERS)
    assert all(isinstance(p, AdapterProbe) for p in results.values())


def test_every_probe_records_a_non_empty_search_boundary():
    """An absence claim must carry the boundary that produced it."""
    for name, probe in probe_all().items():
        assert probe.searched, f"{name} returned a probe with no search boundary"
        assert all(isinstance(p, str) and p for p in probe.searched), name
        assert probe.detail.strip(), name


def test_probe_cannot_be_constructed_without_a_search_boundary():
    with pytest.raises(ValueError):
        AdapterProbe(status=AdapterStatus.UNAVAILABLE, detail="nope")


def test_empty_home_yields_all_unavailable_and_raises_nothing(tmp_path, monkeypatch):
    empty = tmp_path / "empty-home"
    empty.mkdir()
    monkeypatch.setenv("HOME", str(empty))
    monkeypatch.setenv("USERPROFILE", str(empty))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    for var in ENV_OVERRIDES:
        monkeypatch.setenv(var, str(empty / "nonexistent"))

    results = probe_all()  # must not raise
    assert set(results) == {a.name for a in ADAPTERS}
    for name, probe in results.items():
        assert probe.status is AdapterStatus.UNAVAILABLE, (name, probe.detail)
        assert probe.located_at is None, name
        assert probe.searched, name
    assert available() == frozenset()


def test_azure_is_always_unavailable_and_says_why():
    probe = adapters.AzureIncidentAdapter().probe()
    assert probe.status is AdapterStatus.UNAVAILABLE
    assert "deployment-time" in probe.detail
    assert probe.searched


def test_import_succeeds_in_fresh_subprocess_with_empty_home(tmp_path):
    """Mechanical proof that adapters are optional, not prerequisites."""
    empty = tmp_path / "clean-home"
    empty.mkdir()
    env = {
        "HOME": str(empty),
        "USERPROFILE": str(empty),
        "PATH": str(tmp_path / "no-bin"),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    code = (
        "import autofde_lab.adapters as a;"
        "r = a.probe_all();"
        "assert r, 'no adapters registered';"
        "assert all(p.searched for p in r.values()), 'probe without search boundary';"
        "assert all(p.status is a.AdapterStatus.UNAVAILABLE for p in r.values()), r;"
        "assert a.available() == frozenset();"
        "print('OK', len(r))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.stdout.startswith("OK")


def test_no_adapter_module_imports_a_sibling_at_module_level():
    """One property over every adapter module; offenders accumulated.

    rglob, not glob: adapters/azure/ is a subpackage, and a non-recursive glob
    would leave every file in it outside this control. Collapsed from a 20-way
    parametrize — the falsifier is identical per path, and accumulating names
    *every* offending module in one message rather than one per red item.
    """
    paths = sorted(ADAPTER_DIR.rglob("*.py"))
    assert len(paths) > 5, paths  # anti-vacuity: the glob must actually find modules
    offenders: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        bad: list[str] = []
        for node in tree.body:  # top level only
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in SIBLING_PACKAGES:
                        bad.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if node.level == 0 and root in SIBLING_PACKAGES:
                    bad.append(node.module or "")
        if bad:
            offenders.append(f"{path.relative_to(ADAPTER_DIR)} imports {bad}")
    assert not offenders, "sibling imports at module level:\n" + "\n".join(offenders)


def test_adapter_modules_do_not_use_dynamic_import_escape_hatches():
    for path in ADAPTER_DIR.rglob("*.py"):  # rglob: subpackages are covered too
        src = path.read_text()
        assert "__import__(" not in src, path.name
        assert "importlib" not in src, path.name


def test_adapters_expose_no_actuation_surface():
    """Adapters describe what exists; they do not authorize anything."""
    forbidden = ("actuate", "admit", "broker", "receipt", "execute", "run")
    for adapter in ADAPTERS:
        attrs = {a for a in dir(adapter) if not a.startswith("_")}
        assert attrs & {"probe", "name"} == {"probe", "name"} or "probe" in attrs
        for word in forbidden:
            assert not any(word in a.lower() for a in attrs), (adapter.name, word)
