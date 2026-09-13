#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OFMF Utilities
"""

from __future__ import annotations

import time
from typing import Any, Dict, NamedTuple

from rdflib import ConjunctiveGraph, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD


# ---------- Namespaces ----------
KH = Namespace("https://chatmangpt.com/kgc/hooks#")


# ---------- Exceptions ----------
class OFMFError(Exception):
    """Base exception for OFMF errors."""
    pass


class SHACLValidationError(OFMFError):
    """Raised when SHACL validation fails."""
    def __init__(self, message, report_graph, report_text):
        super().__init__(message)
        self.report_graph = report_graph
        self.report_text = report_text


# ---------- Graph Utilities ----------
def new_graph() -> Graph:
    """Create a new RDF graph."""
    return Graph()


def load_graph(path: str, format: str = "turtle") -> Graph:
    """Load an RDF graph from a file."""
    g = new_graph()
    g.parse(path, format=format)
    return g


def write_graph(g: Graph, path: str, format: str = "turtle"):
    """Write an RDF graph to a file."""
    g.serialize(destination=path, format=format)


# ---------- Time Utilities ----------
def now_ns() -> int:
    """Return current time in nanoseconds."""
    return time.time_ns()


# ---------- Event Utilities ----------
def claude_event_to_iri(event_name: str) -> URIRef:
    """Convert a Claude event name to an IRI."""
    return KH[event_name]


# ---------- Receipt Utilities ----------
class ReceiptProofInfo(NamedTuple):
    """Receipt proof information."""
    pass


class ReceiptMetaInfo(NamedTuple):
    """Receipt meta information."""
    pass


def write_receipt_bundle(
    receipt_proof_info: ReceiptProofInfo,
    receipt_meta_info: ReceiptMetaInfo,
    output_path: str
):
    """Write a receipt bundle."""
    # This is a stub.
    pass

def canonical_hash_rdf(g: Graph) -> str:
    """Return the canonical hash of an RDF graph."""
    # This is a stub.
    return ""


# ---------- Hook Utilities ----------
def select_hooks_by_event(hooks: list, event_name: str) -> list:
    """Select hooks by event name."""
    return [h for h in hooks if h.event == event_name]


# ---------- SPARQL Utilities ----------
def sparql_select(g: Graph, query: str) -> list:
    """Perform a SPARQL SELECT query."""
    return list(g.query(query))


# ---------- SHACL Utilities ----------
def shacl_gate(g: Graph, shapes_g: Graph) -> bool:
    """Perform SHACL validation."""
    # This is a stub.
    return True

def enforce_shacl_gate(g: Graph, shapes_g: Graph):
    """Enforce SHACL validation."""
    # This is a stub.
    pass
