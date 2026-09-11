from __future__ import annotations

import sys
import types
from pathlib import Path

# Root tests/conftest.py intentionally imports numpy before DSPy. After that
# repository-wide bootstrap, this focused court narrows import scope to the
# subsystem under test: the source package path is made available without
# executing autofde_lab/__init__.py and its historical planner/domain imports.
_SOURCE_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "autofde_lab"
if "autofde_lab" not in sys.modules:
    package = types.ModuleType("autofde_lab")
    package.__path__ = [str(_SOURCE_PACKAGE)]
    package.__package__ = "autofde_lab"
    sys.modules["autofde_lab"] = package
