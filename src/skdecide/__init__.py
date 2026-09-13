# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deprecated compatibility alias. Import autofde_lab directly.

Bounded compatibility window: this module contains no new implementation,
only a forwarding import, and will be removed after
LEGACY_NAMESPACE_REMOVAL_AFTER (see docs/migration/AUTOFDE_LAB_RENAME.md).
"""

import importlib
import importlib.abc
import importlib.machinery
import sys
import warnings

warnings.warn(
    "skdecide is a deprecated alias for autofde_lab and will be removed. "
    "Update `import skdecide` to `import autofde_lab`.",
    DeprecationWarning,
    stacklevel=2,
)

_LEGACY = __name__
_TARGET = "autofde_lab"


class _AliasLoader(importlib.abc.Loader):
    """Bind an already-imported ``autofde_lab`` module under its legacy name."""

    def create_module(self, spec):
        target = _TARGET + spec.name[len(_LEGACY) :]
        return importlib.import_module(target)

    def exec_module(self, module):  # already executed under its real name
        pass


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Resolve ``skdecide.X.Y`` to ``autofde_lab.X.Y``, at any depth.

    ``from autofde_lab import *`` above re-exports the top-level names but
    creates no submodules, so ``import skdecide.utils`` would otherwise raise
    ModuleNotFoundError. Forwarding here rather than eagerly importing each
    submodule keeps the laziness that autofde_lab/__init__.py documents: the
    agent / fabric / powl / ocel stacks are imported only if asked for.
    """

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(_LEGACY + "."):
            return None
        return importlib.machinery.ModuleSpec(fullname, _AliasLoader(), is_package=True)


if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
    # Must precede the default PathFinder. Appending is not enough: once
    # sys.modules["skdecide.hub"] aliases autofde_lab.hub, PathFinder would
    # resolve "skdecide.hub.domain" against that parent's __path__ and execute
    # a *second*, independent copy of the module -- two distinct Maze classes,
    # so isinstance across the two namespaces silently fails.
    sys.meta_path.insert(0, _AliasFinder())

from autofde_lab import *  # noqa: E402,F401,F403
from autofde_lab import __version__ as __version__  # noqa: E402,F401
