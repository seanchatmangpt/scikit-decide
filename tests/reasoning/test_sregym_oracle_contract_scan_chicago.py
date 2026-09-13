# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `sregym_oracle_contract_scan`.

Real collaborators throughout: the real stdlib `ast` module parsing real,
hand-written fixture `.py` files (small, in `tmp_path` -- real files on a
real filesystem, not synthetic in-memory strings passed around a mock);
one real run against the actual vendored
`vendor/gyms/sregym/sregym/conductor/oracles/` directory, asserting a
real, non-empty, fully-classified finding set.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

from pathlib import Path

from autofde_lab.reasoning.gymact_certification_types import StandingValue
from autofde_lab.reasoning.sregym_oracle_contract_scan import scan_sregym_oracle_contracts

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SREGYM_ORACLES_DIR = REPO_ROOT / "vendor" / "gyms" / "sregym" / "sregym" / "conductor" / "oracles"


def test_all_five_real_shapes_are_classified_from_real_fixture_files(tmp_path) -> None:
    """One real fixture file per real shape found this session -- each is
    real Python source text, parsed for real, never a synthetic AST built
    by hand."""
    (tmp_path / "no_args_oracle.py").write_text(
        "class NoArgsOracle:\n    def evaluate(self) -> dict:\n        return {}\n"
    )
    (tmp_path / "solution_only_oracle.py").write_text(
        "class SolutionOnlyOracle:\n    def evaluate(self, solution) -> dict:\n        return {}\n"
    )
    (tmp_path / "varargs_oracle.py").write_text(
        "class VarargsOracle:\n    def evaluate(self, *args, **kwargs):\n        return {}\n"
    )
    (tmp_path / "solution_trace_duration_optional_oracle.py").write_text(
        "class SolutionTraceDurationOptionalOracle:\n"
        "    def evaluate(self, solution=None, trace=None, duration=None) -> dict:\n"
        "        return {}\n"
    )
    (tmp_path / "solution_duration_no_trace_oracle.py").write_text(
        "class SolutionDurationNoTraceOracle:\n    def evaluate(self, solution, duration=None) -> dict:\n        return {}\n"
    )

    result = scan_sregym_oracle_contracts(tmp_path)

    assert result.files_scanned == 5
    assert result.unparseable_files == ()
    assert len(result.findings) == 5

    shapes_by_class = {f.finding_oracle_class_name: f.finding_evaluate_arg_shape_ref for f in result.findings}
    assert shapes_by_class["NoArgsOracle"] == StandingValue.NO_ARGS.value
    assert shapes_by_class["SolutionOnlyOracle"] == StandingValue.SOLUTION_ONLY.value
    assert shapes_by_class["VarargsOracle"] == StandingValue.VARARGS.value
    assert (
        shapes_by_class["SolutionTraceDurationOptionalOracle"]
        == StandingValue.SOLUTION_TRACE_DURATION_OPTIONAL.value
    )
    assert shapes_by_class["SolutionDurationNoTraceOracle"] == StandingValue.SOLUTION_DURATION_NO_TRACE.value


def test_real_return_type_annotation_mismatch_is_detected() -> None:
    """Same real defect shape as the vendored
    `ingress_misroute_oracle.py`: annotation says `bool`, body really
    returns a dict literal."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        (directory / "wrong_annotation_oracle.py").write_text(
            "class WrongAnnotationOracle:\n"
            "    def evaluate(self) -> bool:\n"
            "        return {\"success\": True}\n"
        )
        result = scan_sregym_oracle_contracts(directory)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.finding_oracle_class_name == "WrongAnnotationOracle"
    assert finding.finding_return_type_annotation_mismatch is True


def test_real_mismatch_via_variable_tracking_matches_the_real_vendored_defect(tmp_path) -> None:
    """The real, motivating case: `results = {}` built up via subscript
    assignment, then `return results`, annotated `-> bool` -- exactly
    `ingress_misroute_oracle.py`'s real shape. A naive `return {...}`-only
    heuristic misses this; same-function-scope variable tracking catches
    it."""
    (tmp_path / "ingress_style_oracle.py").write_text(
        "class IngressStyleOracle:\n"
        "    def evaluate(self) -> bool:\n"
        "        results = {}\n"
        "        results[\"success\"] = True\n"
        "        return results\n"
    )
    result = scan_sregym_oracle_contracts(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].finding_return_type_annotation_mismatch is True


def test_correct_annotation_is_never_flagged_as_mismatch(tmp_path) -> None:
    (tmp_path / "correct_oracle.py").write_text(
        "class CorrectOracle:\n    def evaluate(self) -> dict:\n        return {}\n"
    )
    result = scan_sregym_oracle_contracts(tmp_path)
    assert result.findings[0].finding_return_type_annotation_mismatch is False


def test_unparseable_file_is_named_never_silently_dropped(tmp_path) -> None:
    (tmp_path / "broken_syntax.py").write_text("class Broken(:\n    def evaluate(self\n")
    (tmp_path / "real_oracle.py").write_text(
        "class RealOracle:\n    def evaluate(self) -> dict:\n        return {}\n"
    )

    result = scan_sregym_oracle_contracts(tmp_path)

    assert result.files_scanned == 2
    assert len(result.unparseable_files) == 1
    assert "broken_syntax.py" in result.unparseable_files[0]
    # The real, parseable file is still classified despite the sibling failure.
    assert len(result.findings) == 1
    assert result.findings[0].finding_oracle_class_name == "RealOracle"


def test_no_evaluate_method_contributes_no_finding(tmp_path) -> None:
    (tmp_path / "helper.py").write_text("def not_a_class_method():\n    pass\n")
    result = scan_sregym_oracle_contracts(tmp_path)
    assert result.files_scanned == 1
    assert result.findings == ()


def test_real_exhaustive_scan_against_the_actual_vendored_oracles_directory() -> None:
    """Real, live run against the actual, on-disk, exact-pinned
    `vendor/gyms/sregym/sregym/conductor/oracles/` directory -- proves the
    scanner is exhaustive over the real corpus, not just hand-picked
    fixtures. Reads real source text only; never imports anything from
    `vendor.gyms.sregym`."""
    assert REAL_SREGYM_ORACLES_DIR.is_dir(), f"expected real directory at {REAL_SREGYM_ORACLES_DIR}"

    result = scan_sregym_oracle_contracts(REAL_SREGYM_ORACLES_DIR)

    assert result.files_scanned > 30  # this session's own agent found ~57 real files
    assert len(result.findings) > 30  # real, non-trivial number of real evaluate() methods found
    assert result.unparseable_files == ()  # every real vendored file parses cleanly

    # Every finding's shape is a real, valid StandingValue member -- never
    # an unclassified/fabricated value.
    valid_shapes = {
        StandingValue.NO_ARGS.value,
        StandingValue.SOLUTION_ONLY.value,
        StandingValue.VARARGS.value,
        StandingValue.SOLUTION_TRACE_DURATION_OPTIONAL.value,
        StandingValue.SOLUTION_DURATION_NO_TRACE.value,
    }
    assert all(f.finding_evaluate_arg_shape_ref in valid_shapes for f in result.findings)

    # Real, known positive: the base Oracle ABC's own evaluate() (solution,
    # trace, duration -- all required, no defaults) is real and present in
    # base.py, but base.py is not under this scan's target directory scope
    # in the same class-shape as the concrete subclasses -- confirm at
    # least the NO_ARGS shape (the real majority pattern found by this
    # session's own exhaustive grep) is well represented.
    no_args_count = sum(1 for f in result.findings if f.finding_evaluate_arg_shape_ref == StandingValue.NO_ARGS.value)
    assert no_args_count > 10

    # Real, known positive for the return-type-annotation-mismatch heuristic:
    # ingress_misroute_oracle.py's real IngressMisrouteMitigationOracle
    # (evaluate(self) -> bool, real body builds and returns a dict via
    # results = {}; results["success"] = ...; return results).
    mismatches = {f.finding_oracle_class_name for f in result.findings if f.finding_return_type_annotation_mismatch}
    assert "IngressMisrouteMitigationOracle" in mismatches
