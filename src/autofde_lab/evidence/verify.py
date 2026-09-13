"""Independent SHACL verification of a Level 4 witness graph against the
real PR #37 semantic constitution (`ontology/shapes/{level4,authority,
planning}.shacl.ttl`, `urn:autofde-lab:` namespace).

Modeled directly on `fabric/shacl_conformance.py`'s proven `pyshacl.validate()`
wrapper (lazy import, `ShaclDependencyMissing` typed remedy, real report
parsing) -- reused pattern, not reinvented.

Destructive-verification criterion, satisfied **by construction**, not by a
runtime `sys.modules` assertion bolted on afterward (`standalone_verifier.py`'s
weaker approach): this module imports only `rdflib`, `pyshacl`, and stdlib.
It never imports `level4_witness` at module scope either -- `main()` imports
it lazily so a caller who only wants to validate an already-projected graph
(e.g. from a `.ttl` file on disk) never pulls in System A at all. Run as
`python -m autofde_lab.evidence.verify <trial_dir>` in a fresh subprocess and
the producer modules (`hub.domain.gym_procedure.level4_crown`, `level4_ocel`,
`standalone_verifier`) are provably absent from `sys.modules` -- nothing in
this file's own import graph can reach them.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SHAPES_DIR = Path(__file__).resolve().parents[3] / "ontology" / "shapes"
SHAPE_FILES = (
    SHAPES_DIR / "level4.shacl.ttl",
    SHAPES_DIR / "authority.shacl.ttl",
    SHAPES_DIR / "planning.shacl.ttl",
)


class ShaclDependencyMissing(RuntimeError):
    """`pyshacl`/`rdflib` are not importable in this environment.

    Both are declared under the `ofmf` optional extra
    (`pyproject.toml`'s `[project.optional-dependencies].ofmf`) --
    install with `uv sync --extra ofmf` to enable real SHACL verification.
    """


@dataclass(frozen=True)
class Level4VerificationResult:
    """Typed conformance evidence -- never a bare boolean.

    `conforms` is `None` (not `False`) when the check could not be run at
    all (missing shapes, missing engine), per `absence-is-not-evidence.md`.
    """

    conforms: bool | None
    report_text: str
    violations: tuple[str, ...]
    shapes_paths: tuple[Path, ...]
    unknown_reason: str | None = None


def _load_shapes_graph():
    import rdflib

    missing = [p for p in SHAPE_FILES if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"SHACL shapes file(s) not found: {missing}")
    shapes = rdflib.Graph()
    for path in SHAPE_FILES:
        shapes.parse(path, format="turtle")
    return shapes


def verify_witness_graph(data_graph) -> Level4VerificationResult:
    """Validate an already-projected `rdflib.Graph` (e.g. from
    `level4_witness.project_trial_to_witness(...).graph`) against the real
    committed shapes. Never mutates `data_graph`."""
    try:
        shapes_graph = _load_shapes_graph()
    except FileNotFoundError as exc:
        return Level4VerificationResult(
            conforms=None,
            report_text="",
            violations=(),
            shapes_paths=SHAPE_FILES,
            unknown_reason=str(exc),
        )

    try:
        import pyshacl
    except ImportError:  # pragma: no cover - exercised only without the extra
        raise ShaclDependencyMissing(
            "pyshacl/rdflib not importable; install with `uv sync --extra ofmf` "
            "to enable real SHACL verification"
        ) from None

    validation = pyshacl.validate(
        data_graph,
        shacl_graph=shapes_graph,
        advanced=True,
        allow_warnings=False,
    )
    conforms, results_graph, report_text = validation
    return Level4VerificationResult(
        conforms=bool(conforms),
        report_text=str(report_text),
        violations=_read_violations(results_graph),
        shapes_paths=SHAPE_FILES,
    )


def _read_violations(results_graph) -> tuple[str, ...]:
    from rdflib import RDF, URIRef

    sh = lambda term: URIRef("http://www.w3.org/ns/shacl#" + term)  # noqa: E731
    return tuple(
        str(results_graph.value(result, sh("resultMessage")) or result)
        for result in results_graph.subjects(RDF.type, sh("ValidationResult"))
    )


def verify_trial(trial_dir: Path, *, repo_root: Path | None = None) -> Level4VerificationResult:
    """Project a real trial directory to a witness graph, then verify it.

    Imports `level4_witness` lazily -- see module docstring -- so callers
    that already hold a graph (`verify_witness_graph`) never need it, and
    a fresh-process CLI run's import graph is exactly what's asserted.
    """
    from autofde_lab.evidence.level4_witness import project_trial_to_witness

    projection = project_trial_to_witness(trial_dir, repo_root=repo_root)
    return verify_witness_graph(projection.graph)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m autofde_lab.evidence.verify <trial_dir>", file=sys.stderr)
        return 2
    trial_dir = Path(argv[0])
    result = verify_trial(trial_dir)
    print(f"shapes: {[str(p) for p in result.shapes_paths]}")
    if result.conforms is None:
        print(f"UNKNOWN: {result.unknown_reason}")
        return 3
    print(result.report_text)
    if result.conforms:
        print("CONFORMS")
        return 0
    print(f"VIOLATED ({len(result.violations)} violation(s))")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
