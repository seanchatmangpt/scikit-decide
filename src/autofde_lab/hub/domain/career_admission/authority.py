# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Load :class:`CapabilityFact` tuples from a real, generated authority file.

Motivation -- a structural defect in ``DEFAULT_FACTS``
-----------------------------------------------------

``DEFAULT_FACTS`` in :mod:`.career_admission` is a curated fixture in which
two facts have empty ``prerequisite_ids`` and every other fact closes over
those two. Consequently at least one action is applicable from every
non-goal state and the goal is always reachable: **a blocked state is
structurally unreachable there**. That makes the fixture unable to model the
one situation the ecosystem actually needs modelled -- a parent workflow
that is genuinely stuck.

This module builds a second, independent fixture from an authority file that
is *generated, not curated*: ``ontology/v26.8.1/legacy-capabilities.ttl`` in
the ``ggen-legacy`` repository (65 ``ggen:LegacyCapability`` individuals
emitted by ``tools/v26.8.1/legacy_archaeology.py`` from mined git history).
The file is read **in place**; nothing is copied into this repository.

Scope -- this is search-graph work only
---------------------------------------

Facts are loaded and reachability is computed. No receipt, admission,
actuation, or standing-closure semantics are implemented or implied here.
"UNKNOWN standing" below is a *literal read* of a predicate in someone
else's file, not a standing determination made by this repository.

Why a local reader instead of ``autofde_lab.fabric.ontology.parse_turtle``
----------------------------------------------------------------------

``parse_turtle`` recognises a new subject only via the exact form
``<absolute-iri> a ...`` (it tests ``line.startswith("<") and "> a " in
line``). Every subject in the ggen-legacy file is a **prefixed name**::

    legacy:legacy_wizard_command a ggen:LegacyCapability ;

so ``parse_turtle`` would attach all 1600+ predicate lines to ``subject is
None`` and return an empty graph. That single construct -- prefixed
subjects -- is what forces the small local reader below. (The file is
otherwise within reach: one statement per line, no blank nodes, no RDF
collections, no triple-quoted literals; it does contain backslash-escaped
quotes inside literals, which the reader handles.)

Blockedness criterion
---------------------

Every one of the 65 individuals carries ``ggen:hasStanding ggen:UNKNOWN``
and ``ggen:equivalenceVerifier "UNASSIGNED"`` -- i.e. the ontology asserts
of all of them that no verifier exists that could establish equivalence.
Taken alone that would make *every* fact unadmittable and the domain
degenerate. The ontology does, however, record a second, distinct route: a
named successor carrying the capability forward, via a non-empty
``ggen:replacementOwner`` or ``ggen:migrationPath``.

A capability is therefore treated as **blocked** when it has UNKNOWN
standing, an UNASSIGNED equivalence verifier, *and* neither a replacement
owner nor a migration path -- no verification route and no succession
route. 45 of the 65 individuals meet this; notably it is exactly the 11
``ggen:REFUSED`` individuals plus 34 ``ggen:ARCHIVED`` ones, so the
``REFUSED`` disposition is *entirely* blocked.

Blocked facts are given a prerequisite id (:data:`UNASSIGNED_VERIFIER_ID`)
that no fact in the loaded set provides, so no action sequence can ever
admit them. Since ``category`` is mapped from ``ggen:hasDisposition`` and
every ``REFUSED`` capability is blocked, a plan can admit every admittable
fact and still never cover the ``REFUSED`` category: the domain reaches a
state with an empty applicable-action set that is not a goal. That is a
genuinely reachable blocked state, asserted by the ecosystem's own
ontology rather than by a fixture written to produce it.
"""

from __future__ import annotations

import os
import re
from typing import Dict, FrozenSet, List, Optional, Tuple

from .career_admission import CapabilityFact

#: Default location of the ggen-legacy authority file (read in place).
DEFAULT_AUTHORITY_PATH = os.path.expanduser(
    "~/ggen-legacy/ontology/v26.8.1/legacy-capabilities.ttl"
)

#: Prerequisite id used for capabilities the ontology leaves with no
#: verification route and no succession route. Deliberately not a capability
#: id, so no fact in the loaded set can ever provide it.
UNASSIGNED_VERIFIER_ID = "ggen:equivalenceVerifier/UNASSIGNED"

_SUBJECT_RE = re.compile(r"^(\w+):([\w./-]+)\s+a\s+(\w+:\w+)\s*;?\s*$")
_PREDICATE_RE = re.compile(r"^(\w+:[\w./-]+)\s+(.*?)\s*[;.]\s*$")
_LITERAL_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"')


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def parse_legacy_turtle(text: str) -> Dict[str, Dict[str, List[str]]]:
    """Read the prefixed-subject Turtle subset used by ggen-legacy.

    Returns ``{subject_curie: {predicate_curie: [object, ...]}}``. Literal
    objects are unquoted and unescaped; prefixed-name objects (e.g.
    ``ggen:UNKNOWN``) are returned verbatim. See the module docstring for
    why this exists alongside
    :func:`autofde_lab.fabric.ontology.parse_turtle`.
    """
    graph: Dict[str, Dict[str, List[str]]] = {}
    subject: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("@prefix"):
            continue

        subject_match = _SUBJECT_RE.match(line)
        if subject_match:
            subject = f"{subject_match.group(1)}:{subject_match.group(2)}"
            graph.setdefault(subject, {}).setdefault("a", []).append(
                subject_match.group(3)
            )
            continue

        if subject is None:
            continue

        predicate_match = _PREDICATE_RE.match(line)
        if not predicate_match:
            continue
        predicate, obj = predicate_match.group(1), predicate_match.group(2)

        literal_match = _LITERAL_RE.match(obj)
        value = _unescape(literal_match.group(1)) if literal_match else obj
        graph[subject].setdefault(predicate, []).append(value)

        if line.endswith("."):
            subject = None

    return graph


def _first(entry: Dict[str, List[str]], predicate: str) -> str:
    values = entry.get(predicate)
    return values[0] if values else ""


def is_blocked_capability(entry: Dict[str, List[str]]) -> bool:
    """True when the ontology leaves a capability with no admission route.

    UNKNOWN standing and an UNASSIGNED equivalence verifier (no verification
    route), *and* neither a replacement owner nor a migration path (no
    succession route). See the module docstring.
    """
    unverifiable = (
        _first(entry, "ggen:hasStanding") == "ggen:UNKNOWN"
        and _first(entry, "ggen:equivalenceVerifier") == "UNASSIGNED"
    )
    has_successor = bool(
        _first(entry, "ggen:replacementOwner").strip()
        or _first(entry, "ggen:migrationPath").strip()
    )
    return unverifiable and not has_successor


def load_capability_facts(
    path: str = DEFAULT_AUTHORITY_PATH,
) -> Tuple[Tuple[CapabilityFact, ...], FrozenSet[str]]:
    """Load capability facts from a ggen-legacy capability ontology.

    ``category`` is mapped from ``ggen:hasDisposition`` (ARCHIVED / REFUSED /
    REPLACED / SUBSUMED). Costs are uniform (1.0): the authority file records
    no effort metric, and inventing one would be fixture curation of exactly
    the kind this module exists to avoid.

    :returns: ``(facts, required_categories)`` ready for
        :class:`~.career_admission.CareerAdmission`.
    """
    with open(path, "r", encoding="utf-8") as handle:
        graph = parse_legacy_turtle(handle.read())

    facts: List[CapabilityFact] = []
    categories: List[str] = []
    for entry in graph.values():
        if "ggen:LegacyCapability" not in entry.get("a", []):
            continue
        identifier = _first(entry, "ggen:capabilityId")
        if not identifier:
            continue
        disposition = _first(entry, "ggen:hasDisposition").removeprefix("ggen:")
        category = disposition or "UNDISPOSED"
        categories.append(category)
        facts.append(
            CapabilityFact(
                id=identifier,
                category=category,
                cost=1.0,
                prerequisite_ids=(
                    (UNASSIGNED_VERIFIER_ID,) if is_blocked_capability(entry) else ()
                ),
            )
        )

    return tuple(facts), frozenset(categories)


def blocked_prerequisites(
    facts: Tuple[CapabilityFact, ...],
) -> Dict[str, Tuple[str, ...]]:
    """Per fact, the prerequisite ids that no fact in ``facts`` provides.

    A fact appearing here can never be admitted from any state, because no
    action produces the missing prerequisite. Purely a reachability
    computation over the given tuple -- it makes no claim about the world.
    """
    provided = {fact.id for fact in facts}
    missing: Dict[str, Tuple[str, ...]] = {}
    for fact in facts:
        dangling = tuple(
            prerequisite
            for prerequisite in fact.prerequisite_ids
            if prerequisite not in provided
        )
        if dangling:
            missing[fact.id] = dangling
    return missing
