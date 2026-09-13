# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `_construct_provider`, the generic provider
constructor shared by `_BRIDGE_SCRIPT` (discovery) and `_EXECUTE_SCRIPT`
(actuation).

The defect this pins: both bridge scripts always called `provider_cls()`
zero-arg, which crashes with `TypeError: __init__() missing 1 required
positional argument: 'name'` on `gymact.gyms.vendor_benchmarks.
VendorBenchmarkProvider(self, name: str)` -- the single generic class
covering all 52 pinned vendor benchmark corpora (`VENDOR_REVISIONS`).
Confirmed live before writing this test.

The fix introspects the real constructor signature (never a per-provider-
name branch): a class needing no required argument constructs exactly as
before; a class needing one real required argument (matching its own
registered name) gets `provider_name`. This is additive, not enabling: no
`_PROVIDERS` entry or goal predicate is added for any vendor here, so
nothing becomes newly executable through `run_real_trial` as a result --
only construction itself, which any future provider wiring will need
working regardless.

Every collaborator is real: the actual `_BRIDGE_SCRIPT`/`_EXECUTE_SCRIPT`
module constants (executed as real Python, not copied), invoked via a real
subprocess in `~/gymact`'s own venv (the same interpreter the real bridges
always run under -- `gymact`'s optional extras, e.g. `cube_counter`'s `cube`
extra, are installed there, not necessarily in this repo's own venv, so
exercising provider construction anywhere else would test the wrong
environment). The real `gymact.gyms.vendor_benchmarks.VendorBenchmarkProvider`
and zero-arg provider classes. No mocks.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    GYMACT,
    GYMACT_VENV_PYTHON,
    _EXECUTE_SCRIPT,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    _BRIDGE_SCRIPT,
    _PROVIDERS,
)

pytestmark = pytest.mark.skipif(
    not Path(GYMACT_VENV_PYTHON).exists(),
    reason=f"real gymact interpreter absent at {GYMACT_VENV_PYTHON}",
)

_CHECK_TEMPLATE = """
import json

{script_text}

results = {{}}
for module_path, class_name, expected_name in {cases!r}:
    import importlib
    cls = getattr(importlib.import_module(module_path), class_name)
    try:
        instance = _construct_provider(cls, expected_name)
        results[class_name] = {{"ok": True, "name": getattr(instance, "name", None)}}
    except Exception as exc:
        results[class_name] = {{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}}
print(json.dumps(results))
"""


def _run_construction_checks(script_text: str, cases: list[tuple[str, str, str]]) -> dict:
    """Run `_construct_provider` checks for real, inside `~/gymact`'s own
    venv -- the same interpreter every real bridge invocation uses.

    The script's own `if __name__ == "__main__":` entry point is stripped
    before appending the real check code -- run via `-c`, `__name__` is
    `"__main__"` for the whole thing, so the unstripped script would try to
    execute `main()` with no real argv and crash before the check ever ran.
    Only function/class definitions execute; `main()` itself is never
    called by this test.
    """
    defs_only = script_text.split('if __name__ == "__main__":')[0]
    script = _CHECK_TEMPLATE.format(script_text=textwrap.dedent(defs_only), cases=cases)
    completed = subprocess.run(
        [str(GYMACT_VENV_PYTHON), "-c", script],
        capture_output=True, text=True, cwd=str(GYMACT), timeout=60,
    )
    assert completed.returncode == 0, (
        f"construction check subprocess failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


_ZERO_ARG_CASES = [
    ("gymact.gyms.cube_counter", "CubeCounterProvider", "cube-counter"),
    ("gymact.gyms.lock_and_key", "LockAndKeyProvider", "lock-and-key"),
    ("gymact.gyms.switchboard", "SwitchboardProvider", "switchboard"),
]
_VENDOR_CASE = [("gymact.gyms.vendor_benchmarks", "VendorBenchmarkProvider", "agentdojo")]


@pytest.mark.parametrize("script_text", [_BRIDGE_SCRIPT, _EXECUTE_SCRIPT], ids=["discovery", "actuation"])
def test_zero_arg_providers_still_construct(script_text: str) -> None:
    """Every currently wired provider (all zero-arg) must construct exactly
    as before -- the fix must not regress the already-ALIVE gyms."""
    results = _run_construction_checks(script_text, _ZERO_ARG_CASES)
    for case in _ZERO_ARG_CASES:
        class_name = case[1]
        assert results[class_name]["ok"], results[class_name]


@pytest.mark.parametrize("script_text", [_BRIDGE_SCRIPT, _EXECUTE_SCRIPT], ids=["discovery", "actuation"])
def test_vendor_benchmark_provider_now_constructs(script_text: str) -> None:
    """The real defect, closed: `VendorBenchmarkProvider(name: str)`
    previously crashed both bridges on `provider_cls()`; it must now
    construct correctly, carrying the real requested name."""
    results = _run_construction_checks(script_text, _VENDOR_CASE)
    result = results["VendorBenchmarkProvider"]
    assert result["ok"], result
    assert result["name"] == "agentdojo"


def test_no_provider_entry_or_goal_predicate_was_added_for_any_vendor() -> None:
    """This fix is additive-only at the construction layer. Confirms the
    real, current state: no `VendorBenchmarkProvider` vendor is reachable
    through `run_real_trial` as a side effect of this change -- `_PROVIDERS`
    names exactly the gyms genuinely migrated this session, none of which is
    a vendor benchmark. (`memory` was added later this session as its own,
    separately-designed 6th tracer bullet -- see
    `tests/domains/python/test_level4_memory_gym_chicago.py` -- not as a
    side effect of the constructor fix this test pins.)"""
    assert set(_PROVIDERS) == {
        "cube_counter", "cube_container_counter", "switchboard",
        "resource_flow", "lock_and_key", "memory",
    }
