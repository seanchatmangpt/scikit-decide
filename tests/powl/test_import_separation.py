# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Anti-self-attestation: the validator must not pull in the executor.

A structural validator that shares a code path with the machinery producing or
interpreting the model attests to its own output. These tests enforce the
separation in a **fresh subprocess** — checking ``sys.modules`` inside the
already-loaded pytest process would be meaningless, because another test module
may have imported the executor first.

Why the parent package is stubbed
---------------------------------
``autofde_lab/powl/__init__.py`` is a flat re-export: it eagerly imports every
submodule, semantics included. So a naive ``import autofde_lab.powl.validate``
always drags ``autofde_lab.powl.semantics`` in *through the package* regardless of
what ``validate.py`` itself imports, and the test would be unfalsifiable. The
probe therefore installs a stub ``autofde_lab.powl`` package module (correct
``__path__``, no ``__init__`` body) before importing the submodule, so what
gets loaded is exactly the submodule's own transitive import graph.

A meta-path blocker turns a forbidden import into an immediate hard failure
rather than a post-hoc ``sys.modules`` inspection, so an import buried inside a
function body is caught too, as long as it runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_identity import PYTHON_NAMESPACE  # noqa: E402

import pytest

_NS = PYTHON_NAMESPACE  # a rename updates this one import, not four literals below
_FORBIDDEN = (f"{_NS}.powl.executor", f"{_NS}.powl.semantics")

_PROBE = '''
import importlib, importlib.util, json, os, sys, types

FORBIDDEN = {forbidden!r}
NS = {ns!r}

class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name in FORBIDDEN:
            raise AssertionError("FORBIDDEN_IMPORT:" + name)
        return None

autofde_lab = importlib.import_module(NS)

pkg_dir = os.path.join(os.path.dirname(autofde_lab.__file__), "powl")
stub = types.ModuleType(NS + ".powl")
stub.__path__ = [pkg_dir]
stub.__package__ = NS + ".powl"
sys.modules[NS + ".powl"] = stub

sys.meta_path.insert(0, _Blocker())
importlib.import_module({module!r})
print(json.dumps(sorted(m for m in sys.modules if m.startswith(NS + ".powl"))))
'''


def _loaded_powl_modules(module: str) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=module, forbidden=_FORBIDDEN, ns=_NS)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"importing {module} in isolation failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _module_exists(module: str) -> bool:
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import importlib.util as u; raise SystemExit(0 if u.find_spec({module!r}) else 1)",
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _assert_separated(module: str) -> None:
    loaded = _loaded_powl_modules(module)
    assert module in loaded
    for forbidden in _FORBIDDEN:
        assert forbidden not in loaded, (
            f"{forbidden} was pulled in by importing {module}; loaded={loaded}"
        )


def test_validate_does_not_import_executor_or_semantics():
    _assert_separated("autofde_lab.powl.validate")


def test_membership_does_not_import_executor_or_semantics():
    if not _module_exists("autofde_lab.powl.membership"):
        pytest.xfail("autofde_lab.powl.membership does not exist yet")
    _assert_separated("autofde_lab.powl.membership")


def test_probe_would_catch_a_violation():
    """The probe is falsifiable: a module that *does* import semantics fails it."""
    if not _module_exists("autofde_lab.powl.semantics"):
        pytest.xfail("autofde_lab.powl.semantics does not exist yet")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE.format(module=f"{_NS}.powl.semantics", forbidden=_FORBIDDEN, ns=_NS),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "FORBIDDEN_IMPORT:autofde_lab.powl.semantics" in proc.stderr
