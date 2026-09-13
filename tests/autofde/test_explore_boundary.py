# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""``autofde_lab.autofde`` is a leaf: nothing in the core may import it.

The dependency arrow points one way — ``autofde`` depends on
:mod:`autofde_lab.powl`, and ``autofde_lab/{powl,agent,ocel,fabric}`` must not depend
on ``autofde``. That keeps the extraction boundary real for when AutoFDE moves
to its own repository: a core module importing it would silently make the move
a breaking change.

Shape copied from ``tests/adapters/test_adapters.py``'s
``test_no_adapter_module_imports_a_sibling_at_module_level`` — module-level
imports read with :mod:`ast`, not text search.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_identity import PYTHON_NAMESPACE  # noqa: E402
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "autofde_lab"
AUTOFDE = SRC / "autofde"

#: Core packages that must never depend on autofde.
CORE_PACKAGES = ("powl", "agent", "ocel", "fabric")

CORE_MODULES = sorted(
    p
    for pkg in CORE_PACKAGES
    for p in (SRC / pkg).rglob("*.py")
    if "__pycache__" not in p.parts
)


#: Matches ``autofde`` as a whole word only. The namespace is ``autofde_lab``,
#: which *contains* the substring "autofde", so a substring test would flag
#: every core import (`autofde_lab.powl.algebra`) as an autofde dependency and
#: the boundary would be unfalsifiable. ``_`` is a word character, so
#: ``\bautofde\b`` matches the subpackage and never the underscored namespace.
#:
#: The lookahead covers the hyphenated form. ``-`` is NOT a word character, so
#: a bare ``\bautofde\b`` matches inside the project's display names
#: (``autofde-lab-fabric``, ``ontology/autofde-lab-capabilities.ttl``) and
#: reports the project's own name as a dependency on its own leaf subpackage.
#: That is a false positive on the *spelling*, not a real boundary crossing:
#: neither string is an import, and the extraction boundary this file defends
#: is about the ``autofde`` subpackage, not about the word.
_AUTOFDE_WORD = re.compile(r"\bautofde\b(?![-_]lab\b)")


def _names_autofde(dotted: str) -> bool:
    """True when a dotted import path refers to the ``autofde`` subpackage."""
    return "autofde" in dotted.split(".")


def _imported_names(tree: ast.AST) -> list[str]:
    """Every dotted name imported anywhere in the module, not only at top level."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                names.append(node.module or "")
    return names


def test_core_modules_were_actually_found():
    """Guard against a vacuous pass from a bad glob."""
    assert len(CORE_MODULES) > 10, CORE_MODULES
    assert AUTOFDE.is_dir()


def test_no_core_module_imports_autofde():
    """One property, every core module — offenders accumulated, not short-circuited.

    Collapsed from a 40-way parametrize: the falsifier is identical for every
    path, so N red items carried no more information than one red item whose
    message names *every* offending module. ``break``/first-failure would lose
    that, so the loop accumulates.
    """
    offenders: list[str] = []
    for path in CORE_MODULES:
        tree = ast.parse(path.read_text(), filename=str(path))
        bad = [n for n in _imported_names(tree) if _names_autofde(n)]
        if bad:
            offenders.append(f"{path.relative_to(SRC)} imports {bad}")
    assert not offenders, "core modules import autofde:\n" + "\n".join(offenders)


def test_the_autofde_word_pattern_still_detects_a_real_crossing():
    """Anti-vacuity for the pattern itself, not just the module glob.

    The pattern carries a lookahead exempting the project's own hyphenated
    display name. A lookahead that over-matched would make
    ``test_core_modules_do_not_reach_autofde_dynamically`` pass for every
    possible input -- green, and detecting nothing. These cases pin both
    directions explicitly.
    """
    must_match = [
        "from autofde_lab.autofde import phases",
        "importlib.import_module('autofde_lab.autofde.graph')",
        "getattr(mod, 'autofde')",
        "path = SRC / 'autofde' / 'graph.py'",
    ]
    for line in must_match:
        assert _AUTOFDE_WORD.search(line), f"pattern missed a real crossing: {line!r}"

    must_not_match = [
        "from autofde_lab.powl.algebra import Atom",
        'APP_NAME = "autofde-lab-fabric"',
        '"ontology/autofde-lab-capabilities.ttl"',
        "AUTOFDE_LAB_DATAHOME_ENVVARNAME = 'AUTOFDE_LAB_DATA'".lower(),
    ]
    for line in must_not_match:
        assert not _AUTOFDE_WORD.search(line), f"pattern false-positived: {line!r}"


def test_core_modules_do_not_reach_autofde_dynamically():
    offenders = [
        str(path.relative_to(SRC))
        for path in CORE_MODULES
        if _AUTOFDE_WORD.search(path.read_text())
    ]
    assert not offenders, f"core modules mention autofde: {offenders}"


def test_skdecide_top_level_init_does_not_import_autofde():
    tree = ast.parse((SRC / "__init__.py").read_text())
    assert not [n for n in _imported_names(tree) if _names_autofde(n)]


def test_autofde_depends_only_on_powl_within_skdecide():
    """The arrow points one way, and at exactly one core package."""
    allowed = {f"{PYTHON_NAMESPACE}.powl", f"{PYTHON_NAMESPACE}.autofde"}
    offenders: list[str] = []
    checked_any = False
    for path in sorted(AUTOFDE.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for name in _imported_names(tree):
            if name.startswith(PYTHON_NAMESPACE):
                checked_any = True
                root = ".".join(name.split(".")[:2])
                if root not in allowed:
                    offenders.append(f"{path.name} imports {name}")
    # Anti-vacuity: if a rename makes PYTHON_NAMESPACE stop matching anything,
    # this loop silently checks nothing and passes. It must find at least the
    # `autofde_lab.powl` import every autofde module is expected to have.
    assert checked_any, (
        f"no import in {AUTOFDE} starts with {PYTHON_NAMESPACE!r} -- "
        "the namespace constant is stale, or autofde no longer depends on "
        "the core at all, either of which needs investigating, not a green"
    )
    assert not offenders, offenders
