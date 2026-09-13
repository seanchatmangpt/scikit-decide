# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Compile an RDF planning-domain description into real PDDL text.

This is the INPUT half of the RDF<->plan loop that ``ontology/CLAUDE.md``
names as missing ("no component in the portfolio executes a POWL plan end
to end"). That statement is about POWL *execution*; this module does not
touch execution at all -- it parses an RDF graph conforming to
``ontology/rdf-planning-domain.ttl`` (a minimal, PDDL-equivalent classical
STRIPS vocabulary: types, predicates, actions with typed
parameters/preconditions/effects, an initial state, and a goal) and
compiles it into ``domain.pddl`` / ``problem.pddl`` text closely enough to
PDDL's real grammar that the existing, unmodified
:func:`autofde_lab.fabric.pddl_engine.solve_to_plan_file` accepts the
compiled files without modification.

Scope boundary, matching ``pddl_engine.py`` and ``powl.py``: this produces
compiled PDDL text and, via the caller wiring it to ``pddl_engine``, a
*candidate plan*. It performs no admission, no receipt, no actuation, and
implements no execution semantics of its own -- it only compiles a graph
into the same PDDL text a human would have written by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import rdflib
from rdflib import Graph
from rdflib.namespace import Namespace

PD = Namespace("urn:autofde-lab:planning-domain:")


class RdfDomainError(ValueError):
    """The RDF graph does not conform to the rdf-planning-domain shape.

    Raised by name for a specific missing/malformed triple pattern, rather
    than surfacing as a bare KeyError/StopIteration, so a caller can tell a
    malformed graph from an unrelated bug.
    """


# ---------------------------------------------------------------------
# Small internal shapes mirroring the ontology's classes. These are plain
# dataclasses, not RDF resources -- the graph is fully consumed by
# `parse_domain`/`parse_problem` before compilation, so `to_pddl` never
# touches rdflib again.
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class Literal_:
    """One precondition/effect/init/goal conjunct: predicate + ordered args."""

    predicate: str
    arguments: Tuple[str, ...]
    negated: bool

    def to_pddl(self, as_variables: bool = False) -> str:
        """Render as PDDL. ``as_variables=True`` for action precondition/
        effect literals, whose arguments name the action's own ``?params``
        (so each gets a ``?`` prefix); ``False`` (default) for init/goal
        literals, whose arguments name ground problem objects."""
        prefix = "?" if as_variables else ""
        atom = f"({self.predicate}{''.join(' ' + prefix + a for a in self.arguments)})"
        return f"(not {atom})" if self.negated else atom


@dataclass(frozen=True)
class Parameter:
    name: str
    type_: Optional[str]
    index: int


@dataclass(frozen=True)
class PredicateDecl:
    name: str
    parameters: Tuple[Parameter, ...]

    def to_pddl(self) -> str:
        args = " ".join(_typed_var(p) for p in self.parameters)
        return f"({self.name}{' ' + args if args else ''})"


@dataclass(frozen=True)
class ActionDecl:
    name: str
    parameters: Tuple[Parameter, ...]
    preconditions: Tuple[Literal_, ...]
    effects: Tuple[Literal_, ...]

    def to_pddl(self) -> str:
        params = " ".join(_typed_var(p) for p in self.parameters)
        precond = _and_block([p.to_pddl(as_variables=True) for p in self.preconditions])
        effect = _and_block([e.to_pddl(as_variables=True) for e in self.effects])
        return (
            f"  (:action {self.name}\n"
            f"    :parameters ({params})\n"
            f"    :precondition {precond}\n"
            f"    :effect {effect})"
        )


@dataclass(frozen=True)
class TypeDecl:
    name: str
    supertype: Optional[str]


@dataclass(frozen=True)
class Domain:
    name: str
    types: Tuple[TypeDecl, ...]
    predicates: Tuple[PredicateDecl, ...]
    actions: Tuple[ActionDecl, ...]

    @property
    def is_typed(self) -> bool:
        return len(self.types) > 0

    def to_pddl(self) -> str:
        requirements = ":strips :typing" if self.is_typed else ":strips"
        lines = [
            f"(define (domain {self.name})",
            f"  (:requirements {requirements})",
        ]
        if self.is_typed:
            lines.append(f"  (:types {_types_block(self.types)})")
        preds = " ".join(p.to_pddl() for p in self.predicates)
        lines.append(f"  (:predicates {preds})")
        lines.extend(a.to_pddl() for a in self.actions)
        lines[-1] = lines[-1] + ")"
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class ObjectDecl:
    name: str
    type_: Optional[str]


@dataclass(frozen=True)
class Problem:
    name: str
    domain_name: str
    objects: Tuple[ObjectDecl, ...]
    init: Tuple[Literal_, ...]
    goal: Tuple[Literal_, ...]

    def to_pddl(self) -> str:
        objects = " ".join(_typed_obj(o) for o in self.objects)
        init_facts = " ".join(f.to_pddl() for f in self.init)
        goal = _and_block([g.to_pddl() for g in self.goal])
        return (
            f"(define (problem {self.name})\n"
            f"  (:domain {self.domain_name})\n"
            f"  (:objects {objects})\n"
            f"  (:init {init_facts})\n"
            f"  (:goal {goal}))\n"
        )


def _typed_var(p: Parameter) -> str:
    return f"?{p.name} - {p.type_}" if p.type_ else f"?{p.name}"


def _typed_obj(o: ObjectDecl) -> str:
    return f"{o.name} - {o.type_}" if o.type_ else o.name


def _types_block(types: Tuple[TypeDecl, ...]) -> str:
    parts = []
    for t in types:
        parts.append(f"{t.name} - {t.supertype}" if t.supertype else t.name)
    return " ".join(parts)


def _and_block(clauses: List[str]) -> str:
    if not clauses:
        return "()"
    if len(clauses) == 1:
        return clauses[0]
    return "(and " + " ".join(clauses) + ")"


# ---------------------------------------------------------------------
# RDF -> dataclass parsing
# ---------------------------------------------------------------------


def _literal_str(graph: Graph, subj, pred) -> str:
    val = graph.value(subj, pred)
    if val is None:
        raise RdfDomainError(f"{subj} is missing required {pred}")
    return str(val)


def _parse_ordered(graph: Graph, subj, list_pred, index_pred, name_pred, type_pred, type_names):
    """Parse an ordered pd:hasParameter-style list off `subj`."""
    entries = []
    for node in graph.objects(subj, list_pred):
        idx = graph.value(node, index_pred)
        idx_val = int(idx) if idx is not None else 0
        name = _literal_str(graph, node, name_pred)
        type_node = graph.value(node, type_pred)
        type_name = type_names.get(type_node) if type_node is not None else None
        entries.append((idx_val, name, type_name))
    entries.sort(key=lambda e: e[0])
    return entries


def _parse_literal_impl(graph: Graph, node, predicate: str, negated: bool) -> Literal_:
    # Each argument is its own pd:ArgumentBinding node carrying pd:argument
    # and pd:argumentIndex together, so name/index correspondence does not
    # depend on triple-insertion order in the store (mirrors pd:Parameter).
    bindings = []
    for bnode in graph.objects(node, PD.hasArgument):
        name = _literal_str(graph, bnode, PD.argument)
        idx = _literal_str(graph, bnode, PD.argumentIndex)
        bindings.append((int(idx), name))
    bindings.sort(key=lambda pair: pair[0])
    ordered = [name for _, name in bindings]
    return Literal_(predicate=predicate, arguments=tuple(ordered), negated=negated)


def _parse_literal_list(graph: Graph, subj, pred) -> Tuple[Literal_, ...]:
    out = []
    for node in graph.objects(subj, pred):
        types = set(graph.objects(node, rdflib.RDF.type))
        negated = PD.NegatedAtom in types
        predicate = _literal_str(graph, node, PD.ofPredicate)
        out.append(_parse_literal_impl(graph, node, predicate, negated))
    return tuple(out)


def parse_domain(graph: Graph, domain_iri) -> Domain:
    """Parse the ``pd:Domain`` at ``domain_iri`` into a :class:`Domain`."""
    name = _literal_str(graph, domain_iri, PD.domainName)

    type_nodes = list(graph.objects(domain_iri, PD.hasType))
    type_names = {}
    for tnode in type_nodes:
        type_names[tnode] = _literal_str(graph, tnode, PD.typeName)
    types: List[TypeDecl] = []
    for tnode in type_nodes:
        super_node = graph.value(tnode, PD.supertype)
        super_name = type_names.get(super_node) if super_node is not None else None
        types.append(TypeDecl(name=type_names[tnode], supertype=super_name))

    predicates: List[PredicateDecl] = []
    for pnode in graph.objects(domain_iri, PD.hasPredicate):
        pname = _literal_str(graph, pnode, PD.predicateName)
        params = _parse_ordered(
            graph, pnode, PD.hasParameter, PD.parameterIndex,
            PD.parameterName, PD.parameterType, type_names,
        )
        predicates.append(
            PredicateDecl(
                name=pname,
                parameters=tuple(
                    Parameter(name=n, type_=t, index=i) for i, n, t in params
                ),
            )
        )

    actions: List[ActionDecl] = []
    for anode in graph.objects(domain_iri, PD.hasAction):
        aname = _literal_str(graph, anode, PD.actionName)
        params = _parse_ordered(
            graph, anode, PD.hasParameter, PD.parameterIndex,
            PD.parameterName, PD.parameterType, type_names,
        )
        actions.append(
            ActionDecl(
                name=aname,
                parameters=tuple(
                    Parameter(name=n, type_=t, index=i) for i, n, t in params
                ),
                preconditions=_parse_literal_list(graph, anode, PD.precondition),
                effects=_parse_literal_list(graph, anode, PD.effect),
            )
        )

    return Domain(
        name=name,
        types=tuple(types),
        predicates=tuple(predicates),
        actions=tuple(actions),
    )


def parse_problem(graph: Graph, problem_iri) -> Tuple[Problem, object]:
    """Parse the ``pd:Problem`` at ``problem_iri``.

    Returns ``(Problem, domain_iri)`` -- the caller resolves and parses the
    referenced domain separately via :func:`parse_domain`, since a domain
    may be reused by several problems.
    """
    name = _literal_str(graph, problem_iri, PD.problemName)
    domain_iri = graph.value(problem_iri, PD.forDomain)
    if domain_iri is None:
        raise RdfDomainError(f"{problem_iri} is missing required pd:forDomain")
    domain_name = _literal_str(graph, domain_iri, PD.domainName)

    type_names = {}
    for tnode in graph.objects(domain_iri, PD.hasType):
        type_names[tnode] = _literal_str(graph, tnode, PD.typeName)

    objects: List[ObjectDecl] = []
    for onode in graph.objects(problem_iri, PD.hasObject):
        oname = _literal_str(graph, onode, PD.objectName)
        otype_node = graph.value(onode, PD.objectType)
        otype = type_names.get(otype_node) if otype_node is not None else None
        objects.append(ObjectDecl(name=oname, type_=otype))

    init = _parse_literal_list(graph, problem_iri, PD.init)
    goal = _parse_literal_list(graph, problem_iri, PD.goal)

    return (
        Problem(
            name=name,
            domain_name=domain_name,
            objects=tuple(objects),
            init=init,
            goal=goal,
        ),
        domain_iri,
    )


def compile_rdf_to_pddl(
    ttl_path: str, domain_iri: Optional[str] = None, problem_iri: Optional[str] = None
) -> Tuple[str, str]:
    """Parse a Turtle file conforming to ``rdf-planning-domain.ttl`` and
    compile it to ``(domain_pddl_text, problem_pddl_text)``.

    If ``domain_iri``/``problem_iri`` are not given, the graph must contain
    exactly one ``pd:Domain`` and one ``pd:Problem`` respectively (true of
    the toy single-domain/single-problem fixtures this module targets).
    """
    graph = Graph()
    graph.parse(ttl_path, format="turtle")

    if problem_iri is None:
        problems = list(graph.subjects(rdflib.RDF.type, PD.Problem))
        if len(problems) != 1:
            raise RdfDomainError(
                f"expected exactly one pd:Problem in {ttl_path}, found {len(problems)}"
            )
        problem_node = problems[0]
    else:
        problem_node = rdflib.URIRef(problem_iri)

    problem, resolved_domain_iri = parse_problem(graph, problem_node)

    if domain_iri is not None:
        resolved_domain_iri = rdflib.URIRef(domain_iri)
    domain = parse_domain(graph, resolved_domain_iri)

    return domain.to_pddl(), problem.to_pddl()


def compile_rdf_to_pddl_files(
    ttl_path: str,
    domain_pddl_path: str,
    problem_pddl_path: str,
    domain_iri: Optional[str] = None,
    problem_iri: Optional[str] = None,
) -> None:
    """Same as :func:`compile_rdf_to_pddl`, but writes the two PDDL files
    directly so the result can be handed to
    :func:`autofde_lab.fabric.pddl_engine.solve_to_plan_file` unmodified.
    """
    domain_text, problem_text = compile_rdf_to_pddl(ttl_path, domain_iri, problem_iri)
    with open(domain_pddl_path, "w", encoding="utf-8") as fh:
        fh.write(domain_text)
    with open(problem_pddl_path, "w", encoding="utf-8") as fh:
        fh.write(problem_text)
