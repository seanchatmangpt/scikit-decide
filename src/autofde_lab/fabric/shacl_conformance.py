# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real SHACL conformance checking for `powl.py`'s POWL v2 projection,
against `~/mfw`'s own committed shapes.

Why this exists, distinct from `powl.py::validate_powl`: `validate_powl`
hand-reimplements the constraints from `~/mfw/mfw-planner/shapes/
powl2.shacl.ttl` (3 `sh:NodeShape`s, 6 `sh:property` blocks) as Python
`if` statements. `docs/ecosystem-standing.md` names the actual defect that
caused: a pass-1 review graded S3b `ALIVE` "on vocabulary resemblance, not
on validation" -- the hand-reimplementation drifted from the real shapes
it was supposed to mirror, and nothing caught it because nothing ran the
real shapes. This module runs the real shapes, via `pyshacl` (an
independent, spec-compliant SHACL engine), against the actual committed
file -- not a second hand-written copy of it.

`pyshacl`/`rdflib` are declared only under the optional `ofmf` extra
(`pyproject.toml`), not the core package -- this module imports them
lazily, inside the function, so importing this module never hard-requires
that extra. Callers without it get a clear, named remedy, not a bare
`ImportError` traceback -- matching this repo's existing "probe honestly,
name the remedy" discipline (`adapters/base.py`'s `AdapterStatus`,
`.claude/hooks/no-hand-edit-generated.sh`).

This is deliberately NOT wired into `powl.py::parse_powl_turtle`'s
always-on decode path -- that path stays dependency-free. This is an
additional, explicit, optional conformance layer callers (chiefly
`tests/ecosystem/test_powl_roundtrip_chicago.py`) opt into.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from autofde_lab.adapters.base import resolve_home

MFW_SHAPES_PATH: Path = (
    Path(resolve_home("MFW_HOME", "~/mfw"))
    / "mfw-planner"
    / "shapes"
    / "powl2.shacl.ttl"
)


class ShaclDependencyMissing(RuntimeError):
    """`pyshacl`/`rdflib` are not importable in this environment.

    Both are declared under the `ofmf` optional extra
    (`pyproject.toml`'s `[project.optional-dependencies].ofmf`), not the
    core package -- install it with `uv sync --extra ofmf` to enable real
    SHACL conformance checking.
    """


@dataclass(frozen=True)
class ShaclConformanceResult:
    """The real, unmodified result of running `pyshacl.validate()`.

    `report_text` is `pyshacl`'s own human-readable validation report --
    quote it verbatim in any status claim about conformance, never
    paraphrase or re-derive it.
    """

    conforms: bool
    report_text: str
    violation_count: int
    shapes_path: Path


@dataclass(frozen=True)
class ShaclViolation:
    """One `sh:ValidationResult`, read out of the real results graph.

    Shaped deliberately like `gymact`'s `Deviation(index, from, to, reason)`:
    an ordinal, the two ends of the offending edge (`focus_node` /
    `value_node`), and a named reason (`source_constraint_component` plus the
    shape's own `sh:message`). Nothing here is re-derived in Python -- every
    field is lifted verbatim out of `pyshacl`'s results graph.
    """

    index: int
    focus_node: str
    result_path: str | None
    source_shape: str | None
    source_constraint_component: str
    value_node: str | None
    message: str
    severity: str


@dataclass(frozen=True)
class TypedShaclConformance:
    """Typed conformance evidence: never a bare boolean.

    `status` is one of:

    - `CONFORMS`  -- the real engine ran and reported conformance.
    - `VIOLATED`  -- the real engine ran and reported violations, which are
      carried individually in `violations`.
    - `UNKNOWN:<reason>` -- the check could **not** be computed (missing
      shapes file, missing engine). Per
      `.claude/rules/absence-is-not-evidence.md` this is neither a pass nor a
      fail, and `conforms` is `None`, not `False`.
    """

    status: str
    conforms: bool | None
    violations: tuple[ShaclViolation, ...]
    report_text: str
    shapes_path: Path
    unknown_reason: str | None = None

    @property
    def violation_count(self) -> int:
        return len(self.violations)


_SH = "http://www.w3.org/ns/shacl#"


def _read_results(results_graph) -> tuple[ShaclViolation, ...]:
    from rdflib import RDF, URIRef

    sh = lambda term: URIRef(_SH + term)  # noqa: E731
    rows = []
    for result in results_graph.subjects(RDF.type, sh("ValidationResult")):
        get = lambda term: results_graph.value(result, sh(term))  # noqa: E731
        rows.append(
            (
                str(get("focusNode")),
                None if get("resultPath") is None else str(get("resultPath")),
                None if get("sourceShape") is None else str(get("sourceShape")),
                str(get("sourceConstraintComponent")),
                None if get("value") is None else str(get("value")),
                "" if get("resultMessage") is None else str(get("resultMessage")),
                "" if get("resultSeverity") is None else str(get("resultSeverity")),
            )
        )
    rows.sort()
    return tuple(
        ShaclViolation(
            index=index,
            focus_node=focus,
            result_path=path,
            source_shape=shape,
            source_constraint_component=component,
            value_node=value,
            message=message,
            severity=severity,
        )
        for index, (focus, path, shape, component, value, message, severity) in enumerate(rows)
    )


def check_graph_shacl(data_graph, shapes_path: Path) -> TypedShaclConformance:
    """Validate an already-built `rdflib.Graph` against explicit shapes.

    Returns typed evidence. A check that could not be computed comes back
    `UNKNOWN:<reason>` with `conforms=None` -- never a silent pass and never a
    failure-by-default.
    """
    if not shapes_path.exists():
        return TypedShaclConformance(
            status="UNKNOWN:SHAPES_FILE_ABSENT",
            conforms=None,
            violations=(),
            report_text="",
            shapes_path=shapes_path,
            unknown_reason=f"shapes file not found: {shapes_path}",
        )
    try:
        import pyshacl
    except ImportError:  # pragma: no cover - exercised only without the extra
        return TypedShaclConformance(
            status="UNKNOWN:SHACL_ENGINE_ABSENT",
            conforms=None,
            violations=(),
            report_text="",
            shapes_path=shapes_path,
            unknown_reason="pyshacl/rdflib not importable; install with `uv sync --extra ofmf`",
        )

    conforms, results_graph, report_text = pyshacl.validate(
        data_graph,
        shacl_graph=shapes_path.read_text(),
        shacl_graph_format="turtle",
        advanced=True,
        allow_warnings=False,
    )
    violations = _read_results(results_graph)
    return TypedShaclConformance(
        status="CONFORMS" if conforms else "VIOLATED",
        conforms=bool(conforms),
        violations=violations,
        report_text=str(report_text),
        shapes_path=shapes_path,
    )


def check_shacl_conformance(
    turtle: str, *, shapes_path: Path | None = None
) -> ShaclConformanceResult:
    """Validate `turtle` (POWL v2 Turtle, as emitted by
    `powl.py::project_plan_to_powl`) against mfw's real committed SHACL
    shapes, using a real SHACL engine.

    Raises `FileNotFoundError` if the shapes file is absent (e.g. `~/mfw`
    not checked out) -- callers should catch this and skip with a named
    `BLOCKED:` reason, per this repo's existing convention, rather than
    treat a missing sibling checkout as a validation failure.

    Raises `ShaclDependencyMissing` if `pyshacl`/`rdflib` are not
    installed.
    """
    path = shapes_path if shapes_path is not None else MFW_SHAPES_PATH
    if not path.exists():
        raise FileNotFoundError(f"SHACL shapes file not found: {path}")

    try:
        import pyshacl
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ShaclDependencyMissing(
            "pyshacl/rdflib not importable; install with `uv sync --extra ofmf` "
            "to enable real SHACL conformance checking"
        ) from exc

    conforms, _, report_text = pyshacl.validate(
        turtle,
        shacl_graph=path.read_text(),
        data_graph_format="turtle",
        shacl_graph_format="turtle",
    )
    violation_count = report_text.count("Constraint Violation")
    return ShaclConformanceResult(
        conforms=bool(conforms),
        report_text=str(report_text),
        violation_count=violation_count,
        shapes_path=path,
    )
