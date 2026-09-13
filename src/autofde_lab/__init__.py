# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from importlib.metadata import PackageNotFoundError, version

from autofde_lab import hub as hub
from autofde_lab.caching import *
from autofde_lab.core import *
from autofde_lab.domains import *
from autofde_lab.solvers import *
from autofde_lab.utils import *

try:
    __version__ = version("autofde-lab")
except PackageNotFoundError:
    # package is not installed
    pass


#: Submodules reachable as ``autofde_lab.<name>`` without an eager import.
#:
#: Lazy on purpose (PEP 562). Eager ``from autofde_lab import agent`` here would
#: pull the whole agent stack -- session, bridge, POWL executor, solvers -- into
#: every ``import autofde_lab``, including the ones that only wanted ``core``. The
#: cost lands on every consumer to save one line for a few.
_LAZY_SUBMODULES = frozenset(
    {"adapters", "agent", "fabric", "ocel", "powl"}
)


def __getattr__(name: str):
    """Import a declared submodule on first attribute access (PEP 562)."""
    if name in _LAZY_SUBMODULES:
        import importlib

        module = importlib.import_module(f"autofde_lab.{name}")
        globals()[name] = module  # cached: the import cost is paid once
        return module
    raise AttributeError(f"module 'autofde_lab' has no attribute {name!r}")


def __dir__() -> list:
    return sorted(set(globals()) | _LAZY_SUBMODULES)
