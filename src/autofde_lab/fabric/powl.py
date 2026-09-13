# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Project a computed plan into a POWL2 process model (Turtle).

A PDDL plan is a *sequence of selected transitions*. In the Chatman
ecosystem that sequence is not the deliverable -- the deliverable is the
process geometry the transitions become, expressed as POWL. The doctrine in
``~/mfw/docs/chatman-ecosystem/CHATMAN-EQUATION.md`` assigns the roles
explicitly: PDDL selects among admitted transitions; *"POWL manufactures
that transition as a child workflow."*

This module emits the same vocabulary and shape as the real committed
artifact ``~/mfw/runs/ticket-10/plan.powl.ttl`` -- ``powl2:Model`` /
``powl2:PartialOrder`` root, ``powl2:ChildBinding`` slots,
``powl2:ActivityLeaf`` steps with ``powl2:activityLabel`` and
``mfwp:planOrdinal``, and ``mfwp:ParameterBinding`` for each ground
argument -- so the output is comparable against, and validatable by, the
SHACL shapes already committed at ``~/mfw/mfw-planner/shapes/powl2.shacl.ttl``.

Digest honesty
--------------
mfw pins artifact identity with **blake3** (``mfwp:domainDigest
"blake3:..."``). The Python ``blake3`` package is not installed in this
environment, so :func:`blake3_digest` shells out to the real ``b3sum``
binary when present and otherwise **refuses** rather than substituting a
different algorithm behind a ``blake3:`` prefix. A sha256 labelled
``blake3:`` would be a forged identity that mfw's
``PLANNER_ENVIRONMENT_DRIFT`` check could never detect as wrong -- it would
simply mismatch, with a misleading reason.

Scope: this produces a candidate process model. It is not admitted, not
receipted, and not authorized to actuate anything.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from autofde_lab.fabric.models import DecisionResult

POWL2 = "https://truex.io/ontology/powl2#"
MFWP = "urn:mfw:powl-trace:"
PROV = "http://www.w3.org/ns/prov#"
XSD = "http://www.w3.org/2001/XMLSchema#"

#: POWL2 node types this projector deliberately does not model. Detected
#: explicitly so a document using one is refused by *name*, rather than
#: incidentally tripping the dangling-``childModel`` check and reporting a
#: misleading "dangling reference" -- a refusal naming the wrong cause sends
#: the reader down a false path, which is worse than a generic message.
UNSUPPORTED_NODE_TYPES: Dict[str, str] = {
    POWL2
    + "SilentLeaf": (
        "this projector emits and parses the total-order projection only; "
        "silent transitions are not modelled"
    ),
}


class DigestUnavailable(RuntimeError):
    """Raised when a real blake3 digest cannot be computed.

    Deliberately fatal rather than falling back to another hash: a wrong
    algorithm under a ``blake3:`` label is worse than no digest.
    """


def blake3_digest(path: str) -> str:
    """Return ``blake3:<hex>`` for a file, or raise :class:`DigestUnavailable`.

    Tries the ``blake3`` Python package first, then the ``b3sum`` CLI. Never
    substitutes a different algorithm.
    """
    try:
        import blake3 as _blake3  # type: ignore

        with open(path, "rb") as handle:
            return f"blake3:{_blake3.blake3(handle.read()).hexdigest()}"
    except ImportError:
        pass

    b3sum = shutil.which("b3sum")
    if b3sum is None:
        raise DigestUnavailable(
            "neither the `blake3` Python package nor the `b3sum` binary is "
            "available; refusing to emit a digest under a `blake3:` label "
            "that was computed with a different algorithm"
        )
    result = subprocess.run(
        [b3sum, "--no-names", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DigestUnavailable(
            f"b3sum failed on {path}: {result.stderr.strip()}"
        )
    return f"blake3:{result.stdout.strip()}"


def _parse_plan_line(line: str) -> tuple[str, list[str]]:
    """Split ``(name arg1 arg2)`` into ``("name", ["arg1", "arg2"])``."""
    tokens = line.strip().strip("()").split()
    if not tokens:
        return "", []
    return tokens[0], tokens[1:]


def project_plan_to_powl(
    plan_lines: Sequence[str],
    base_iri: str,
    domain_path: Optional[str] = None,
    problem_path: Optional[str] = None,
    planner_run: str = "run-autofde_lab",
    domain_iri: Optional[str] = None,
) -> str:
    """Render a total-order POWL2 model for a plan, as Turtle.

    ``plan_lines`` are VAL-format ground action lines (``(move a l1 l2)``);
    comment lines beginning with ``;`` are ignored.

    The emitted shape follows ``~/mfw/mfw-planner/src/projection/powl_rdf.rs``
    (the reference emitter) and validates against
    ``~/mfw/mfw-planner/shapes/powl2.shacl.ttl``: every ``powl2:ActivityLeaf``
    carries ``mfwp:implementsAction`` (SHACL ``minCount 1 / maxCount 1``, which
    an earlier version of this function omitted, making its output
    SHACL-invalid), the root carries ``prov:wasDerivedFrom`` pointing at the
    domain, and the total order is expressed as explicit ``powl2:precedes``
    edges between consecutive binding slots rather than left implicit in the
    child ordering.
    """
    steps = [
        _parse_plan_line(line)
        for line in plan_lines
        if line.strip() and not line.strip().startswith(";")
    ]

    plan_iri = f"{base_iri}/plan"
    out: list[str] = [
        f"@prefix powl2: <{POWL2}> .",
        f"@prefix mfwp: <{MFWP}> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]

    if domain_iri is None:
        domain_iri = f"{base_iri}/domain"

    root = [
        f"<{plan_iri}> a powl2:Model, powl2:PartialOrder ;",
        f"    powl2:derivedFrom <{base_iri}> ;",
        f"    prov:wasDerivedFrom <{domain_iri}> ;",
    ]
    if domain_path is not None:
        root.append(f'    mfwp:domainDigest "{blake3_digest(domain_path)}" ;')
    if problem_path is not None:
        root.append(f'    mfwp:problemDigest "{blake3_digest(problem_path)}" ;')
    root.append(f'    mfwp:plannerRun "{planner_run}" ;')
    root.append('    mfwp:projection "total-order" ;')
    for index in range(len(steps)):
        root.append(f"    powl2:hasChild <{plan_iri}/binding-slot/{index}> ;")
    root.append(
        f'    mfwp:activityCount "{len(steps)}"^^xsd:integer .'
    )
    out.extend(root)
    out.append("")

    for index, (name, arguments) in enumerate(steps):
        step_iri = f"{plan_iri}/step/{index}"
        out.extend(
            [
                f"<{plan_iri}/binding-slot/{index}> a powl2:ChildBinding ;",
                f'    powl2:childIndex "{index}"^^xsd:integer ;',
                f"    powl2:childModel <{step_iri}> .",
                "",
                f"<{step_iri}> a powl2:Leaf, powl2:ActivityLeaf ;",
                f'    powl2:activityLabel "{name}" ;',
                f"    mfwp:implementsAction <{base_iri}/{name}> ;",
            ]
        )
        for arg_index in range(len(arguments)):
            out.append(
                f"    mfwp:bindsParameter <{step_iri}/binding/{arg_index}> ;"
            )
        out.append(f'    mfwp:planOrdinal "{index}"^^xsd:integer .')
        out.append("")

        for arg_index, argument in enumerate(arguments):
            out.extend(
                [
                    f"<{step_iri}/binding/{arg_index}> a mfwp:ParameterBinding ;",
                    f'    mfwp:bindingIndex "{arg_index}"^^xsd:integer ;',
                    f"    mfwp:parameter <{base_iri}/{name}-p{arg_index}> ;",
                    f"    mfwp:boundObject <{base_iri}/object/{argument}> .",
                    "",
                ]
            )

    # Total order, made explicit. The previous version hardcoded
    # `mfwp:projection "total-order"` and emitted zero `powl2:precedes` edges,
    # so the declared PartialOrder carried no order relation at all. mfw's
    # emitter writes these edges between binding-slot IRIs
    # (powl_rdf.rs, `<base/binding-slot/{before}> powl2:precedes ...`).
    for index in range(len(steps) - 1):
        out.append(
            f"<{plan_iri}/binding-slot/{index}> powl2:precedes "
            f"<{plan_iri}/binding-slot/{index + 1}> ."
        )
    if len(steps) > 1:
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Strict decoder for the POWL2 Turtle subset above.
# ---------------------------------------------------------------------------
#
# Deliberately a subset parser, for the reason this module's docstring already
# gives for the writer: `rdflib` is not a dependency of this package and is not
# installed, and pulling one in to read a file we also write would be circular.
# What it accepts is exactly what `project_plan_to_powl` and mfw's
# `powl_rdf.rs` produce; anything else is REFUSED with a named reason rather
# than silently ignored, because a decoder that skips what it does not
# understand cannot be used to validate.


class PowlDecodeError(ValueError):
    """Raised when POWL2 Turtle cannot be decoded or fails validation.

    Carries a precise reason: the point of this decoder is to say *which*
    constraint failed, not that "the file is bad".
    """


# ---------------------------------------------------------------------------
# DecisionResult -> plan_lines, scoped to the classical PDDL solver family.
# ---------------------------------------------------------------------------

#: Registered domain names belonging to the classical PDDL family this
#: converter understands (``pyproject.toml``'s ``autofde_lab.domains`` entry
#: points). Any other ``DecisionRequest.domain`` is refused by name rather
#: than guessed at.
PDDL_DOMAIN_FAMILY: frozenset[str] = frozenset(
    {"PDDLDomain", "PPDDLDomain", "TPDDLDomain"}
)


class PowlProjectionUnsupported(PowlDecodeError):
    """Raised when a :class:`DecisionResult` cannot become ``plan_lines``.

    Scope, stated precisely rather than left implicit: this repo's fabric
    service (``fabric/service.py``) serializes every ``DecisionStep.action``
    through ``canonical.to_jsonable``, which for a PDDL action object takes
    the generic ``__dict__``-publicization branch -- *not* its ``__repr__``.
    Verified this session: a real ``PDDLAction`` reprs as ``"(unstack a b)"``
    but serializes into a ``DecisionResult`` as
    ``{"action_id": 0, "arguments": [2, 0]}``, an opaque id-based encoding
    that carries no action or object *names* at all. Recovering the VAL-format
    text this module's writer expects therefore requires re-deriving those
    names from the exact domain the request already identifies
    (``request.domain_arguments["domain_path"|"problem_path"]``) -- not
    guessing them from the ids alone. Any result that is not the classical
    PDDL family, or whose action shape does not match the encoding above, is
    refused here by name (``UNSUPPORTED_DOMAIN_FAMILY``) rather than produce
    plan_lines that only look plausible.
    """


def decision_result_to_plan_lines(result: DecisionResult) -> list[str]:
    """Convert a classical-PDDL-solver :class:`DecisionResult` to plan_lines.

    Scoped exactly to the PDDL/classical-solver family
    (``request.domain in PDDL_DOMAIN_FAMILY`` with a ``domain_path`` /
    ``problem_path`` pair recorded in ``request.domain_arguments``, exactly
    as ``fabric/pddl_engine.py``'s own ``PDDLDomain(domain_path,
    problem_path)`` construction). It reconstructs that same domain to
    resolve each step's serialized ``{"action_id", "arguments"}`` encoding
    (see :class:`PowlProjectionUnsupported`) into the VAL-format
    ``"(name arg1 arg2)"`` lines :func:`project_plan_to_powl` already
    consumes -- the identical stringification
    ``pddl_engine.py::_write_plan`` performs via ``f"{action}"`` on the raw,
    unserialized action object.

    Any result outside this family -- a different domain, or a step action
    that is not exactly the ``{"action_id": int, "arguments": [int, ...]}``
    shape -- raises :class:`PowlProjectionUnsupported` rather than guessing.
    This function deliberately does not attempt a generic
    ``DecisionStep.action`` -> PDDL-string converter for arbitrary domains;
    that is real unsolved semantic work, out of scope here.
    """
    request = result.request
    if request.domain not in PDDL_DOMAIN_FAMILY:
        raise PowlProjectionUnsupported(
            "UNSUPPORTED_DOMAIN_FAMILY: decision_result_to_plan_lines only "
            f"supports {sorted(PDDL_DOMAIN_FAMILY)}, got domain="
            f"{request.domain!r}"
        )

    domain_path = request.domain_arguments.get("domain_path")
    problem_path = request.domain_arguments.get("problem_path")
    if not isinstance(domain_path, str) or not isinstance(problem_path, str):
        raise PowlProjectionUnsupported(
            "UNSUPPORTED_DOMAIN_FAMILY: request.domain_arguments must carry "
            "string 'domain_path' and 'problem_path' to resolve action_id/"
            f"arguments into names; got keys={sorted(request.domain_arguments)}"
        )

    try:
        from autofde_lab.hub.domain.pddl import PDDLDomain
    except Exception as exc:  # noqa: BLE001 - any import failure is refusal
        raise PowlProjectionUnsupported(
            f"UNSUPPORTED_DOMAIN_FAMILY: PDDLDomain backend unavailable: {exc}"
        ) from exc

    try:
        domain = PDDLDomain(domain_path, problem_path)
        task = domain._task
    except Exception as exc:  # noqa: BLE001 - any reconstruction failure
        raise PowlProjectionUnsupported(
            "UNSUPPORTED_DOMAIN_FAMILY: cannot reconstruct the PDDL domain "
            f"from domain_path={domain_path!r} problem_path={problem_path!r}: "
            f"{exc}"
        ) from exc

    lines: list[str] = []
    for step in result.steps:
        action = step.action
        valid_shape = (
            isinstance(action, dict)
            and set(action) == {"action_id", "arguments"}
            and isinstance(action.get("action_id"), int)
            and isinstance(action.get("arguments"), list)
            and all(isinstance(arg, int) for arg in action["arguments"])
        )
        if not valid_shape:
            raise PowlProjectionUnsupported(
                "UNSUPPORTED_DOMAIN_FAMILY: step "
                f"{step.index} action is not the PDDL "
                "{'action_id': int, 'arguments': [int, ...]} encoding this "
                f"converter understands: {action!r}"
            )
        try:
            name = task.action_name(action["action_id"])
            arguments = [task.object_name(index) for index in action["arguments"]]
        except Exception as exc:  # noqa: BLE001 - id resolution failure
            raise PowlProjectionUnsupported(
                "UNSUPPORTED_DOMAIN_FAMILY: cannot resolve step "
                f"{step.index} action_id/arguments against the reconstructed "
                f"domain: {exc}"
            ) from exc
        lines.append("(" + " ".join([name, *arguments]) + ")")

    return lines


RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


@dataclass(frozen=True)
class ParameterBinding:
    """One ``mfwp:ParameterBinding`` node."""

    iri: str
    binding_index: int
    parameter: str
    bound_object: str


@dataclass(frozen=True)
class ActivityLeaf:
    """One ``powl2:ActivityLeaf`` node."""

    iri: str
    activity_label: str
    implements_action: str
    plan_ordinal: int
    binds_parameter: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ChildBinding:
    """One ``powl2:ChildBinding`` slot."""

    iri: str
    child_index: int
    child_model: str
    precedes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PowlModel:
    """The decoded ``powl2:Model`` root plus everything it reaches."""

    iri: str
    types: Tuple[str, ...]
    derived_from: Tuple[str, ...]
    was_derived_from: Tuple[str, ...]
    has_child: Tuple[str, ...]
    projection: Optional[str] = None
    planner_run: Optional[str] = None
    domain_digest: Optional[str] = None
    problem_digest: Optional[str] = None
    activity_count: Optional[int] = None
    children: Dict[str, ChildBinding] = field(default_factory=dict)
    leaves: Dict[str, ActivityLeaf] = field(default_factory=dict)
    bindings: Dict[str, ParameterBinding] = field(default_factory=dict)

    def ordered_children(self) -> List[ChildBinding]:
        return sorted(self.children.values(), key=lambda c: c.child_index)


# --- tokenizer -------------------------------------------------------------


def _split_top_level(text: str, separator: str) -> List[str]:
    """Split on ``separator`` outside of quoted literals and IRIs."""
    parts: List[str] = []
    current: List[str] = []
    in_quote = False
    in_iri = False
    escaped = False
    for char in text:
        if in_quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quote = False
            continue
        if in_iri:
            current.append(char)
            if char == ">":
                in_iri = False
            continue
        if char == '"':
            in_quote = True
            current.append(char)
        elif char == "<":
            in_iri = True
            current.append(char)
        elif char == separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if in_quote or in_iri:
        raise PowlDecodeError("unterminated literal or IRI")
    parts.append("".join(current))
    return parts


def _expand(name: str, prefixes: Dict[str, str]) -> str:
    prefix, _, local = name.partition(":")
    if prefix not in prefixes:
        raise PowlDecodeError(f"undeclared prefix {prefix!r} in {name!r}")
    return prefixes[prefix] + local


def _parse_term(token: str, prefixes: Dict[str, str]) -> Tuple[str, str, Optional[str]]:
    """Return ``(kind, value, datatype)`` where kind is ``iri`` or ``literal``."""
    token = token.strip()
    if not token:
        raise PowlDecodeError("empty term")
    if token.startswith("<"):
        if not token.endswith(">"):
            raise PowlDecodeError(f"malformed IRI term {token!r}")
        return "iri", token[1:-1], None
    if token.startswith('"'):
        closing = token.rfind('"')
        if closing == 0:
            raise PowlDecodeError(f"malformed literal {token!r}")
        value = token[1:closing].replace('\\"', '"').replace("\\n", "\n")
        tail = token[closing + 1 :].strip()
        if not tail:
            return "literal", value, XSD + "string"
        if not tail.startswith("^^"):
            raise PowlDecodeError(
                f"unsupported literal suffix {tail!r} (only ^^datatype accepted)"
            )
        datatype_token = tail[2:].strip()
        if datatype_token.startswith("<") and datatype_token.endswith(">"):
            return "literal", value, datatype_token[1:-1]
        return "literal", value, _expand(datatype_token, prefixes)
    if token in ("[", "]", "(", ")") or token.startswith("_:"):
        raise PowlDecodeError(
            f"unsupported Turtle construct {token!r}; this subset decoder "
            "accepts only IRIs and literals, never blank nodes or collections"
        )
    if ":" in token:
        return "iri", _expand(token, prefixes), None
    raise PowlDecodeError(f"unrecognised term {token!r}")


def _parse_graph(text: str) -> Dict[str, Dict[str, List[Tuple[str, str, Optional[str]]]]]:
    """Parse the subset into ``{subject: {predicate: [terms]}}``."""
    prefixes: Dict[str, str] = {}
    graph: Dict[str, Dict[str, List[Tuple[str, str, Optional[str]]]]] = {}

    block: List[str] = []
    blocks: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@prefix"):
            if block:
                raise PowlDecodeError("@prefix inside an unterminated statement")
            body = line[len("@prefix") :].strip().rstrip(".").strip()
            name, _, iri = body.partition(" ")
            name = name.strip().rstrip(":")
            iri = iri.strip()
            if not (iri.startswith("<") and iri.endswith(">")):
                raise PowlDecodeError(f"malformed @prefix declaration: {line!r}")
            prefixes[name] = iri[1:-1]
            continue
        block.append(line)
        if line.endswith("."):
            blocks.append(" ".join(block))
            block = []
    if block:
        raise PowlDecodeError(
            "unterminated statement at end of document: " + " ".join(block)[:80]
        )

    for statement in blocks:
        statement = statement.rstrip()[:-1].strip()  # drop terminating '.'
        if not statement.startswith("<") and ":" not in statement.split(" ")[0]:
            raise PowlDecodeError(f"statement does not begin with a subject: {statement[:80]!r}")
        if not statement.startswith("<"):
            raise PowlDecodeError(
                f"subject must be an absolute IRI in <>, got {statement.split(' ')[0]!r}"
            )
        # Real defect found and fixed forward this session: a subject IRI
        # that never closes with ">" on the same statement (e.g.
        # "<urn:x a powl2:Model .") previously leaked a bare, uncaught
        # `ValueError: substring not found` from `str.index` straight out
        # of `parse_powl_turtle` -- confirmed live, pinned as a regression
        # fixture in
        # tests/powl/test_turtle_bridge_runner_integration_chicago.py's
        # test_subject_iri_missing_closing_bracket_leaks_an_unwrapped_value_error
        # before this fix. This module's own docstring promises "anything
        # else is REFUSED with a named reason rather than silently
        # ignored" -- an unclosed subject IRI is exactly that case, and
        # must raise the same named `PowlDecodeError` every other
        # malformed-input path here already does, not a raw stdlib
        # exception with no domain-specific reason.
        if ">" not in statement:
            raise PowlDecodeError(
                f"subject IRI never closes with '>': {statement[:80]!r}"
            )
        end = statement.index(">")
        subject = statement[1:end]
        remainder = statement[end + 1 :].strip()
        if not remainder:
            raise PowlDecodeError(f"subject {subject!r} has no predicates")

        entry = graph.setdefault(subject, {})
        for pair in _split_top_level(remainder, ";"):
            pair = pair.strip()
            if not pair:
                continue
            predicate_token, _, object_text = pair.partition(" ")
            object_text = object_text.strip()
            if not object_text:
                raise PowlDecodeError(
                    f"predicate {predicate_token!r} on <{subject}> has no object"
                )
            if predicate_token == "a":
                predicate = RDF_TYPE
            elif predicate_token.startswith("<") and predicate_token.endswith(">"):
                predicate = predicate_token[1:-1]
            else:
                predicate = _expand(predicate_token, prefixes)
            for token in _split_top_level(object_text, ","):
                entry.setdefault(predicate, []).append(_parse_term(token, prefixes))

    return graph


# --- model construction ----------------------------------------------------


def _iris(terms: List[Tuple[str, str, Optional[str]]], predicate: str, subject: str) -> List[str]:
    values = []
    for kind, value, _ in terms:
        if kind != "iri":
            raise PowlDecodeError(
                f"<{subject}> {predicate}: expected an IRI object, got literal {value!r}"
            )
        values.append(value)
    return values


def _one_integer(
    terms: List[Tuple[str, str, Optional[str]]], predicate: str, subject: str
) -> int:
    if len(terms) != 1:
        raise PowlDecodeError(
            f"<{subject}> {predicate}: expected exactly 1 value, got {len(terms)}"
        )
    kind, value, datatype = terms[0]
    if kind != "literal" or datatype != XSD + "integer":
        raise PowlDecodeError(
            f"<{subject}> {predicate}: must be an xsd:integer literal, got "
            f"{kind} with datatype {datatype!r}"
        )
    try:
        return int(value)
    except ValueError as exc:  # pragma: no cover - datatype check precedes
        raise PowlDecodeError(f"<{subject}> {predicate}: {value!r} is not an integer") from exc


def _one_string(
    terms: List[Tuple[str, str, Optional[str]]], predicate: str, subject: str
) -> str:
    if len(terms) != 1:
        raise PowlDecodeError(
            f"<{subject}> {predicate}: expected exactly 1 value, got {len(terms)}"
        )
    kind, value, datatype = terms[0]
    if kind != "literal" or datatype != XSD + "string":
        raise PowlDecodeError(
            f"<{subject}> {predicate}: must be an xsd:string literal, got "
            f"{kind} with datatype {datatype!r}"
        )
    return value


def _one_iri(
    terms: List[Tuple[str, str, Optional[str]]], predicate: str, subject: str
) -> str:
    values = _iris(terms, predicate, subject)
    if len(values) != 1:
        raise PowlDecodeError(
            f"<{subject}> {predicate}: expected exactly 1 IRI, got {len(values)}"
        )
    return values[0]


def _optional_plain(
    entry: Dict[str, List[Tuple[str, str, Optional[str]]]], predicate: str
) -> Optional[str]:
    terms = entry.get(predicate)
    if not terms:
        return None
    return terms[0][1]


def parse_powl_turtle(text: str) -> PowlModel:
    """Decode POWL2 Turtle into a :class:`PowlModel`, or raise.

    Raises :class:`PowlDecodeError` on anything outside the accepted subset,
    on a SHACL-relevant cardinality/datatype violation reachable at parse
    time, and on the structural defects :func:`validate_powl` checks (this
    function calls it before returning).

    Known scope limit, stated rather than left implicit: ``powl2:SilentLeaf``
    (which mfw's Rust emitter can produce, and which carries no
    ``powl2:activityLabel`` and no ``mfwp:implementsAction``) is not modelled
    here. A document containing one is REFUSED explicitly, by name, with an
    ``UNSUPPORTED_CONSTRUCT:`` reason (see :data:`UNSUPPORTED_NODE_TYPES`) --
    not silently accepted, and not misreported as a dangling reference. This
    projector never emits one, and ``~/mfw/runs/ticket-10/plan.powl.ttl``
    contains none.
    """
    graph = _parse_graph(text)

    roots = [
        subject
        for subject, entry in graph.items()
        if POWL2 + "Model" in [v for k, v, _ in entry.get(RDF_TYPE, [])]
    ]
    if len(roots) != 1:
        raise PowlDecodeError(
            f"expected exactly 1 powl2:Model root, found {len(roots)}"
        )
    root = roots[0]
    entry = graph[root]

    children: Dict[str, ChildBinding] = {}
    leaves: Dict[str, ActivityLeaf] = {}
    bindings: Dict[str, ParameterBinding] = {}

    for subject, node in graph.items():
        types = [v for _, v, _ in node.get(RDF_TYPE, [])]
        for node_type in types:
            if node_type in UNSUPPORTED_NODE_TYPES:
                short = "powl2:" + node_type[len(POWL2) :]
                raise PowlDecodeError(
                    f"UNSUPPORTED_CONSTRUCT: {short} at <{subject}> -- "
                    f"{UNSUPPORTED_NODE_TYPES[node_type]}."
                )
        if POWL2 + "ChildBinding" in types:
            if POWL2 + "childIndex" not in node:
                raise PowlDecodeError(f"<{subject}>: powl2:childIndex missing (minCount 1)")
            if POWL2 + "childModel" not in node:
                raise PowlDecodeError(f"<{subject}>: powl2:childModel missing (minCount 1)")
            children[subject] = ChildBinding(
                iri=subject,
                child_index=_one_integer(
                    node[POWL2 + "childIndex"], "powl2:childIndex", subject
                ),
                child_model=_one_iri(
                    node[POWL2 + "childModel"], "powl2:childModel", subject
                ),
                precedes=tuple(
                    _iris(node.get(POWL2 + "precedes", []), "powl2:precedes", subject)
                ),
            )
        if POWL2 + "ActivityLeaf" in types:
            if POWL2 + "activityLabel" not in node:
                raise PowlDecodeError(
                    f"<{subject}>: powl2:activityLabel missing (minCount 1)"
                )
            if MFWP + "planOrdinal" not in node:
                raise PowlDecodeError(
                    f"<{subject}>: mfwp:planOrdinal missing (minCount 1)"
                )
            if MFWP + "implementsAction" not in node:
                raise PowlDecodeError(
                    f"<{subject}>: mfwp:implementsAction missing (minCount 1). "
                    "powl2:ActivityLeafShape requires every activity to bind "
                    "its grounded action; an unbound activity is untraceable."
                )
            leaves[subject] = ActivityLeaf(
                iri=subject,
                activity_label=_one_string(
                    node[POWL2 + "activityLabel"], "powl2:activityLabel", subject
                ),
                implements_action=_one_iri(
                    node[MFWP + "implementsAction"], "mfwp:implementsAction", subject
                ),
                plan_ordinal=_one_integer(
                    node[MFWP + "planOrdinal"], "mfwp:planOrdinal", subject
                ),
                binds_parameter=tuple(
                    _iris(
                        node.get(MFWP + "bindsParameter", []),
                        "mfwp:bindsParameter",
                        subject,
                    )
                ),
            )
        if MFWP + "ParameterBinding" in types:
            bindings[subject] = ParameterBinding(
                iri=subject,
                binding_index=_one_integer(
                    node.get(MFWP + "bindingIndex", []), "mfwp:bindingIndex", subject
                ),
                parameter=_one_iri(
                    node.get(MFWP + "parameter", []), "mfwp:parameter", subject
                ),
                bound_object=_one_iri(
                    node.get(MFWP + "boundObject", []), "mfwp:boundObject", subject
                ),
            )

    activity_count = None
    if MFWP + "activityCount" in entry:
        activity_count = _one_integer(
            entry[MFWP + "activityCount"], "mfwp:activityCount", root
        )

    model = PowlModel(
        iri=root,
        types=tuple(v for _, v, _ in entry.get(RDF_TYPE, [])),
        derived_from=tuple(
            _iris(entry.get(POWL2 + "derivedFrom", []), "powl2:derivedFrom", root)
        ),
        was_derived_from=tuple(
            _iris(entry.get(PROV + "wasDerivedFrom", []), "prov:wasDerivedFrom", root)
        ),
        has_child=tuple(
            _iris(entry.get(POWL2 + "hasChild", []), "powl2:hasChild", root)
        ),
        projection=_optional_plain(entry, MFWP + "projection"),
        planner_run=_optional_plain(entry, MFWP + "plannerRun"),
        domain_digest=_optional_plain(entry, MFWP + "domainDigest"),
        problem_digest=_optional_plain(entry, MFWP + "problemDigest"),
        activity_count=activity_count,
        children=children,
        leaves=leaves,
        bindings=bindings,
    )
    validate_powl(model)
    return model


def validate_powl(model: PowlModel) -> PowlModel:
    """Re-express the committed SHACL shapes plus structural checks.

    The shape file ``~/mfw/mfw-planner/shapes/powl2.shacl.ttl`` declares 3
    node shapes carrying 6 ``sh:property`` constraint blocks:

    1. ``powl2:ModelShape``        -- ``powl2:derivedFrom`` minCount 1
    2. ``powl2:ChildBindingShape`` -- ``powl2:childIndex`` minCount/maxCount 1,
       datatype ``xsd:integer``
    3. ``powl2:ChildBindingShape`` -- ``powl2:childModel`` minCount/maxCount 1
    4. ``powl2:ActivityLeafShape`` -- ``powl2:activityLabel`` minCount/maxCount 1,
       datatype ``xsd:string``
    5. ``powl2:ActivityLeafShape`` -- ``mfwp:implementsAction`` minCount/maxCount 1
    6. ``powl2:ActivityLeafShape`` -- ``mfwp:planOrdinal`` minCount/maxCount 1,
       datatype ``xsd:integer``

    Cardinality and datatype for 2-6 are enforced during decoding (a violation
    cannot survive to produce a model object). What remains here is (1) and the
    structural invariants SHACL does not express: contiguous child indices,
    acyclic ``powl2:precedes``, and no dangling reference.

    Note that ``prov:wasDerivedFrom`` is required by this repo's emitter and by
    mfw's own emitter, but is NOT in the shape file -- see the tests for that
    disagreement.
    """
    if not model.derived_from:
        raise PowlDecodeError(
            f"<{model.iri}>: powl2:derivedFrom missing (powl2:ModelShape minCount 1)"
        )
    if not model.was_derived_from:
        raise PowlDecodeError(
            f"<{model.iri}>: prov:wasDerivedFrom missing; mfw's emitter binds "
            "every plan to its source domain"
        )

    indices = sorted(child.child_index for child in model.children.values())
    if len(indices) != len(set(indices)):
        raise PowlDecodeError(f"duplicate powl2:childIndex among {indices}")
    if indices and indices != list(range(len(indices))):
        raise PowlDecodeError(
            f"powl2:childIndex values are not contiguous from 0: {indices}"
        )

    if model.activity_count is not None and model.activity_count != len(model.children):
        raise PowlDecodeError(
            f"mfwp:activityCount {model.activity_count} != {len(model.children)} "
            "child bindings"
        )

    for child_iri in model.has_child:
        if child_iri not in model.children:
            raise PowlDecodeError(
                f"<{model.iri}> powl2:hasChild <{child_iri}>: no such powl2:ChildBinding"
            )

    for child in model.children.values():
        if child.child_model not in model.leaves:
            raise PowlDecodeError(
                f"<{child.iri}> powl2:childModel <{child.child_model}>: dangling "
                "reference, no such powl2:ActivityLeaf"
            )
        for target in child.precedes:
            if target not in model.children:
                raise PowlDecodeError(
                    f"<{child.iri}> powl2:precedes <{target}>: dangling reference, "
                    "no such powl2:ChildBinding"
                )

    for leaf in model.leaves.values():
        for binding_iri in leaf.binds_parameter:
            if binding_iri not in model.bindings:
                raise PowlDecodeError(
                    f"<{leaf.iri}> mfwp:bindsParameter <{binding_iri}>: dangling "
                    "reference, no such mfwp:ParameterBinding"
                )

    _assert_acyclic(model)
    return model


def _assert_acyclic(model: PowlModel) -> None:
    """Depth-first cycle detection over ``powl2:precedes``.

    A cycle means the "partial order" is not an order; a downstream scheduler
    would deadlock or, worse, pick an arbitrary linearisation.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {iri: WHITE for iri in model.children}

    def visit(node: str, stack: List[str]) -> None:
        colour[node] = GREY
        for target in model.children[node].precedes:
            if colour.get(target) == GREY:
                cycle = " -> ".join(stack[stack.index(target) :] + [target])
                raise PowlDecodeError(f"powl2:precedes contains a cycle: {cycle}")
            if colour.get(target) == WHITE:
                visit(target, stack + [target])
        colour[node] = BLACK

    for iri in sorted(colour):
        if colour[iri] == WHITE:
            visit(iri, [iri])
