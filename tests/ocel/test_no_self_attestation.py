# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The OCEL validators must not know about their producer.

``autofde_lab.agent.ocel_sink`` emits logs; ``autofde_lab.ocel`` judges them. If the
judge imported the producer it could be shaped -- deliberately, or by drift --
to admit exactly what that one producer emits, which is the thing being checked
supplying the check.

Mechanically enforced, not left to convention, and shaped after
``tests/powl/test_membership.py::test_membership_module_does_not_import_the_executor``:
both the import lines and the loaded module globals are inspected, and both
assertions are guarded against a vacuous pass.
"""

import importlib
import pkgutil

import autofde_lab.ocel


def _ocel_modules():
    modules = [autofde_lab.ocel]
    for info in pkgutil.iter_modules(autofde_lab.ocel.__path__):
        modules.append(importlib.import_module(f"autofde_lab.ocel.{info.name}"))
    return modules


def test_the_ocel_package_has_modules_to_check():
    """Guard against the whole file passing because it found nothing."""
    names = {m.__name__ for m in _ocel_modules()}
    assert {"autofde_lab.ocel.log", "autofde_lab.ocel.model", "autofde_lab.ocel.refusals"} <= names


def test_no_ocel_module_imports_the_sink():
    for module in _ocel_modules():
        src = open(module.__file__).read()
        import_lines = [
            line
            for line in src.splitlines()
            if line.startswith(("import ", "from "))
            or line.lstrip().startswith(("import ", "from "))
        ]
        assert import_lines, f"{module.__name__} has no imports at all"  # not vacuous
        offending = [
            line
            for line in import_lines
            if "ocel_sink" in line or "autofde_lab.agent" in line
        ]
        assert not offending, f"{module.__name__} imports its producer: {offending}"


def test_no_loaded_ocel_module_grew_the_dependency_at_runtime():
    for module in _ocel_modules():
        names = [n for n in vars(module) if not n.startswith("__")]
        assert names, f"{module.__name__} has no globals at all"  # not vacuous
        assert not [
            n for n in names if "ocel_sink" in n or n == "agent"
        ], f"{module.__name__} grew a producer dependency"


def test_the_check_would_catch_a_real_back_edge():
    """The producer really does import the judge -- one direction, not both."""
    import autofde_lab.agent.ocel_sink as sink

    src = open(sink.__file__).read()
    assert "from autofde_lab.ocel" in src
    # and nothing under autofde_lab.ocel names the sink anywhere in its source
    for module in _ocel_modules():
        assert "ocel_sink" not in open(module.__file__).read(), module.__name__


def test_validate_is_reachable_without_importing_the_sink_at_all():
    """A fresh interpreter validating a log must never load the producer."""
    import subprocess
    import sys

    script = (
        "import sys\n"
        "from autofde_lab.ocel.log import OcelLog\n"
        "from autofde_lab.ocel.model import OcelObject\n"
        "log = OcelLog().with_objects(OcelObject('o', 'T'))"
        ".append_event('e', 'A', [('o', 'q')], timestamp_ns=1)\n"
        "log.validate(strict_qualifiers=True)\n"
        "assert 'autofde_lab.agent.ocel_sink' not in sys.modules\n"
        "print('OK')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert "OK" in out.stdout
