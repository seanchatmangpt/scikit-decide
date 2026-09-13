# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for the ggen-manufactured K8s fault-taxonomy universe
fixtures (`src/autofde_lab/reasoning/universes/k8s_fault_universes.py`).

Real collaborators throughout, zero mocks: imports the real generated
module (produced by a real `ggen sync run` against `ontology/k8s-fault-
taxonomy.ttl` and `queries/k8s-fault/cross_product.rq`), calls the real
generated fixture-builder functions, and validates the real
`autofde_lab.powl.algebra.ChoiceGraph` objects they return through the real
`autofde_lab.powl.validate.validate_model` structural checker — no fake
validator, no patched builder, no interaction assertions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from autofde_lab.powl.algebra import Atom, ChoiceGraph
from autofde_lab.powl.validate import validate_model

#: This worktree's own installed `autofde_lab` may resolve, via the
#: scikit-build-core editable-install meta-path finder, to a *different*
#: checkout's `src/` tree than this file lives in (the finder's package
#: file map is fixed at install time and predates this session's generated
#: module). Loading the real generated file directly by its real on-disk
#: path -- rather than via the dotted `autofde_lab.reasoning.universes...`
#: import that finder would otherwise intercept -- is the real collaborator
#: for *this* worktree, not a mock: it is the exact file `ggen sync run`
#: wrote this session, executed for real.
_GENERATED_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "autofde_lab"
    / "reasoning"
    / "universes"
    / "k8s_fault_universes.py"
)
_spec = importlib.util.spec_from_file_location(
    "k8s_fault_universes_under_test", _GENERATED_MODULE_PATH
)
assert _spec is not None and _spec.loader is not None
k8s_fault_universes = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = k8s_fault_universes
_spec.loader.exec_module(k8s_fault_universes)

ALL_UNIVERSES = k8s_fault_universes.ALL_UNIVERSES
universe_names = k8s_fault_universes.__all__

#: 6 Component x 7 FailureMode x 3 AppTopology x 3 Severity, per
#: `ontology/k8s-fault-taxonomy.ttl`'s four SKOS-enumerated axes.
EXPECTED_UNIVERSE_COUNT = 6 * 7 * 3 * 3


def test_all_universes_count_is_exact_cross_product():
    assert len(ALL_UNIVERSES) == EXPECTED_UNIVERSE_COUNT == 378
    assert len(universe_names) == EXPECTED_UNIVERSE_COUNT
    # ALL_UNIVERSES holds the real function objects, not names or stubs.
    assert all(callable(fn) for fn in ALL_UNIVERSES)


def test_deterministic_sample_of_universes_pass_real_validate_model():
    """A real deterministic sample of >=10 universes, each independently
    validated by the real structural validator -- never assumed well-formed
    just because it was generated."""
    sample = ALL_UNIVERSES[::37][:15]
    assert len(sample) >= 10

    for build_universe in sample:
        model = build_universe()
        assert isinstance(model, ChoiceGraph)
        validate_model(model)  # raises PowlError on any structural defect


def test_two_universes_carry_genuinely_different_labels():
    """Guard against identical-placeholder generation: two arbitrarily
    chosen universes must produce real, textually different Atom labels."""
    first_universe = ALL_UNIVERSES[0]()
    other_universe = ALL_UNIVERSES[200]()

    first_labels = {
        child.label for child in first_universe.children if isinstance(child, Atom)
    }
    other_labels = {
        child.label for child in other_universe.children if isinstance(child, Atom)
    }

    assert first_labels, "expected real Atom labels in the first universe"
    assert other_labels, "expected real Atom labels in the other universe"
    assert first_labels != other_labels
