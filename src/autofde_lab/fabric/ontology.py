# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Capability ontology for scikit-decide, generated from the live registry.

This is deliberately **not** a hand-maintained catalog. Every capability
here is discovered at generation time from:

* ``pyproject.toml`` entry points, via
  :func:`autofde_lab.utils.get_registered_domains` /
  :func:`~autofde_lab.utils.get_registered_solvers` — the authoritative registry;
* each solver's ``get_domain_requirements()`` (``src/autofde_lab/solvers.py:85``),
  which derives the required domain characteristics from the solver's
  ``T_domain`` MRO — so applicability is *derived*, never asserted;
* an actual import attempt per capability, which is the standing evidence.

A hand-written list of capabilities that happens to sit next to real logic
would not be ontology-backed. The test consumes the emitted Turtle file, so
a capability that is registered but missing from the ontology, or present in
the ontology but no longer registered, makes the coverage assertion fail.

Standing vocabulary follows `.claude/rules/standing-law.md` and
`docs/ecosystem-standing.md`.

Note on `_load_registered_entry` (``src/autofde_lab/utils.py:94``): it swallows
exceptions and returns ``None`` with a warning. A failed load is therefore
positive ``UNSUPPORTED`` evidence, not absence — recorded as such here so a
silently-unloadable solver cannot simply vanish from the tally.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SKD = "urn:skdecide:capability:"
SKDT = "urn:skdecide:term:"

#: Standing vocabulary from `.claude/rules/standing-law.md`.
STANDING_ALIVE = "ALIVE"
STANDING_PARTIAL = "PARTIAL_ALIVE"
STANDING_BLOCKED = "BLOCKED"
STANDING_BUILD_BROKEN = "BUILD_BROKEN"
STANDING_UNKNOWN = "UNKNOWN"
STANDING_UNSUPPORTED = "UNSUPPORTED"

#: PDDL requirements the C++ backend parses but does NOT implement. Kept in
#: sync with `autofde_lab.fabric.pddl_engine.UNIMPLEMENTED_REQUIREMENTS`; encoded
#: in the ontology so the silent-wrong-answer hazard is a first-class fact
#: about the capability surface rather than a comment in one module.
PDDL_REQUIREMENT_STATUS: Dict[str, str] = {
    ":strips": STANDING_ALIVE,
    ":typing": STANDING_ALIVE,
    ":equality": STANDING_ALIVE,
    ":negative-preconditions": STANDING_ALIVE,
    ":disjunctive-preconditions": STANDING_ALIVE,
    ":existential-preconditions": STANDING_ALIVE,
    ":universal-preconditions": STANDING_ALIVE,
    ":conditional-effects": STANDING_ALIVE,
    ":fluents": STANDING_ALIVE,
    ":numeric-fluents": STANDING_ALIVE,
    ":action-costs": STANDING_ALIVE,
    ":probabilistic-effects": STANDING_ALIVE,
    # Parsed, never implemented -- these produce WRONG plans silently.
    ":derived-predicates": STANDING_UNSUPPORTED,
    ":constraints": STANDING_UNSUPPORTED,
    ":preferences": STANDING_UNSUPPORTED,
    # Hard-fails at evaluation time rather than silently.
    ":durative-actions": STANDING_UNSUPPORTED,
}


#: Kinds discovered from ``pyproject.toml`` entry points.
ENTRY_POINT_KINDS: Dict[str, str] = {
    "Domain": "autofde_lab.domains",
    "Solver": "autofde_lab.solvers",
}

#: Kinds discovered by walking a live in-process registry rather than an entry
#: point group. Widened here **before** the ontology was widened: the drift test
#: compares exactly the kinds this module declares, so a kind that is emitted but
#: not declared, or declared but not emitted, fails. Adding terms first and the
#: drift control afterwards would have produced an ontology that could go stale
#: silently, which is the one failure the generator exists to prevent.
IN_PROCESS_KINDS: Tuple[str, ...] = (
    "PowlConstruct",
    "AgentLifecyclePhase",
    "OcelLaw",
    "Adapter",
)

#: Every kind the ontology may contain.
ALL_KINDS: Tuple[str, ...] = tuple(ENTRY_POINT_KINDS) + IN_PROCESS_KINDS

#: Claim ceiling for kinds that are *vocabulary*, not runnable capability. An
#: ``ALIVE`` row for one of these says the term is declared and reachable in the
#: live package -- never that a plan was computed, executed, admitted, or
#: verified. Stated in the artifact so a downstream reader cannot over-read it.
VOCABULARY_CEILING = (
    "declared vocabulary term reachable in the live package; NOT a claim that "
    "anything was computed, executed, admitted, actuated, or verified"
)


@dataclass
class Capability:
    """One registered capability or declared term, with derived facts."""

    identifier: str
    kind: str  # one of ALL_KINDS
    entry_point: str
    standing: str
    evidence: str
    owning_module: Optional[str] = None
    extras: Optional[str] = None
    requirements: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()
    claim_ceiling: Optional[str] = None

    @property
    def iri(self) -> str:
        return f"{SKD}{self.kind.lower()}/{self.identifier}"


def _entry_points(group: str) -> Dict[str, importlib.metadata.EntryPoint]:
    try:
        entries = importlib.metadata.entry_points(group=group)
    except TypeError:  # pragma: no cover - very old importlib
        entries = importlib.metadata.entry_points().get(group, [])
    return {entry.name: entry for entry in entries}


def _probe(kind: str, name: str, entry) -> Capability:
    """Import a capability and record the outcome as standing evidence."""
    from autofde_lab import utils

    loader = (
        utils.load_registered_domain
        if kind == "Domain"
        else utils.load_registered_solver
    )
    extras = ",".join(entry.extras) if getattr(entry, "extras", None) else None

    try:
        loaded = loader(name)
    except Exception as exc:  # noqa: BLE001
        return Capability(
            identifier=name,
            kind=kind,
            entry_point=entry.value,
            standing=STANDING_UNSUPPORTED,
            evidence=f"load raised {type(exc).__name__}: {exc}",
            extras=extras,
        )

    if loaded is None:
        # utils._load_registered_entry swallowed an ImportError. This is
        # positive UNSUPPORTED evidence, not absence.
        return Capability(
            identifier=name,
            kind=kind,
            entry_point=entry.value,
            standing=STANDING_UNSUPPORTED,
            evidence="load_registered_* returned None (dependency missing)",
            extras=extras,
        )

    requirements: Tuple[str, ...] = ()
    limitations: List[str] = []
    if kind == "Solver":
        try:
            requirements = tuple(
                sorted(req.__name__ for req in loaded.get_domain_requirements())
            )
        except Exception as exc:  # noqa: BLE001
            limitations.append(f"get_domain_requirements failed: {exc}")

    return Capability(
        identifier=name,
        kind=kind,
        entry_point=entry.value,
        standing=STANDING_ALIVE,
        evidence=f"imported {loaded.__module__}.{loaded.__qualname__}",
        owning_module=loaded.__module__,
        extras=extras,
        requirements=requirements,
        limitations=tuple(limitations),
    )


def _vocabulary(kind: str, identifier: str, module: str, evidence: str) -> Capability:
    return Capability(
        identifier=identifier,
        kind=kind,
        entry_point=module,
        standing=STANDING_ALIVE,
        evidence=evidence,
        owning_module=module,
        claim_ceiling=VOCABULARY_CEILING,
    )


def collect_powl_constructs() -> List[Capability]:
    """Concrete POWL 2.0 node types, read off the live algebra module."""
    from autofde_lab.powl import algebra

    out: List[Capability] = []
    for name in sorted(vars(algebra)):
        obj = getattr(algebra, name)
        if not isinstance(obj, type) or obj is algebra.PowlNode:
            continue
        if not issubclass(obj, algebra.PowlNode):
            continue
        if obj.__module__ != algebra.__name__:
            continue
        out.append(
            _vocabulary(
                "PowlConstruct",
                name,
                algebra.__name__,
                f"PowlNode subclass defined in {algebra.__name__}",
            )
        )
    return out


def collect_agent_lifecycle() -> List[Capability]:
    """Agent lifecycle phases an occurrence log can record."""
    from autofde_lab.agent.ocel_sink import LifecyclePhase

    return [
        _vocabulary(
            "AgentLifecyclePhase",
            phase.name,
            "autofde_lab.agent.ocel_sink",
            f"LifecyclePhase member with wire value {phase.value!r}",
        )
        for phase in LifecyclePhase
    ]


def collect_ocel_laws() -> List[Capability]:
    """Named OCEL admission refusals -- the laws a projected log is judged by."""
    from autofde_lab.ocel.refusals import OcelRefusal

    return [
        _vocabulary(
            "OcelLaw",
            refusal.name,
            "autofde_lab.ocel.refusals",
            f"OcelRefusal member with wire value {refusal.value!r}",
        )
        for refusal in OcelRefusal
    ]


def collect_adapters() -> List[Capability]:
    """Declared sibling-repository adapters.

    Standing is ``UNKNOWN``, deliberately. An adapter's probe result depends on
    which sibling repositories exist on *this* host, so baking a probe outcome
    into a committed artifact would make the file machine-dependent and would
    turn a local filesystem fact into a portfolio-wide claim. What is stable and
    therefore recorded is only that the adapter is declared.
    """
    from autofde_lab import adapters

    return [
        Capability(
            identifier=adapter.name,
            kind="Adapter",
            entry_point=f"{type(adapter).__module__}.{type(adapter).__qualname__}",
            standing=STANDING_UNKNOWN,
            evidence=(
                "declared in autofde_lab.adapters.ADAPTERS; probe status is "
                "host-dependent and deliberately not baked into this artifact"
            ),
            owning_module=type(adapter).__module__,
            claim_ceiling=(
                "adapter is declared; availability, compatibility and any "
                "cross-repository consequence remain UNKNOWN from here"
            ),
        )
        for adapter in sorted(adapters.ADAPTERS, key=lambda a: a.name)
    ]


def collect_capabilities() -> List[Capability]:
    """Discover every registered capability and declared term, with standing."""
    capabilities: List[Capability] = []
    for kind, group in sorted(ENTRY_POINT_KINDS.items()):
        for name, entry in sorted(_entry_points(group).items()):
            capabilities.append(_probe(kind, name, entry))
    capabilities.extend(collect_powl_constructs())
    capabilities.extend(collect_agent_lifecycle())
    capabilities.extend(collect_ocel_laws())
    capabilities.extend(collect_adapters())
    return capabilities


def capabilities_of_kind(capabilities: List[Capability], kind: str) -> Dict[str, Capability]:
    """Index ``capabilities`` of one kind by identifier."""
    return {c.identifier: c for c in capabilities if c.kind == kind}


def parse_kinds(text: str) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
    """Read an emitted ontology back, grouped by ``skdt:`` kind.

    Deliberately independent of :func:`autofde_lab.fabric.coverage.load_ontology`,
    which knows only about ``Solver`` and ``Domain``. The drift test reads
    through here so a newly emitted kind is compared rather than ignored.
    """
    graph = parse_turtle(text)
    out: Dict[str, Dict[str, Dict[str, List[str]]]] = {kind: {} for kind in ALL_KINDS}
    for subject, predicates in graph.items():
        identifier = (predicates.get("skdt:identifier") or [None])[0]
        if identifier is None:
            continue
        for kind in ALL_KINDS:
            if f"skdt:{kind}" in predicates.get("a", []):
                out[kind][identifier] = dict(predicates, iri=[subject])
                break
    return out


def _literal(text: str) -> str:
    escaped = (
        str(text)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def emit_turtle(capabilities: List[Capability]) -> str:
    """Render the capability graph as Turtle."""
    out: List[str] = [
        f"@prefix skd: <{SKD}> .",
        f"@prefix skdt: <{SKDT}> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        "# GENERATED by autofde_lab.fabric.ontology -- do not hand-edit.",
        "# Source of truth: pyproject.toml entry points + live import probe",
        "# + Solver.get_domain_requirements() MRO derivation.",
        "",
    ]

    for capability in capabilities:
        out.append(f"<{capability.iri}> a skdt:{capability.kind} ;")
        out.append(f"    skdt:identifier {_literal(capability.identifier)} ;")
        out.append(f"    skdt:entryPoint {_literal(capability.entry_point)} ;")
        out.append(f"    skdt:standing {_literal(capability.standing)} ;")
        out.append(f"    skdt:evidence {_literal(capability.evidence)} ;")
        if capability.owning_module:
            out.append(
                f"    skdt:owningModule {_literal(capability.owning_module)} ;"
            )
        if capability.extras:
            out.append(f"    skdt:extrasMarker {_literal(capability.extras)} ;")
        for requirement in capability.requirements:
            out.append(
                f"    skdt:requiresCharacteristic <{SKD}characteristic/{requirement}> ;"
            )
        for limitation in capability.limitations:
            out.append(f"    skdt:knownLimitation {_literal(limitation)} ;")
        if capability.claim_ceiling:
            out.append(f"    skdt:claimCeiling {_literal(capability.claim_ceiling)} ;")
        out.append(
            f"    skdt:capabilityCount "
            f'"{len(capability.requirements)}"^^xsd:integer .'
        )
        out.append("")

    for requirement, status in sorted(PDDL_REQUIREMENT_STATUS.items()):
        iri = f"{SKD}pddl-requirement/{requirement.lstrip(':')}"
        out.append(f"<{iri}> a skdt:PddlRequirement ;")
        out.append(f"    skdt:identifier {_literal(requirement)} ;")
        out.append(f"    skdt:standing {_literal(status)} ;")
        if status == STANDING_UNSUPPORTED:
            out.append(
                "    skdt:knownLimitation "
                + _literal(
                    "parsed by the C++ backend but not implemented in its "
                    "semantics; planning would silently return an incorrect "
                    "plan, so autofde_lab.fabric.pddl_engine refuses it"
                )
                + " ;"
            )
        out.append(f"    rdfs:label {_literal(requirement)} .")
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Minimal reader for the subset of Turtle emitted above.
# ---------------------------------------------------------------------------


class TurtleParseError(ValueError):
    """Raised by :func:`parse_turtle` in ``strict`` mode on a malformed input."""


def parse_turtle(
    text: str, strict: bool = False
) -> Dict[str, Dict[str, List[str]]]:
    """Parse the Turtle subset this module emits.

    Deliberately a *subset* reader, not a general Turtle parser: `rdflib` is
    not a dependency of this package, and adding one to read a file we also
    write would be circular. Scope is documented rather than implied --
    it handles ``<iri> pred obj ;`` / ``.`` statements with quoted literals,
    IRIs, and ``^^`` typed literals, which is exactly what `emit_turtle`
    produces. It is not suitable for arbitrary Turtle.

    ``strict=False`` (the default) preserves the historical lossy behaviour
    byte for byte, because ``coverage.load_ontology`` depends on it. Four known
    defects live in that path, all of which ``strict=True`` fixes:

    a. A comma-separated type list (``a powl2:Model, powl2:PartialOrder``) was
       stored as the single string ``"powl2:Model, powl2:PartialOrder"``, so a
       membership test for either type failed.
    b. ``"0"^^xsd:integer`` lost its datatype, so an integer and the string
       ``"0"`` were indistinguishable.
    c. After a statement terminated with ``.``, ``subject`` was reassigned to
       itself -- a no-op -- so a stray predicate line silently attached to the
       PREVIOUS subject instead of being reported.
    d. ``@prefix`` was discarded, so prefixed names were compared as opaque
       strings rather than expanded IRIs.

    In strict mode: types are split, ``^^`` datatypes are preserved on the
    value (``"0"^^http://www.w3.org/2001/XMLSchema#integer``), prefixed names
    are expanded against the declared ``@prefix`` map, and a predicate line
    with no open subject raises :class:`TurtleParseError`.
    """
    graph: Dict[str, Dict[str, List[str]]] = {}
    subject: Optional[str] = None
    prefixes: Dict[str, str] = {}

    def expand(token: str) -> str:
        if not strict:
            return token
        if token.startswith("<") and token.endswith(">"):
            return token[1:-1]
        prefix, sep, local = token.partition(":")
        if not sep or "/" in prefix:
            return token
        if prefix not in prefixes:
            raise TurtleParseError(f"undeclared prefix {prefix!r} in {token!r}")
        return prefixes[prefix] + local

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@prefix"):
            if strict:
                body = line[len("@prefix") :].strip().rstrip(".").strip()
                name, _, iri = body.partition(" ")
                iri = iri.strip()
                if not (iri.startswith("<") and iri.endswith(">")):
                    raise TurtleParseError(f"malformed @prefix: {line!r}")
                prefixes[name.strip().rstrip(":")] = iri[1:-1]
            continue

        terminal = line.endswith(".")
        line = line.rstrip(" .;")

        if line.startswith("<") and "> a " in line:
            subject, _, remainder = line.partition("> a ")
            subject = subject.lstrip("<")
            types = graph.setdefault(subject, {}).setdefault("a", [])
            if strict:
                # (a) comma-separated type lists are several types, not one.
                types.extend(
                    expand(part.strip())
                    for part in remainder.split(",")
                    if part.strip()
                )
            else:
                types.append(remainder.strip())
            if strict and terminal:
                subject = None
            continue

        if subject is None:
            if strict:
                # (c) a stray predicate must not attach to the previous subject.
                raise TurtleParseError(
                    f"predicate line with no open subject: {line[:80]!r}"
                )
            continue

        predicate, _, obj = line.partition(" ")
        obj = obj.strip()
        if obj.startswith('"'):
            closing = obj.rfind('"')
            value = obj[1:closing].replace('\\"', '"').replace("\\n", "\n")
            tail = obj[closing + 1 :].strip()
            if strict and tail.startswith("^^"):
                # (b) keep the datatype instead of dropping it.
                value = f"{value}^^{expand(tail[2:].strip())}"
        elif obj.startswith("<"):
            value = obj.strip("<>")
        else:
            value = expand(obj)
        graph[subject].setdefault(expand(predicate) if strict else predicate, []).append(
            value
        )

        if strict and terminal:
            # (c) the block really is closed.
            subject = None

    return graph


def generate(output_path: str) -> List[Capability]:
    """Regenerate the ontology file from the live registry."""
    capabilities = collect_capabilities()
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(emit_turtle(capabilities))
    return capabilities


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "ontology/autofde-lab-capabilities.ttl"
    caps = generate(target)
    alive = sum(1 for c in caps if c.standing == STANDING_ALIVE)
    print(f"generated {target}: {len(caps)} capabilities, {alive} ALIVE")
