# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Worktree-local import redirect for ``autofde_lab.ocel.powl_replay``.

This repo's editable install (scikit-build-core's ``ScikitBuildRedirectingFinder``)
bakes an **absolute path to the main checkout** into the venv at build time, so
plain ``import autofde_lab...`` inside a git worktree silently resolves back to
the main checkout's copy of a pure-Python module, not this worktree's edited
one -- confirmed via ``autofde_lab.ocel.powl_replay.__file__`` pointing at
``/Users/sac/autofde-lab/src/...`` even with this worktree first on
``PYTHONPATH``, because the custom finder is inserted at ``sys.meta_path[0]``
and wins regardless of ``sys.path`` order.

This is an import-resolution fixup for running THIS worktree's own source
against its own tests, not a test double: it loads the real file that lives in
this worktree, from disk, via ``importlib``, and registers it under its real
module name so every ordinary ``import`` sees the real, unmodified-by-this-file
module object. No behavior of the module under test is altered or faked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_WORKTREE_SRC = Path(__file__).resolve().parents[2] / "src"
_TARGETS = [
    "autofde_lab.ocel.mcp_session",
    "autofde_lab.ocel.powl_replay",
]


def _load_worktree_module(dotted: str) -> None:
    rel = Path(*dotted.split(".")).with_suffix(".py")
    module_path = _WORKTREE_SRC / rel
    spec = importlib.util.spec_from_file_location(dotted, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = module
    spec.loader.exec_module(module)


for _dotted in _TARGETS:
    _load_worktree_module(_dotted)
