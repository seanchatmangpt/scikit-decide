#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kgc_ofmf_utils.py

KGC / OFMF utility spine: deterministic, fail-hard, receipted RDF pipelines.

Core law enforced:
    A = μ(O)  AND  hash(A) = hash(μ(O))

Non-negotiables:
- Hard deps only (missing dependency => exception)
- Deterministic canonicalization (URDNA2015 via pyld) + hashing (BLAKE3)
- SHACL gate as a hard gate
- Receipts as RDF:
    - ReceiptProof graph MUST be hash-stable (no timestamps, no run ids)
    - ReceiptMeta graph MAY contain timestamps/run ids (never included in determinism proofs)
- Two-run determinism harnesses

This file intentionally contains utilities only.
"""

from __future__ import annotations

import io
import os
import re
import sys
import json
import time
import shutil
import tempfile
import pathlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

# -----------------------------
# Exceptions (fail hard)
# -----------------------------

class OFMFError(RuntimeError):
    pass


class DependencyError(OFMFError):
    pass


class CanonicalizationError(OFMFError):
    pass


class HashingError(OFMFError):
    pass


class SHACLValidationError(OFMFError):
    pass


class ArtifactError(OFMFError):
    pass


class DeterminismError(OFMFError):
    pass


# -----------------------------
# Hard dependencies (fail hard)
# -----------------------------

def require_module(modname: str, install_hint: str = "") -> Any:
    """
    Import-or-die. No graceful degradation.
    """
    try:
        __import__(modname)
        return sys.modules[modname]
    except Exception as e:
        hint = f" Install: {install_hint}" if install_hint else ""
        raise DependencyError(f"Missing required dependency: {modname}.{hint} Error: {e}") from e


def require_executable(exe: str, install_hint: str = "") -> None:
    """
    Executable-or-die (for external engines).
    
    For automated installation, run:
        uv run python scripts/install-external-executables.py
    """
    if shutil.which(exe) is None:
        hint = f" Install: {install_hint}" if install_hint else ""
        script_hint = "\n  Or run: uv run python scripts/install-external-executables.py"
        raise DependencyError(f"Missing required executable: {exe}.{hint}{script_hint}")


# Core libs
rdflib = require_module("rdflib", "uv add rdflib")
pyld = require_module("pyld", "uv add pyld")
blake3_mod = require_module("blake3", "uv add blake3")
pyshacl = require_module("pyshacl", "uv add pyshacl")

from rdflib import Graph, Dataset, URIRef, BNode, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD, DCTERMS
jsonld = pyld.jsonld
blake3 = blake3_mod.blake3
validate_shacl = pyshacl.validate


# -----------------------------
# Namespaces / Vocabulary
# -----------------------------

KH = Namespace("https://chatmangpt.com/kgc/hooks#")
OFMF = Namespace("http://unrdf.io/ontology/ofmf#")
KGC = Namespace("http://unrdf.io/ontology/kgc#")


# -----------------------------
# Time helpers
# -----------------------------

def now_ns() -> int:
    return time.time_ns()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# -----------------------------
# File I/O (atomic where possible)
# -----------------------------

def ensure_dir(path: Union[str, Path]) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_bytes(path: Union[str, Path]) -> bytes:
    return Path(path).read_bytes()


def read_text(path: Union[str, Path], encoding: str = "utf-8") -> str:
    return Path(path).read_text(encoding=encoding)


def write_bytes(path: Union[str, Path], data: bytes) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_bytes(data)
    return p


def write_text(path: Union[str, Path], text: str, encoding: str = "utf-8") -> Path:
    return write_bytes(path, text.encode(encoding))


def write_bytes_atomic(path: Union[str, Path], data: bytes) -> Path:
    """
    Atomic write: write to tmp in same directory then replace.
    """
    dst = Path(path)
    ensure_dir(dst.parent)
    with tempfile.NamedTemporaryFile(dir=str(dst.parent), delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(dst)
    return dst


def write_text_atomic(path: Union[str, Path], text: str, encoding: str = "utf-8") -> Path:
    return write_bytes_atomic(path, text.encode(encoding))


# -----------------------------
# Hashing
# -----------------------------

_BLAKE3_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class HashBundle:
    algo: str
    hex: str
    byte_len: int


def blake3_hash_bytes(data: bytes) -> HashBundle:
    try:
        h = blake3(data).hexdigest()
    except Exception as e:
        raise HashingError(f"BLAKE3 hashing failed: {e}") from e
    if not _BLAKE3_HEX_RE.match(h):
        raise HashingError("BLAKE3 hash output unexpected (not 64 hex chars).")
    return HashBundle(algo="blake3", hex=h, byte_len=len(data))


def blake3_hex(data: bytes) -> str:
    return blake3_hash_bytes(data).hex


def blake3_file_hex(path: Union[str, Path]) -> str:
    return blake3_hex(read_bytes(path))


# -----------------------------
# RDF load/save
# -----------------------------

RDFFormat = str  # rdflib format string


def new_graph() -> Graph:
    return Graph()


def load_graph(path: Union[str, Path], *, format: RDFFormat = "turtle", base_iri: Optional[str] = None) -> Graph:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing RDF file: {p}")
    g = new_graph()
    try:
        g.parse(p.as_posix(), format=format, publicID=base_iri)
    except Exception as e:
        raise ArtifactError(f"Failed to parse RDF: {p}. Error: {e}") from e
    return g


def load_rdf(paths: Sequence[Union[str, Path]], *, format: RDFFormat = "turtle", base_iri: Optional[str] = None) -> Graph:
    g = new_graph()
    for p in paths:
        fp = Path(p)
        if not fp.exists():
            raise FileNotFoundError(f"Missing RDF file: {fp}")
        try:
            g.parse(fp.as_posix(), format=format, publicID=base_iri)
        except Exception as e:
            raise ArtifactError(f"Failed to parse RDF: {fp}. Error: {e}") from e
    return g


def graph_to_bytes(g: Union[Graph, Dataset], *, format: RDFFormat, base: Optional[str] = None) -> bytes:
    try:
        data = g.serialize(format=format, base=base)
    except Exception as e:
        raise ArtifactError(f"RDF serialization failed ({format}): {e}") from e
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


def write_graph(g: Union[Graph, Dataset], path: Union[str, Path], *, format: RDFFormat = "turtle", base: Optional[str] = None) -> Path:
    return write_bytes_atomic(path, graph_to_bytes(g, format=format, base=base))


def graph_as_dataset(g: Graph) -> Dataset:
    """
    Promote a Graph to a Dataset (default graph) so we can serialize N-Quads.
    """
    ds = Dataset()
    dg = ds.default_context.identifier
    for s, p, o in g.triples((None, None, None)):
        ds.add((s, p, o, dg))
    return ds


def dataset_from_graphs(graphs: Sequence[Graph]) -> Dataset:
    ds = Dataset()
    dg = ds.default_context.identifier
    for g in graphs:
        for s, p, o in g.triples((None, None, None)):
            ds.add((s, p, o, dg))
    return ds


# -----------------------------
# Canonicalization (URDNA2015) + canonical hashing
# -----------------------------

def canonicalize_urdna2015_from_nquads(nq_bytes: bytes) -> bytes:
    """
    Canonicalize RDF dataset N-Quads using URDNA2015 via pyld.
    Returns canonical N-Quads bytes.
    """
    try:
        nq_text = nq_bytes.decode("utf-8")
    except Exception as e:
        raise CanonicalizationError(f"N-Quads bytes not UTF-8: {e}") from e

    try:
        canon = jsonld.normalize(
            nq_text,
            {
                "algorithm": "URDNA2015",
                "format": "application/n-quads",
            },
        )
    except Exception as e:
        raise CanonicalizationError(f"URDNA2015 normalization failed: {e}") from e

    if not isinstance(canon, str):
        raise CanonicalizationError("URDNA2015 normalization returned non-string output.")
    return canon.encode("utf-8")


def to_nquads_bytes(g: Union[Graph, Dataset]) -> bytes:
    """
    Serialize to N-Quads bytes (Dataset) or promote Graph -> Dataset then N-Quads.
    """
    if isinstance(g, Dataset):
        return graph_to_bytes(g, format="nquads")
    ds = graph_as_dataset(g)
    return graph_to_bytes(ds, format="nquads")


def canonicalize_rdf_urdna2015_bytes(g: Union[Graph, Dataset]) -> bytes:
    """
    Canonicalize a graph/dataset: serialize to N-Quads, then URDNA2015 normalize.
    """
    nq = to_nquads_bytes(g)
    return canonicalize_urdna2015_from_nquads(nq)


def canonical_hash_rdf(g: Union[Graph, Dataset]) -> Tuple[bytes, HashBundle]:
    """
    Canonicalize (URDNA2015) then hash (BLAKE3).
    Returns (canonical_nquads_bytes, HashBundle).
    """
    canon = canonicalize_rdf_urdna2015_bytes(g)
    hb = blake3_hash_bytes(canon)
    return canon, hb


def emit_canonical_nquads(g: Union[Graph, Dataset], path: Union[str, Path]) -> HashBundle:
    canon, hb = canonical_hash_rdf(g)
    write_bytes_atomic(path, canon)
    return hb


# -----------------------------
# SHACL gate (hard)
# -----------------------------

@dataclass(frozen=True)
class ShaclReport:
    conforms: bool
    report_graph: Graph
    report_text: str


def shacl_gate(
    data_graph: Graph,
    shacl_graph: Graph,
    *,
    inference: str = "rdfs",
    advanced: bool = True,
    abort_on_first: bool = False,
    meta_shacl: bool = False,
    debug: bool = False,
) -> ShaclReport:
    """
    Runs SHACL validation. Engine errors => exception. Nonconformance => report returned; caller decides.
    """
    try:
        conforms, report_graph, report_text = validate_shacl(
            data_graph=data_graph,
            shacl_graph=shacl_graph,
            inference=inference,
            advanced=advanced,
            abort_on_first=abort_on_first,
            meta_shacl=meta_shacl,
            debug=debug,
        )
    except Exception as e:
        raise SHACLValidationError(f"SHACL validation execution failed: {e}") from e

    if not isinstance(report_graph, Graph):
        raise SHACLValidationError("pyshacl returned non-Graph report_graph.")
    return ShaclReport(bool(conforms), report_graph, str(report_text))


def enforce_shacl_gate(
    data_graph: Graph,
    shacl_graph: Graph,
    *,
    on_fail_write_report_ttl: Optional[Union[str, Path]] = None,
    inference: str = "rdfs",
) -> Graph:
    """
    Nonconformance => hard stop. Optionally writes report graph to disk first.
    Returns report graph if conforms.
    """
    rep = shacl_gate(data_graph, shacl_graph, inference=inference)
    if not rep.conforms:
        if on_fail_write_report_ttl is not None:
            write_graph(rep.report_graph, on_fail_write_report_ttl, format="turtle")
        snippet = rep.report_text[:8000]
        raise SHACLValidationError(f"SHACL gate failed. Report (truncated):\n{snippet}")
    return rep.report_graph


# -----------------------------
# SPARQL helpers (rdflib)
# -----------------------------

def sparql_select(g: Graph, query: str, init_bindings: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    SELECT -> list of dict rows. Hard-fail on query errors.
    """
    try:
        res = g.query(query, initBindings=init_bindings or {})
    except Exception as e:
        raise OFMFError(f"SPARQL SELECT failed: {e}") from e

    rows: List[Dict[str, Any]] = []
    for row in res:
        try:
            rows.append(row.asdict())
        except Exception:
            rows.append({str(i): v for i, v in enumerate(row)})
    return rows


def sparql_construct(g: Graph, query: str, init_bindings: Optional[Dict[str, Any]] = None) -> Graph:
    """
    CONSTRUCT -> Graph.
    """
    try:
        res = g.query(query, initBindings=init_bindings or {})
    except Exception as e:
        raise OFMFError(f"SPARQL CONSTRUCT failed: {e}") from e

    out = new_graph()
    try:
        for triple in res.graph.triples((None, None, None)):
            out.add(triple)
    except Exception as e:
        raise OFMFError(f"SPARQL CONSTRUCT result handling failed: {e}") from e
    return out


def sparql_update(g: Graph, update: str, init_bindings: Optional[Dict[str, Any]] = None) -> None:
    """
    SPARQL Update (hard-fail).
    """
    try:
        g.update(update, initBindings=init_bindings or {})
    except Exception as e:
        raise OFMFError(f"SPARQL UPDATE failed: {e}") from e


# -----------------------------
# Deltas (RDF-level representation + apply)
# -----------------------------

@dataclass(frozen=True)
class RdfDelta:
    adds: Graph
    deletes: Graph

    def stats(self) -> Dict[str, int]:
        return {"adds": len(self.adds), "deletes": len(self.deletes)}


def empty_delta() -> RdfDelta:
    return RdfDelta(adds=new_graph(), deletes=new_graph())


def apply_delta_in_place(target: Graph, delta: RdfDelta) -> None:
    """
    Apply deletes then adds.
    """
    for s, p, o in delta.deletes.triples((None, None, None)):
        target.remove((s, p, o))
    for s, p, o in delta.adds.triples((None, None, None)):
        target.add((s, p, o))


def delta_to_graph(delta: RdfDelta, ns: Namespace = KH) -> Graph:
    """
    Encode a delta as RDF (queryable).
    """
    g = new_graph()
    g.bind("kh", ns)

    dnode = BNode()
    g.add((dnode, RDF.type, ns.Delta))
    g.add((dnode, ns.addCount, Literal(len(delta.adds), datatype=XSD.integer)))
    g.add((dnode, ns.deleteCount, Literal(len(delta.deletes), datatype=XSD.integer)))

    def emit_set(set_node: BNode, triples: Iterable[Tuple[Any, Any, Any]]) -> None:
        for (s, p, o) in triples:
            t = BNode()
            g.add((set_node, ns.triple, t))
            g.add((t, ns.s, s))
            g.add((t, ns.p, p))
            g.add((t, ns.o, o))

    adds_node = BNode()
    dels_node = BNode()
    g.add((dnode, ns.adds, adds_node))
    g.add((dnode, ns.deletes, dels_node))
    emit_set(adds_node, delta.adds.triples((None, None, None)))
    emit_set(dels_node, delta.deletes.triples((None, None, None)))
    return g


# -----------------------------
# Receipts (split: Proof vs Meta)
# -----------------------------

@dataclass(frozen=True)
class ReceiptProofInfo:
    """
    Hash-stable proof payload ONLY.
    Do NOT put timestamps, cwd, run id, or any varying fields here.
    """
    did_execute: bool
    input_hash: HashBundle
    output_hash: HashBundle
    diagnostics_hash: Optional[HashBundle] = None
    hookpack_hash: Optional[HashBundle] = None
    shacl_shapes_hash: Optional[HashBundle] = None
    toolchain: Optional[Dict[str, str]] = None  # versions; should be stable within env


@dataclass(frozen=True)
class ReceiptMetaInfo:
    """
    Non-hashed run metadata. Useful for ops; never included in determinism proofs.
    """
    started_ns: int
    ended_ns: int
    duration_ns: int
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    cwd: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    hook_event_name: Optional[str] = None
    tool_name: Optional[str] = None


def toolchain_versions() -> Dict[str, str]:
    import rdflib as _rdflib
    import pyshacl as _pyshacl
    import pyld as _pyld
    import blake3 as _blake3

    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "rdflib": getattr(_rdflib, "__version__", "unknown"),
        "pyshacl": getattr(_pyshacl, "__version__", "unknown"),
        "pyld": getattr(_pyld, "__version__", "unknown"),
        "blake3": getattr(_blake3, "__version__", "unknown"),
    }


def build_receipt_proof_graph(
    *,
    receipt_iri: Optional[str],
    proof: ReceiptProofInfo,
) -> Graph:
    g = new_graph()
    g.bind("kh", KH)
    g.bind("ofmf", OFMF)
    g.bind("kgc", KGC)

    receipt = URIRef(receipt_iri) if receipt_iri else BNode()
    g.add((receipt, RDF.type, KH.ReceiptProof))
    g.add((receipt, KH.didExecute, Literal(bool(proof.did_execute), datatype=XSD.boolean)))

    def add_hashnode(pred: URIRef, hb: HashBundle) -> None:
        n = BNode()
        g.add((receipt, pred, n))
        g.add((n, RDF.type, KH.Hash))
        g.add((n, KH.algo, Literal(hb.algo)))
        g.add((n, KH.hex, Literal(hb.hex)))
        g.add((n, KH.byteLen, Literal(hb.byte_len, datatype=XSD.integer)))

    add_hashnode(KH.inputHash, proof.input_hash)
    add_hashnode(KH.outputHash, proof.output_hash)
    if proof.diagnostics_hash:
        add_hashnode(KH.diagnosticsHash, proof.diagnostics_hash)
    if proof.hookpack_hash:
        add_hashnode(KH.hookpackHash, proof.hookpack_hash)
    if proof.shacl_shapes_hash:
        add_hashnode(KH.shaclShapesHash, proof.shacl_shapes_hash)

    if proof.toolchain:
        tc = BNode()
        g.add((receipt, KH.toolchain, tc))
        for k, v in sorted(proof.toolchain.items()):
            # Use KH[k] as a compact encoding (stable by key sort)
            g.add((tc, KH[k], Literal(v)))

    return g


def build_receipt_meta_graph(
    *,
    receipt_iri: Optional[str],
    meta: ReceiptMetaInfo,
) -> Graph:
    g = new_graph()
    g.bind("kh", KH)

    receipt = URIRef(receipt_iri) if receipt_iri else BNode()
    g.add((receipt, RDF.type, KH.ReceiptMeta))

    g.add((receipt, KH.startedNs, Literal(meta.started_ns, datatype=XSD.integer)))
    g.add((receipt, KH.endedNs, Literal(meta.ended_ns, datatype=XSD.integer)))
    g.add((receipt, KH.durationNs, Literal(meta.duration_ns, datatype=XSD.integer)))

    if meta.started_at:
        g.add((receipt, KH.startedAt, Literal(meta.started_at, datatype=XSD.dateTime)))
    if meta.finished_at:
        g.add((receipt, KH.finishedAt, Literal(meta.finished_at, datatype=XSD.dateTime)))
    if meta.cwd:
        g.add((receipt, KH.cwd, Literal(meta.cwd)))
    if meta.session_id:
        g.add((receipt, KH.sessionId, Literal(meta.session_id)))
    if meta.run_id:
        g.add((receipt, KH.runId, Literal(meta.run_id)))
    if meta.hook_event_name:
        g.add((receipt, KH.hookEventName, Literal(meta.hook_event_name)))
    if meta.tool_name:
        g.add((receipt, KH.toolName, Literal(meta.tool_name)))

    return g


def write_receipt_bundle(
    *,
    out_dir: Union[str, Path],
    receipt_iri: Optional[str],
    proof: ReceiptProofInfo,
    meta: Optional[ReceiptMetaInfo] = None,
    write_canonical_nq: bool = True,
) -> Dict[str, Any]:
    """
    Writes:
      - receipt_proof.ttl (+ optional receipt_proof.canon.nq)
      - receipt_meta.ttl  (+ optional receipt_meta.canon.nq)  (if meta provided)

    Returns dict with hashes and paths. Determinism proofs MUST use proof hash only.
    """
    out = ensure_dir(out_dir)

    proof_g = build_receipt_proof_graph(receipt_iri=receipt_iri, proof=proof)
    proof_path = out / "receipt_proof.ttl"
    write_graph(proof_g, proof_path, format="turtle")

    proof_canon_path = out / "receipt_proof.canon.nq"
    proof_hb = emit_canonical_nquads(proof_g, proof_canon_path) if write_canonical_nq else canonical_hash_rdf(proof_g)[1]

    result: Dict[str, Any] = {
        "receipt_proof_path": proof_path,
        "receipt_proof_hash": proof_hb,
    }

    if meta is not None:
        meta_g = build_receipt_meta_graph(receipt_iri=receipt_iri, meta=meta)
        meta_path = out / "receipt_meta.ttl"
        write_graph(meta_g, meta_path, format="turtle")

        meta_canon_path = out / "receipt_meta.canon.nq"
        meta_hb = emit_canonical_nquads(meta_g, meta_canon_path) if write_canonical_nq else canonical_hash_rdf(meta_g)[1]

        result.update(
            {
                "receipt_meta_path": meta_path,
                "receipt_meta_hash": meta_hb,  # informational only; do NOT use for determinism proofs
            }
        )

    return result


# -----------------------------
# Determinism harnesses
# -----------------------------

@dataclass(frozen=True)
class ProofResult:
    ok: bool
    output_hash_1: HashBundle
    output_hash_2: HashBundle
    receipt_proof_hash_1: HashBundle
    receipt_proof_hash_2: HashBundle


def run_twice_and_prove(
    run_once_fn: Callable[[], Tuple[Union[Graph, Dataset], Graph, Optional[Graph]]],
    *,
    label: str = "ofmf",
) -> ProofResult:
    """
    Calls run_once_fn() twice. Each call MUST return:
      (output_payload, receipt_proof_graph, diagnostics_graph_or_None)

    Proof checks:
      - canonical hash of output_payload identical
      - canonical hash of receipt_proof_graph identical
      - diagnostics graph is hashed only if provided and desired by caller (not enforced here)

    Any mismatch => hard failure.
    """
    out1, rp1, _diag1 = run_once_fn()
    out2, rp2, _diag2 = run_once_fn()

    _, out1_hb = canonical_hash_rdf(out1)
    _, out2_hb = canonical_hash_rdf(out2)
    if out1_hb.hex != out2_hb.hex:
        raise DeterminismError(f"{label}: output nondeterminism: {out1_hb.hex} != {out2_hb.hex}")

    _, rp1_hb = canonical_hash_rdf(rp1)
    _, rp2_hb = canonical_hash_rdf(rp2)
    if rp1_hb.hex != rp2_hb.hex:
        raise DeterminismError(f"{label}: receipt_proof nondeterminism: {rp1_hb.hex} != {rp2_hb.hex}")

    return ProofResult(
        ok=True,
        output_hash_1=out1_hb,
        output_hash_2=out2_hb,
        receipt_proof_hash_1=rp1_hb,
        receipt_proof_hash_2=rp2_hb,
    )


@dataclass(frozen=True)
class RunDirArtifacts:
    root_dir: Path
    inputs_dir: Path
    out_dir: Path
    # required by contract
    deltas_ttl: Path
    diagnostics_ttl: Path
    receipt_proof_ttl: Path
    # optional
    receipt_meta_ttl: Optional[Path]
    # canonical outputs
    input_canon_nq: Path
    output_canon_nq: Path
    diagnostics_canon_nq: Path
    receipt_proof_canon_nq: Path


def runner_contract_doc() -> str:
    """
    Contract for filesystem runners used by run_twice_determinism_proof().
    """
    return """
Runner contract (filesystem):
- Input files are in:   <run_dir>/inputs/
- Output files go to:   <run_dir>/out/
- Must emit (required):
    - <run_dir>/out/deltas.ttl
    - <run_dir>/out/diagnostics.ttl
    - <run_dir>/out/receipt_proof.ttl     (hash-stable, no timestamps)
- May emit:
    - <run_dir>/out/receipt_meta.ttl      (timestamps/run metadata allowed)
- Must fail hard on missing dependencies or invalid shapes.
- Must not use randomness, time, or external state in hashed outputs.
"""


def run_twice_determinism_proof(
    *,
    runner: Callable[[Path], None],
    input_pack_files: Sequence[Union[str, Path]],
    shacl_file: Union[str, Path],
) -> Tuple[RunDirArtifacts, ReceiptProofInfo, RunDirArtifacts, ReceiptProofInfo]:
    """
    Run runner(run_dir) twice in isolated temp dirs.
    Harness:
      - copies inputs into run_dir/inputs
      - requires runner to emit standard outputs into run_dir/out
      - canonicalizes+hashes inputs and outputs
      - checks determinism across runs based on canonical hashes
    """
    input_pack_files = [Path(p) for p in input_pack_files]
    shacl_file = Path(shacl_file)

    for p in input_pack_files + [shacl_file]:
        if not p.exists():
            raise FileNotFoundError(f"Missing input: {p}")

    def prepare_run_dir() -> Path:
        d = Path(tempfile.mkdtemp(prefix="ofmf-proof-"))
        ensure_dir(d / "inputs")
        ensure_dir(d / "out")
        for p in input_pack_files:
            shutil.copy2(p, d / "inputs" / p.name)
        shutil.copy2(shacl_file, d / "inputs" / shacl_file.name)
        return d

    def expected_layout(run_dir: Path) -> RunDirArtifacts:
        inputs_dir = run_dir / "inputs"
        out_dir = run_dir / "out"
        return RunDirArtifacts(
            root_dir=run_dir,
            inputs_dir=inputs_dir,
            out_dir=out_dir,
            deltas_ttl=out_dir / "deltas.ttl",
            diagnostics_ttl=out_dir / "diagnostics.ttl",
            receipt_proof_ttl=out_dir / "receipt_proof.ttl",
            receipt_meta_ttl=(out_dir / "receipt_meta.ttl"),
            input_canon_nq=out_dir / "input.canon.nq",
            output_canon_nq=out_dir / "output.canon.nq",
            diagnostics_canon_nq=out_dir / "diagnostics.canon.nq",
            receipt_proof_canon_nq=out_dir / "receipt_proof.canon.nq",
        )

    def one_run() -> Tuple[RunDirArtifacts, ReceiptProofInfo]:
        run_dir = prepare_run_dir()
        art = expected_layout(run_dir)

        runner(run_dir)

        # required outputs
        for must in [art.deltas_ttl, art.diagnostics_ttl, art.receipt_proof_ttl]:
            if not must.exists():
                raise ArtifactError(f"Runner did not emit required artifact: {must}")

        # input hash: pack files + shapes (all in inputs dir)
        input_paths = [art.inputs_dir / p.name for p in input_pack_files] + [art.inputs_dir / shacl_file.name]
        input_g = load_rdf(input_paths, format="turtle")
        input_ds = graph_as_dataset(input_g)
        input_hb = emit_canonical_nquads(input_ds, art.input_canon_nq)

        # output payload hash: deltas + diagnostics as a dataset
        delta_g = load_graph(art.deltas_ttl, format="turtle")
        diag_g = load_graph(art.diagnostics_ttl, format="turtle")
        out_ds = dataset_from_graphs([delta_g, diag_g])
        output_hb = emit_canonical_nquads(out_ds, art.output_canon_nq)

        diagnostics_hb = emit_canonical_nquads(diag_g, art.diagnostics_canon_nq)
        receipt_proof_g = load_graph(art.receipt_proof_ttl, format="turtle")
        receipt_proof_hb = emit_canonical_nquads(receipt_proof_g, art.receipt_proof_canon_nq)

        # ReceiptProofInfo derived from what the harness computed (not from meta)
        proof = ReceiptProofInfo(
            did_execute=True,
            input_hash=input_hb,
            output_hash=output_hb,
            diagnostics_hash=diagnostics_hb,
            toolchain=toolchain_versions(),
        )

        # sanity: receipt_proof must be deterministic; we also ensure it references at least input/output hex strings
        # (strictness without guessing graph shape)
        proof_hexes = {proof.input_hash.hex, proof.output_hash.hex}
        ttl_text = read_text(art.receipt_proof_ttl)
        for hx in proof_hexes:
            if hx not in ttl_text:
                raise ArtifactError(f"receipt_proof.ttl does not contain required hash hex: {hx}")

        # receipt_proof hash is informational here; determinism check uses harness proof and receipt_proof canonical hash
        # Caller can choose to require receipt_proof_hb == something; we enforce cross-run equality below.
        _ = receipt_proof_hb

        # receipt_meta is optional
        if art.receipt_meta_ttl is not None and not art.receipt_meta_ttl.exists():
            art = RunDirArtifacts(**{**art.__dict__, "receipt_meta_ttl": None})

        return art, proof

    art1, p1 = one_run()
    art2, p2 = one_run()

    # determinism checks: input, output, diagnostics (canonical hashes)
    if p1.input_hash.hex != p2.input_hash.hex:
        raise DeterminismError(f"Input hash mismatch across runs: {p1.input_hash.hex} != {p2.input_hash.hex}")
    if p1.output_hash.hex != p2.output_hash.hex:
        raise DeterminismError(f"Output hash mismatch across runs: {p1.output_hash.hex} != {p2.output_hash.hex}")
    if p1.diagnostics_hash and p2.diagnostics_hash and p1.diagnostics_hash.hex != p2.diagnostics_hash.hex:
        raise DeterminismError(f"Diagnostics hash mismatch across runs: {p1.diagnostics_hash.hex} != {p2.diagnostics_hash.hex}")

    # receipt_proof determinism: compare canonical receipt_proof hashes
    r1 = blake3_hash_bytes(read_bytes(art1.receipt_proof_canon_nq))
    r2 = blake3_hash_bytes(read_bytes(art2.receipt_proof_canon_nq))
    if r1.hex != r2.hex:
        raise DeterminismError(f"ReceiptProof hash mismatch across runs: {r1.hex} != {r2.hex}")

    return art1, p1, art2, p2


# -----------------------------
# Assertion helpers (graph + file)
# -----------------------------

def assert_graph_has_triple(g: Graph, s: Any, p: Any, o: Any, *, msg: str = "") -> None:
    if (s, p, o) not in g:
        raise OFMFError(msg or f"Expected triple missing: {(s, p, o)}")


def assert_graph_lacks_triple(g: Graph, s: Any, p: Any, o: Any, *, msg: str = "") -> None:
    if (s, p, o) in g:
        raise OFMFError(msg or f"Unexpected triple present: {(s, p, o)}")


def assert_nonempty_graph(g: Graph, *, msg: str = "") -> None:
    if len(g) == 0:
        raise OFMFError(msg or "Expected non-empty graph")


def assert_file_contains(path: Union[str, Path], pattern: str, *, msg: str = "") -> None:
    txt = read_text(path)
    if re.search(pattern, txt) is None:
        raise OFMFError(msg or f"Expected pattern not found in {path}: {pattern}")


# -----------------------------
# Anti-lie lint (CI friendly)
# -----------------------------

ASSERTION_VERBS = [
    r"\bworks\b",
    r"\bcomplete\b",
    r"\bimplemented\b",
    r"\bdeterministic\b",
    r"\bproduction[- ]ready\b",
    r"\bintegrated\b",
    r"\bvalidated\b",
    r"\bend[- ]to[- ]end\b",
]


def lint_text_requires_receipt_hash(text: str) -> List[str]:
    """
    If text contains assertion verbs, it must also contain at least one BLAKE3 hash.
    """
    violations: List[str] = []
    if any(re.search(v, text, flags=re.IGNORECASE) for v in ASSERTION_VERBS):
        if re.search(r"\b[0-9a-f]{64}\b", text) is None:
            violations.append("Assertion language present without any BLAKE3 hash.")
    return violations


def lint_commit_message_or_pr_body(path: Union[str, Path]) -> None:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing lint input: {p}")
    text = read_text(p)
    violations = lint_text_requires_receipt_hash(text)
    if violations:
        raise OFMFError(f"Anti-lie lint failed for {p}:\n- " + "\n- ".join(violations))


# -----------------------------
# Dialect engines: strict wrappers
# -----------------------------

def owlrl_materialize_in_place(g: Graph) -> None:
    """
    OWL RL materialization using owlrl (real library).
    """
    require_module("owlrl", "uv add owlrl")
    from owlrl import DeductiveClosure, OWLRL_Semantics
    DeductiveClosure(OWLRL_Semantics).expand(g)


def shex_validate_hard(data_graph: Graph, shex_schema_text: str, focus: Optional[str] = None) -> None:
    """
    ShEx validation using pyshex (real library).
    """
    require_module("pyshex", "uv add pyshex")
    from pyshex import ShExEvaluator

    target = URIRef(focus) if focus else None
    evaluator = ShExEvaluator(rdf=data_graph, schema=shex_schema_text, focus=target, start=None)
    results = list(evaluator.evaluate())
    if not results:
        raise OFMFError("ShEx validation produced no results.")
    for r in results:
        if not getattr(r, "result", False):
            raise OFMFError(f"ShEx validation failed: {r}")


def datalog_query_pydatalog_hard(facts: Sequence[str], query: str) -> List[Tuple[Any, ...]]:
    """
    Datalog via pyDatalog (real library).
    """
    require_module("pyDatalog", "uv add pyDatalog")
    from pyDatalog import pyDatalog

    pyDatalog.clear()
    for f in facts:
        pyDatalog.load(f)
    ans = pyDatalog.ask(query)
    if ans is None:
        return []
    return list(ans.answers)


def n3_reason_with_eye_hard(
    n3_text: str = "",
    *,
    eye_exe: str = "eye",
    flags: Optional[List[str]] = None,
) -> str:
    """
    N3 reasoning via EYE (external engine).
    
    Args:
        n3_text: N3 text to pass via stdin (only used if flags is None)
        eye_exe: Path to eye executable (default: "eye")
        flags: List of command-line flags (if provided, n3_text is ignored)
    
    Returns:
        EYE output as string (N3/Turtle format)
    """
    require_executable(eye_exe, "Install EYE reasoner and ensure 'eye' is on PATH")
    args = [eye_exe]
    if flags:
        args.extend(flags)
        # When flags are provided, don't pass input via stdin
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    else:
        # If no flags, read from stdin
        args.append("--n3")
        proc = subprocess.run(
            args,
            input=n3_text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    
    if proc.returncode != 0:
        raise OFMFError(
            f"EYE failed (code {proc.returncode}). stderr:\n{proc.stderr.decode('utf-8', errors='replace')}"
        )
    return proc.stdout.decode("utf-8", errors="strict")


# -----------------------------
# Standard SPARQL snippets (common extraction)
# -----------------------------

SPARQL_EXTRACT_HOOKS = """
PREFIX kh: <https://chatmangpt.com/kgc/hooks#>
SELECT ?hook ?id ?type WHERE {
  ?hook a kh:Hook ;
        kh:hookId ?id .
  OPTIONAL { ?hook kh:hookType ?type }
}
"""

SPARQL_EXTRACT_TRIGGERS = """
PREFIX kh: <https://chatmangpt.com/kgc/hooks#>
SELECT ?hook ?trigger ?event WHERE {
  ?hook kh:trigger ?trigger .
  OPTIONAL { ?trigger kh:event ?event }
}
"""

SPARQL_EXTRACT_ACTIONS = """
PREFIX kh: <https://chatmangpt.com/kgc/hooks#>
SELECT ?hook ?action ?atype WHERE {
  ?hook kh:action ?action .
  OPTIONAL { ?action kh:actionType ?atype }
}
"""


# -----------------------------
# Event Mapping Utilities (Claude Code → Knowledge Hooks)
# -----------------------------

_CLAUDE_EVENT_MAP: Dict[str, URIRef] = {
    "SessionStart": KH.SessionStart,
    "UserPromptSubmit": KH.UserPromptSubmit,
    "PreToolUse": KH.PreToolUse,
    "PostToolUse": KH.PostToolUse,
    "PostToolUseFailure": KH.PostToolUseFailure,
    "PermissionRequest": KH.PermissionRequest,
    "Notification": KH.Notification,
    "SubagentStart": KH.SubagentStart,
    "SubagentStop": KH.SubagentStop,
    "PreCompact": KH.PreCompact,
    "Stop": KH.Stop,
    "SessionEnd": KH.SessionEnd,
    "PartnerRequestReceived": KH.PartnerRequestReceived,
}


def claude_event_to_iri(event_name: str) -> URIRef:
    """
    Maps Claude Code event name to knowledge hook event IRI.
    
    Args:
        event_name: Claude event name (e.g., "PostToolUse", "SessionStart")
    
    Returns:
        URIRef for the corresponding kh:Event individual
    
    Raises:
        OFMFError: If event_name is not recognized
    """
    event_iri = _CLAUDE_EVENT_MAP.get(event_name)
    if event_iri is None:
        raise OFMFError(f"Unknown Claude event: {event_name}. Valid events: {list(_CLAUDE_EVENT_MAP.keys())}")
    return event_iri


def select_hooks_by_event(event_iri: URIRef, pack_graph: Graph) -> List[URIRef]:
    """
    Selects hooks from a pack graph that match the given event.
    
    Args:
        event_iri: kh:Event IRI to match (e.g., KH.PostToolUse)
        pack_graph: Graph containing hook pack definitions
    
    Returns:
        List of hook URIRefs whose triggers have matching kh:event
    """
    query = """
        PREFIX kh: <https://chatmangpt.com/kgc/hooks#>
        SELECT ?hook WHERE {
            ?hook a kh:Hook ;
                  kh:trigger ?trigger .
            ?trigger kh:event ?event .
        }
    """
    results = sparql_select(pack_graph, query, init_bindings={"event": event_iri})
    return [row["hook"] for row in results if isinstance(row["hook"], URIRef)]


def validate_pack_events(pack_graph: Graph) -> List[URIRef]:
    """
    Extracts required events declared in a hook pack.
    
    Args:
        pack_graph: Graph containing hook pack definitions
    
    Returns:
        List of kh:Event IRIs that the pack requires
    """
    query = """
        PREFIX kh: <https://chatmangpt.com/kgc/hooks#>
        SELECT DISTINCT ?event WHERE {
            ?pack a kh:HookPack ;
                  kh:requiresEvent ?event .
        }
    """
    results = sparql_select(pack_graph, query)
    return [row["event"] for row in results if isinstance(row.get("event"), URIRef)]


# -----------------------------
# Minimal CLI: anti-lie lint only
# -----------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("Usage: kgc_ofmf_utils.py lint <path-to-text>", file=sys.stderr)
        return 2

    cmd = argv[0]
    if cmd == "lint":
        if len(argv) != 2:
            print("Usage: kgc_ofmf_utils.py lint <path-to-text>", file=sys.stderr)
            return 2
        lint_commit_message_or_pr_body(argv[1])
        print("OK")
        return 0

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
