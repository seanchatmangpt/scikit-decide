# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Worktree-local import fixup.

The shared ``.venv``'s scikit-build-core editable install hardcodes
``autofde_lab.powl.__path__`` to the *main* checkout's
``src/autofde_lab/powl`` directory (a ``MetaPathFinder`` keyed off a
source-file manifest baked in at install time), so a module added only in
this isolated worktree (``soundness_bridge.py``) is invisible to it even
with ``PYTHONPATH`` set. This prepends the worktree's own ``powl`` package
directory onto the already-resolved package's search path so new modules
added here are importable without touching the shared venv or the main
checkout.
"""

from __future__ import annotations

import os

import autofde_lab.powl as _powl_pkg

_worktree_powl_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "autofde_lab", "powl"))
if _worktree_powl_dir not in _powl_pkg.__path__:
    _powl_pkg.__path__.insert(0, _worktree_powl_dir)
