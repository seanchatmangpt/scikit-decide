from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_subject():
    path = Path(__file__).parents[1] / "scripts" / "dspy_maximal.py"
    spec = importlib.util.spec_from_file_location("dspy_maximal", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_maximal_inventory_is_dependency_closed_and_unique():
    subject = load_subject()
    assert len(subject.MODULE_KINDS) == 13
    assert len(subject.OPTIMIZER_KINDS) == 16
    assert len(set(subject.MODULE_KINDS)) == len(subject.MODULE_KINDS)
    assert len(set(subject.OPTIMIZER_KINDS)) == len(subject.OPTIMIZER_KINDS)
    assert set(subject.KNOWN_UPSTREAM) <= set(subject.OPTIMIZER_KINDS)
    assert {"SignatureOptimizer", "AvatarOptimizer", "BetterTogether"} == set(
        subject.KNOWN_UPSTREAM
    )


def test_pairwise_cover_covers_every_cross_dimension_pair():
    subject = load_subject()
    dims = {
        "module": subject.MODULE_KINDS,
        "optimizer": subject.OPTIMIZER_KINDS,
        "regime": subject.TASK_REGIMES,
    }
    cover = subject.pairwise_cover(dims)
    assert len(cover) < len(subject.MODULE_KINDS) * len(subject.OPTIMIZER_KINDS) * len(
        subject.TASK_REGIMES
    )

    keys = tuple(dims)
    for left_i, left in enumerate(keys):
        for right in keys[left_i + 1 :]:
            observed = {(row[left], row[right]) for row in cover}
            expected = {(a, b) for a in dims[left] for b in dims[right]}
            assert observed == expected, (left, right, expected - observed)


def test_full_space_size_is_1040():
    subject = load_subject()
    assert (
        len(subject.MODULE_KINDS)
        * len(subject.OPTIMIZER_KINDS)
        * len(subject.TASK_REGIMES)
        == 1040
    )
